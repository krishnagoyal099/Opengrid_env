import os
import json
from openai import OpenAI
from .models import GridAction, BusAdjustment, TopologyAction

# Use mandatory environment variables
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")
API_KEY = os.getenv("HF_TOKEN", os.getenv("OPENAI_API_KEY", ""))


def _get_client():
    """Lazy client creation to avoid errors when env vars aren't set."""
    return OpenAI(base_url=API_BASE_URL, api_key=API_KEY)


SYSTEM_PROMPT = """You are a Power Grid Controller AI. Your goal is to maintain grid stability.

Key objectives:
1. Keep grid frequency close to 50.0 Hz (acceptable: 49.5–50.5 Hz)
2. Prevent transmission line overloads (rho < 1.0)
3. Avoid grid islanding (blackout)

Available actions:
1. bus_adjustments: List of {"bus_id": int, "delta": float}
   - Positive delta = increase power injection (discharge battery / ramp up generator)
   - Negative delta = decrease power injection (charge battery / ramp down generator)
   - Only works on battery and generator/slack buses (not load/solar/wind)
2. topology_actions: List of {"line_id": str, "action": "open" | "close"}
   - Opening a line removes it; closing reconnects. 3-step cooldown after each switch.
   - WARNING: Opening lines can cause islanding → blackout → -100 reward

Strategy tips:
- If frequency < 50 Hz: grid needs more generation → discharge batteries or ramp up generators
- If frequency > 50 Hz: grid has excess generation → charge batteries or ramp down
- If a line rho > 0.9: it's near overload → consider rerouting power, NOT opening the line
- Prefer minimal actions. Do-nothing is better than reckless switching.

Respond with ONLY a valid JSON object, no markdown, no explanation. Example:
{"bus_adjustments": [{"bus_id": 2, "delta": 5.0}], "topology_actions": []}
"""


def parse_action_response(response_text: str) -> GridAction:
    """Parse LLM response into a GridAction. Falls back to no-op on parse errors."""
    try:
        clean_text = response_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        return GridAction(**data)
    except Exception:
        return GridAction()


def llm_policy(obs):
    """LLM-based policy using the OpenAI-compatible API."""
    client = _get_client()
    obs_json = obs.model_dump_json()

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Current Grid State:\n{obs_json}"}
            ],
            temperature=0.0,
            max_tokens=300
        )
        action_str = response.choices[0].message.content
        return parse_action_response(action_str)
    except Exception as e:
        print(f"[DEBUG] LLM policy error: {e}", flush=True)
        return GridAction()


def heuristic_policy(obs):
    """
    Rule-based baseline policy for reproducible scoring.
    
    Strategy:
    - Use batteries for frequency regulation (proportional control)
    - DO NOT open overloaded lines (causes cascading failures)
    - Instead, shed load or ramp generators to relieve overloads
    """
    adj = []
    freq = obs.grid_frequency
    freq_error = freq - 50.0  # positive = too high, negative = too low

    # Proportional frequency control via batteries
    for bus in obs.buses:
        if bus.type == 'battery':
            if abs(freq_error) > 0.1:
                # Proportional response: larger error → larger correction
                correction = -freq_error * 2.0  # negative freq_error → inject more
                correction = max(-10.0, min(10.0, correction))  # Clamp

                if correction > 0 and bus.soc > 0:
                    adj.append(BusAdjustment(bus_id=bus.id, delta=correction))
                elif correction < 0 and bus.soc < 50:
                    adj.append(BusAdjustment(bus_id=bus.id, delta=correction))

    # For overloaded lines: ramp down nearby generators instead of opening lines
    for line in obs.lines:
        if line.rho > 0.95 and line.connected:
            # Find generators and reduce their output slightly
            for bus in obs.buses:
                if bus.type in ['slack'] and bus.p_injection > 5:
                    adj.append(BusAdjustment(bus_id=bus.id, delta=-3.0))
                    break

    # No topology actions — much safer than opening overloaded lines
    return GridAction(bus_adjustments=adj, topology_actions=[])