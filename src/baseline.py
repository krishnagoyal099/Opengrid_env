"""
Baseline Policies for OpenGrid
================================
Provides two agent implementations:
1. heuristic_policy — deterministic rule-based baseline for reproducible scoring
2. llm_policy — LLM-based policy using OpenAI-compatible API

Both support GridObservation (single-agent) and ZoneObservation (multi-agent).
"""

import json
import logging
import os
from typing import List, Union

from openai import OpenAI
from .models import GridAction, BusAdjustment, GridObservation, ZoneObservation

logger = logging.getLogger(__name__)

# API configuration — HF_TOKEN for Hugging Face endpoints, OPENAI_API_KEY for OpenAI
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")
API_KEY = os.getenv("OPENAI_API_KEY", os.getenv("HF_TOKEN", ""))

# Cached client instance
_CLIENT = None


def _get_client() -> OpenAI:
    """Lazy-cached client creation."""
    global _CLIENT
    if _CLIENT is None:
        if not API_KEY:
            raise RuntimeError(
                "Missing API key. Set OPENAI_API_KEY or HF_TOKEN environment variable."
            )
        _CLIENT = OpenAI(base_url=API_BASE_URL, api_key=API_KEY, timeout=15.0)
    return _CLIENT


def _obs_buses(obs):
    """Extract bus list from either GridObservation or ZoneObservation."""
    return getattr(obs, "buses", getattr(obs, "local_buses", []))


def _obs_lines(obs):
    """Extract line list from either GridObservation or ZoneObservation."""
    if hasattr(obs, "lines"):
        return obs.lines
    internal = getattr(obs, "internal_lines", [])
    boundary = getattr(obs, "boundary_lines", [])
    return list(internal) + list(boundary)


SYSTEM_PROMPT = """You are a Power Grid Controller AI. Your goal is to maintain grid stability.

Key objectives:
1. Keep grid frequency close to 50.0 Hz (acceptable: 49.5–50.5 Hz)
2. Prevent transmission line overloads (rho < 1.0)
3. Avoid grid islanding (blackout)

Available actions:
1. bus_adjustments: List of {"bus_id": int, "delta": float}
   - Positive delta = increase power injection (discharge battery / ramp up generator)
   - Negative delta = decrease power injection (charge battery / ramp down generator)
   - Only works on battery and generator buses (NOT slack, load, solar, or wind)
   - Slack bus injection is computed by physics — adjustments are ignored
2. topology_actions: List of {"line_id": str, "action": "open" | "close"}
   - Opening a line removes it; closing reconnects. 3-step cooldown after each switch.
   - WARNING: Opening lines can cause islanding → blackout → -100 reward
   - Prefer NO topology actions unless absolutely necessary.

Strategy tips:
- If frequency < 50 Hz: grid needs more generation → discharge batteries or ramp up generators
- If frequency > 50 Hz: grid has excess generation → charge batteries or ramp down generators
- If a line rho > 0.9: reduce generation at one end or increase at the other to shift flow
- Prefer minimal actions. Do-nothing is better than reckless switching.

Respond with ONLY a valid JSON object, no markdown, no explanation. Example:
{"bus_adjustments": [{"bus_id": 2, "delta": 5.0}], "topology_actions": []}
"""


def parse_action_response(response_text: str) -> GridAction:
    """Parse LLM response into a GridAction. Falls back to no-op on parse errors."""
    try:
        text = response_text.strip()

        # Remove fenced code block if present
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Extract first JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return GridAction()

        data = json.loads(text[start:end + 1])

        # Handle list wrapping
        if isinstance(data, list):
            data = data[0] if data else {}

        return GridAction(**data)
    except Exception:
        return GridAction()


def llm_policy(obs: Union[GridObservation, ZoneObservation]) -> GridAction:
    """LLM-based policy using the OpenAI-compatible API.

    Supports both GridObservation and ZoneObservation.
    Falls back to no-op on any error.
    """
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
            max_tokens=300,
        )
        action_str = response.choices[0].message.content
        return parse_action_response(action_str)
    except Exception as e:
        logger.debug("LLM policy error: %s", e, exc_info=True)
        return GridAction()


def heuristic_policy(
    obs: Union[GridObservation, ZoneObservation],
) -> GridAction:
    """Rule-based baseline policy for reproducible scoring.

    Strategy:
    - Use batteries and generators for frequency regulation (proportional control)
    - DO NOT open overloaded lines (causes cascading failures)
    - DO NOT adjust the slack bus (overwritten by physics solver)
    - Let the environment/safety layer clamp any out-of-range deltas

    Supports both GridObservation (single-agent) and ZoneObservation (multi-agent).
    """
    adj = []
    freq = obs.grid_frequency
    freq_error = freq - 50.0  # positive = too high, negative = too low

    buses = list(_obs_buses(obs))
    lines = list(_obs_lines(obs))

    batteries = [b for b in buses if b.type == 'battery']
    generators = [b for b in buses if b.type == 'generator']

    # --- 1. Proportional frequency control via batteries ---
    if abs(freq_error) > 0.1 and batteries:
        # Distribute correction across all available batteries
        correction_total = -freq_error * 15.0  # stronger gain than naive 2.0
        correction_total = max(-20.0, min(20.0, correction_total))
        per_battery = correction_total / len(batteries)

        for bus in batteries:
            if per_battery > 0 and bus.soc > 0:
                # Discharge — safety layer clamps to actual SOC
                adj.append(BusAdjustment(bus_id=bus.id, delta=per_battery))
            elif per_battery < 0:
                # Charge — safety layer clamps to remaining capacity
                adj.append(BusAdjustment(bus_id=bus.id, delta=per_battery))

    # --- 2. Generator response for larger deviations ---
    if abs(freq_error) > 0.25:
        for bus in generators:
            delta = -freq_error * 5.0
            ramp = getattr(bus, 'ramp_rate', 20.0)
            delta = max(-ramp, min(ramp, delta))
            adj.append(BusAdjustment(bus_id=bus.id, delta=delta))

    # --- 3. Overload relief via generators (not slack) ---
    adjusted_for_overload = set()
    for line in lines:
        if line.rho > 0.95 and line.connected:
            for bus in generators:
                if bus.id not in adjusted_for_overload and bus.p_injection > 5:
                    adj.append(BusAdjustment(bus_id=bus.id, delta=-3.0))
                    adjusted_for_overload.add(bus.id)
                    break

    # No topology actions — much safer than opening overloaded lines
    return GridAction(bus_adjustments=adj, topology_actions=[])