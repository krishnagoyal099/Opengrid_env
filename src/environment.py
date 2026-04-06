import numpy as np
import math
from typing import List, Dict, Tuple
from .models import GridObservation, GridAction, GridReward, GridInfo, LineStatus, BusState
from .physics import DCSolver, IslandedException

class OpenGridEnv:
    """
    OpenGrid: A renewable energy grid load-balancing environment.
    
    The agent must maintain grid stability by:
    - Balancing generation and load (frequency control)
    - Managing transmission line loading (congestion management)
    - Coordinating battery storage and topology switching
    """

    NOMINAL_FREQ = 50.0
    FREQ_DEADBAND = 0.5  # Hz — acceptable deviation band

    def __init__(self, config: Dict):
        self.config = config
        self.num_buses = config['num_buses']
        self.lines_config = config['lines']
        self.buses_config = config['buses']

        self.solver = DCSolver(self.num_buses)
        self.timestep = 0
        self.max_steps = config.get('max_steps', 50)

        self.bus_state = []
        self.line_state = []
        self.cooldowns = {}
        self.slack_injection = 0.0

        # Calibrate droop constant to system size:
        # Real-world: ~5% droop means full-load deviation → 2.5 Hz change (at 50 Hz)
        # droop = 2.5 / total_system_capacity  →  Hz per MW
        # This keeps frequency deviations in a realistic 0.5–2 Hz range for all grid sizes
        total_load = sum(
            b['base_p'] for b in self.buses_config if b['type'] == 'load'
        )
        total_gen = sum(
            b['max_p'] for b in self.buses_config
            if b['type'] in ['slack', 'generator', 'solar', 'wind']
        )
        total_system = max(total_load + total_gen, 50.0)  # Floor at 50 MW
        self.droop_constant = 2.5 / total_system

        # Per-episode RNG for reproducibility
        self._rng = None
        self._seed = config.get('seed', 42)

    def reset(self) -> GridObservation:
        """Reset the environment to initial state. Returns initial observation."""
        self.timestep = 0
        self.slack_injection = 0.0
        self.cooldowns = {l['id']: 0 for l in self.lines_config}

        # Create a per-episode RNG — deterministic for the same seed
        self._rng = np.random.default_rng(self._seed)

        self.bus_state = [
            {'id': b['id'], 'p': 0.0, 'soc': b.get('init_soc', 0.0)}
            for b in self.buses_config
        ]
        self.line_state = [
            {'id': l['id'], 'connected': True, 'flow': 0.0}
            for l in self.lines_config
        ]

        self._update_loads_and_renewables()
        self._run_power_flow()

        return self._get_obs()

    def step(self, action: GridAction) -> Tuple[GridObservation, GridReward, bool, GridInfo]:
        """Execute one step: apply action, update dynamics, solve physics, compute reward."""
        self.timestep += 1
        reward_components = {"survival": 1.0, "frequency": 0.0, "overload": 0.0, "action_cost": 0.0}
        is_blackout = False

        # 1. Apply topology actions (with cooldown enforcement)
        for t_act in action.topology_actions:
            l_id = t_act.line_id
            if l_id not in self.cooldowns:
                continue  # Guard against invalid line IDs
            if self.cooldowns[l_id] == 0:
                line = self._find_line(l_id)
                if line is None:
                    continue
                current_status = line['connected']
                new_status = (t_act.action == "close")

                if current_status != new_status:
                    line['connected'] = new_status
                    self.cooldowns[l_id] = 3
                    reward_components['action_cost'] -= 0.5

        # Tick cooldowns
        for l_id in self.cooldowns:
            self.cooldowns[l_id] = max(0, self.cooldowns[l_id] - 1)

        # 2. Apply power adjustment actions
        for adj in action.bus_adjustments:
            bus_cfg = self._find_bus_config(adj.bus_id)
            bus_dyn = self._find_bus_state(adj.bus_id)
            if bus_cfg is None or bus_dyn is None:
                continue  # Guard against invalid bus IDs

            delta = adj.delta

            if bus_cfg['type'] == 'battery':
                max_charge = bus_cfg['capacity'] - bus_dyn['soc']
                max_discharge = bus_dyn['soc']

                if delta > 0:
                    delta = min(delta, max_discharge)
                else:
                    delta = max(delta, -max_charge)

                bus_dyn['soc'] -= delta
                bus_dyn['p'] = delta

            elif bus_cfg['type'] not in ['load', 'solar', 'wind']:
                max_ramp = bus_cfg.get('ramp_rate', 10.0)
                delta = np.clip(delta, -max_ramp, max_ramp)
                new_p = bus_dyn['p'] + delta
                bus_dyn['p'] = np.clip(new_p, bus_cfg['min_p'], bus_cfg['max_p'])

        # 3. Update load/renewable dynamics
        self._update_loads_and_renewables()

        # 4. Solve physics
        try:
            self._run_power_flow()

            # Check line overloads
            for l in self.line_state:
                if l['connected']:
                    flow = l['flow']
                    limit = self._get_line_capacity(l['id'])
                    rho = abs(flow) / limit if limit > 0 else 0.0

                    if rho > 1.0:
                        reward_components['overload'] -= (rho - 1.0) ** 2 * 20
                    elif rho > 0.8:
                        reward_components['overload'] -= 0.1

            # Frequency reward: penalize deviation from 50 Hz
            # Capped so that surviving with bad frequency is always better than blackout (-100)
            # Max penalty per step: -1.5 → worst case 50 steps = -75 (< 100 blackout penalty)
            freq = self._compute_frequency()
            freq_dev = abs(freq - self.NOMINAL_FREQ)
            if freq_dev > self.FREQ_DEADBAND:
                raw_penalty = (freq_dev - self.FREQ_DEADBAND) * 0.5
                reward_components['frequency'] -= min(raw_penalty, 1.5)
            elif freq_dev < 0.1:
                reward_components['frequency'] += 0.2  # Bonus for tight control

        except IslandedException:
            is_blackout = True
            reward_components['survival'] = -100.0

        done = is_blackout or (self.timestep >= self.max_steps)

        total_reward = sum(reward_components.values())
        reward = GridReward(value=total_reward, components=reward_components)
        info = GridInfo(task_id=self.config['id'], is_blackout=is_blackout)

        return self._get_obs(), reward, done, info

    def state(self) -> GridObservation:
        """Return current state (alias for observation)."""
        return self._get_obs()

    # ---------- Internal Methods ----------

    def _run_power_flow(self):
        """Build active line list, solve DC power flow, update line flows and slack injection."""
        active_lines = []
        for l_cfg in self.lines_config:
            l_dyn = self._find_line(l_cfg['id'])
            if l_dyn and l_dyn['connected']:
                active_lines.append({
                    'id': l_cfg['id'], 'from': l_cfg['from'], 'to': l_cfg['to'],
                    'susceptance': l_cfg['susceptance'], 'connected': True
                })

        self.solver.update_grid(active_lines)

        p_inj = np.zeros(self.num_buses)
        for b_dyn in self.bus_state:
            p_inj[b_dyn['id']] = b_dyn['p']

        theta, flows, slack_inj = self.solver.solve(p_inj)

        # Update slack bus injection — this is what the slack bus actually produced
        self.slack_injection = slack_inj
        self.bus_state[0]['p'] = slack_inj

        # Update line flows
        for l in self.line_state:
            if l['connected'] and l['id'] in flows:
                l['flow'] = flows[l['id']]
            elif not l['connected']:
                l['flow'] = 0.0

    def _compute_frequency(self) -> float:
        """
        Frequency proxy using droop model, calibrated to system size.
        droop_constant = base_droop * (ref_MVA / total_capacity)
        f = f0 - droop_constant * P_slack
        """
        return self.NOMINAL_FREQ - self.droop_constant * self.slack_injection

    def _update_loads_and_renewables(self):
        """Update time-varying loads and renewable generation. Uses per-episode RNG."""
        for b_dyn in self.bus_state:
            b_cfg = self._find_bus_config(b_dyn['id'])
            if b_cfg is None:
                continue

            if b_cfg['type'] == 'load':
                daily_cycle = math.sin((self.timestep % 24 - 6) * math.pi / 12)
                b_dyn['p'] = -b_cfg['base_p'] * (0.8 + 0.4 * max(0, daily_cycle))

            elif b_cfg['type'] == 'solar':
                solar_cycle = max(0, math.sin((self.timestep % 24 - 6) * math.pi / 12))
                b_dyn['p'] = b_cfg['max_p'] * solar_cycle

            elif b_cfg['type'] == 'wind':
                # Per-episode RNG for reproducibility (not global random)
                wind_delta = self._rng.uniform(-5, 5)
                b_dyn['p'] = float(np.clip(b_dyn['p'] + wind_delta, 0, b_cfg['max_p']))

    def _get_obs(self) -> GridObservation:
        """Build observation from current state."""
        obs_lines = []
        for l in self.line_state:
            limit = self._get_line_capacity(l['id'])
            rho = abs(l['flow']) / limit if l['connected'] and limit > 0 else 0.0
            obs_lines.append(LineStatus(
                id=l['id'], connected=l['connected'], flow=round(l['flow'], 4), rho=round(rho, 4)
            ))

        obs_buses = []
        for b in self.bus_state:
            b_cfg = self._find_bus_config(b['id'])
            if b_cfg is None:
                continue
            obs_buses.append(BusState(
                id=b['id'], type=b_cfg['type'],
                p_injection=round(b['p'], 4),
                soc=round(b.get('soc', 0.0), 4),
                ramp_rate=b_cfg.get('ramp_rate', 0.0)
            ))

        freq = self._compute_frequency()

        return GridObservation(
            timestep=self.timestep,
            grid_frequency=round(freq, 4),
            buses=obs_buses,
            lines=obs_lines,
            cooldowns=self.cooldowns,
            is_blackout=False
        )

    # ---------- Lookup Helpers (guarded) ----------

    def _find_line(self, line_id: str):
        return next((l for l in self.line_state if l['id'] == line_id), None)

    def _find_bus_config(self, bus_id: int):
        return next((b for b in self.buses_config if b['id'] == bus_id), None)

    def _find_bus_state(self, bus_id: int):
        return next((b for b in self.bus_state if b['id'] == bus_id), None)

    def _get_line_capacity(self, line_id: str) -> float:
        cfg = next((ln for ln in self.lines_config if ln['id'] == line_id), None)
        return cfg['capacity'] if cfg else 1.0