import numpy as np
import math
from typing import List, Dict, Tuple, Optional
from .models import (
    GridObservation, GridAction, GridReward, GridInfo,
    LineStatus, BusState, ZoneObservation, ZoneInfo,
    SafetyReport, OversightReport, MultiAgentStepResult,
)
from .physics import DCSolver, IslandedException
from .safety import SafetyLayer
from .oversight import OversightAgent


class OpenGridEnv:
    """
    OpenGrid: A renewable energy grid load-balancing environment.

    Supports two modes:
    1. Single-agent (backward compatible): reset()/step()/state()
    2. Multi-agent POMDP: reset_multi()/step_multi() with per-zone
       partial observability, safety layer, and oversight agent.

    The agent(s) must maintain grid stability by:
    - Balancing generation and load (frequency control)
    - Managing transmission line loading (congestion management)
    - Coordinating battery storage and topology switching
    """

    NOMINAL_FREQ = 50.0
    FREQ_DEADBAND = 0.5  # Hz — acceptable deviation band
    FREQ_NOISE_STD = 0.05  # Hz — noise added to POMDP observations
    LINE_NOISE_STD = 0.02  # fraction — noise added to line readings

    def __init__(self, config: Dict):
        self.config = config
        self.num_buses = config['num_buses']
        self.lines_config = config['lines']
        self.buses_config = config['buses']

        # Resolve slack bus from config (not hardcoded to index 0)
        self.slack_bus_id = next(
            (b['id'] for b in self.buses_config if b['type'] == 'slack'), 0
        )

        self.solver = DCSolver(self.num_buses, slack_bus=self.slack_bus_id)
        self.timestep = 0
        self.max_steps = config.get('max_steps', 50)

        self.bus_state = []
        self.line_state = []
        self.cooldowns = {}
        self.slack_injection = 0.0
        self._is_blackout = False

        # Build index dicts for O(1) lookups
        self._bus_cfg_by_id = {b['id']: b for b in self.buses_config}
        self._line_cfg_by_id = {l['id']: l for l in self.lines_config}

        # Multi-agent config
        self.num_agents = config.get('num_agents', 1)
        self.zone_assignments = config.get('zone_assignments', {})
        self.zone_names = config.get('zone_names', [])
        self.zone_bus_ids = config.get('zone_bus_ids', {})
        self.internal_lines = config.get('internal_lines', {})
        self.boundary_lines = config.get('boundary_lines', {})

        # Safety and oversight (initialized on first multi-agent use)
        self.safety_layer = SafetyLayer(config)
        self.oversight_agent = OversightAgent(config)

        # Episode tracking for multi-agent rewards
        self._safety_reports_this_step: List[SafetyReport] = []
        self._oversight_report_this_step: Optional[OversightReport] = None

        # Calibrate droop constant to system size
        total_load = sum(
            b['base_p'] for b in self.buses_config if b['type'] == 'load'
        )
        total_gen = sum(
            b['max_p'] for b in self.buses_config
            if b['type'] in ['slack', 'generator', 'solar', 'wind']
        )
        total_system = max(total_load + total_gen, 50.0)
        self.droop_constant = 2.5 / total_system

        # Per-episode RNG — initialized early so _update_loads_and_renewables never crashes
        self._seed = config.get('seed', 42)
        self._rng = np.random.default_rng(self._seed)

    # ======================================================================
    # State Restoration (for GRPO environment-grounded rewards)
    # ======================================================================

    def _set_state(self, obs_dict: dict) -> None:
        """Restore the environment to a state described by an observation dict.

        This enables environment-grounded GRPO rewards: instead of scoring
        actions with a heuristic proxy, we restore the env to the observed state,
        step with the proposed action, and use the real reward.

        Args:
            obs_dict: A dict from ZoneObservation.model_dump() or
                      GridObservation.model_dump(), containing at minimum:
                      timestep, grid_frequency, and bus/line state.
        """
        self.timestep = obs_dict.get('timestep', 0)
        self._is_blackout = obs_dict.get('is_blackout', False)
        self.cooldowns = obs_dict.get('cooldowns', {k: 0 for k in self.cooldowns})

        # Restore bus state from observation
        local_buses = obs_dict.get('local_buses', obs_dict.get('buses', []))
        if local_buses:
            for b_obs in local_buses:
                b_dyn = self._find_bus_state(b_obs['id'])
                if b_dyn is not None:
                    b_dyn['p'] = b_obs.get('p_injection', b_dyn['p'])
                    b_dyn['soc'] = b_obs.get('soc', b_dyn.get('soc', 0.0))

        # Restore line state from observation
        all_lines = (obs_dict.get('internal_lines', []) or []) + \
                    (obs_dict.get('boundary_lines', []) or []) + \
                    (obs_dict.get('lines', []) or [])
        for l_obs in all_lines:
            l_dyn = self._find_line(l_obs['id'])
            if l_dyn is not None:
                l_dyn['connected'] = l_obs.get('connected', True)
                l_dyn['flow'] = l_obs.get('flow', 0.0)

        # Rebuild lookup indices
        self._bus_state_by_id = {b['id']: b for b in self.bus_state}
        self._line_state_by_id = {l['id']: l for l in self.line_state}

        # Re-derive slack injection from frequency if available
        freq = obs_dict.get('grid_frequency', self.NOMINAL_FREQ)
        self.slack_injection = (self.NOMINAL_FREQ - freq) / self.droop_constant

        # Update slack bus p to match
        slack_dyn = self._find_bus_state(self.slack_bus_id)
        if slack_dyn is not None:
            slack_dyn['p'] = self.slack_injection

    # ======================================================================
    # Single-Agent API (backward compatible)
    # ======================================================================

    def reset(self) -> GridObservation:
        """Reset the environment to initial state. Returns initial observation."""
        self.timestep = 0
        self.slack_injection = 0.0
        self.cooldowns = {l['id']: 0 for l in self.lines_config}
        self._rng = np.random.default_rng(self._seed)
        self.oversight_agent.reset()

        self.bus_state = []
        for b in self.buses_config:
            init_p = 0.0
            # Initialize generators at 50% capacity so slack doesn't absorb all load
            if b['type'] in ['generator']:
                init_p = b['max_p'] * 0.5
            self.bus_state.append({
                'id': b['id'], 'p': init_p, 'soc': b.get('init_soc', 0.0)
            })
        self.line_state = [
            {'id': l['id'], 'connected': True, 'flow': 0.0}
            for l in self.lines_config
        ]

        # Build O(1) lookup indices for dynamic state
        self._bus_state_by_id = {b['id']: b for b in self.bus_state}
        self._line_state_by_id = {l['id']: l for l in self.line_state}

        self._is_blackout = False
        self._update_loads_and_renewables()
        self._run_power_flow()

        return self._get_obs()

    def step(self, action: GridAction) -> Tuple[GridObservation, GridReward, bool, GridInfo]:
        """Execute one step: apply action, update dynamics, solve physics, compute reward."""
        self.timestep += 1
        reward_components = {"survival": 1.0, "frequency": 0.0, "overload": 0.0, "action_cost": 0.0}
        self._is_blackout = False

        # 1. Apply topology actions (with cooldown enforcement)
        for t_act in action.topology_actions:
            l_id = t_act.line_id
            if l_id not in self.cooldowns:
                continue
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
                continue

            delta = adj.delta

            if bus_cfg['type'] == 'battery':
                max_charge = bus_cfg['capacity'] - bus_dyn['soc']
                max_discharge = bus_dyn['soc']

                if delta > 0:
                    delta = min(delta, max_discharge)
                else:
                    delta = max(delta, -max_charge)

                bus_dyn['soc'] = np.clip(bus_dyn['soc'] - delta, 0.0, bus_cfg['capacity'])
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

            # Frequency reward
            freq = self._compute_frequency()
            freq_dev = abs(freq - self.NOMINAL_FREQ)
            if freq_dev > self.FREQ_DEADBAND:
                raw_penalty = (freq_dev - self.FREQ_DEADBAND) * 0.5
                reward_components['frequency'] -= min(raw_penalty, 1.5)
            elif freq_dev < 0.1:
                reward_components['frequency'] += 0.2

        except IslandedException:
            self._is_blackout = True
            reward_components['survival'] = -100.0

        done = self._is_blackout or (self.timestep >= self.max_steps)

        total_reward = sum(reward_components.values())
        reward = GridReward(value=total_reward, components=reward_components)
        info = GridInfo(task_id=self.config['id'], is_blackout=self._is_blackout)

        return self._get_obs(), reward, done, info

    def state(self) -> GridObservation:
        """Return current state (alias for observation)."""
        return self._get_obs()

    # ======================================================================
    # Multi-Agent POMDP API
    # ======================================================================

    def reset_multi(self) -> Dict[int, ZoneObservation]:
        """Reset environment and return per-agent partial observations."""
        self.reset()  # Reuse single-agent reset for state initialization
        return {
            agent_id: self._get_zone_obs(agent_id)
            for agent_id in range(self.num_agents)
        }

    def step_multi(self, agent_actions: Dict[int, GridAction]) -> MultiAgentStepResult:
        """Multi-agent step with safety layer and oversight.

        Flow:
        1. Safety layer validates each agent's actions
        2. Combine corrected actions into one GridAction
        3. Run single-agent step with combined action
        4. Oversight agent evaluates coordination
        5. Compute per-agent rewards (local + global + safety + coordination)
        """
        pre_frequency = self._compute_frequency()
        pre_bus_state = [dict(b) for b in self.bus_state]

        # --- 1. Safety validation per agent ---
        safety_reports: Dict[int, SafetyReport] = {}
        corrected_actions: Dict[int, GridAction] = {}

        for agent_id in range(self.num_agents):
            proposed = agent_actions.get(agent_id, GridAction())
            corrected, report = self.safety_layer.validate_and_correct(
                agent_id=agent_id,
                proposed_action=proposed,
                current_line_state=self.line_state,
                current_bus_state=self.bus_state,
                cooldowns=self.cooldowns,
            )
            corrected_actions[agent_id] = corrected
            safety_reports[agent_id] = report

        self._safety_reports_this_step = safety_reports

        # --- 2. Combine all corrected actions ---
        combined = GridAction(
            bus_adjustments=[
                adj for action in corrected_actions.values()
                for adj in action.bus_adjustments
            ],
            topology_actions=[
                t for action in corrected_actions.values()
                for t in action.topology_actions
            ],
        )

        # --- 3. Run the step ---
        obs, base_reward, done, info = self.step(combined)
        post_frequency = self._compute_frequency()

        # --- 4. Oversight evaluation ---
        oversight_report = self.oversight_agent.evaluate(
            agent_actions=agent_actions,
            safety_reports=safety_reports,
            pre_frequency=pre_frequency,
            post_frequency=post_frequency,
            pre_bus_state=pre_bus_state,
            post_bus_state=self.bus_state,
        )
        self._oversight_report_this_step = oversight_report

        # --- 5. Per-agent rewards ---
        per_agent_rewards = {}
        for agent_id in range(self.num_agents):
            agent_reward = self._compute_agent_reward(
                agent_id=agent_id,
                base_reward=base_reward,
                safety_report=safety_reports.get(agent_id),
                oversight_report=oversight_report,
                is_blackout=info.is_blackout,
            )
            per_agent_rewards[agent_id] = agent_reward

        team_reward = base_reward.value

        # --- 6. Per-agent partial observations ---
        per_agent_obs = {
            agent_id: self._get_zone_obs(agent_id)
            for agent_id in range(self.num_agents)
        }

        # Propagate blackout to observations
        if info.is_blackout:
            for obs in per_agent_obs.values():
                obs.is_blackout = True

        return MultiAgentStepResult(
            observations=per_agent_obs,
            rewards=per_agent_rewards,
            team_reward=round(team_reward, 4),
            done=done,
            safety_reports=safety_reports,
            oversight_report=oversight_report,
            info=info,
        )

    def get_zone_info(self) -> Dict[int, ZoneInfo]:
        """Get metadata about each agent's zone."""
        zones = {}
        for agent_id in range(self.num_agents):
            zones[agent_id] = ZoneInfo(
                agent_id=agent_id,
                zone_name=self.zone_names[agent_id] if agent_id < len(self.zone_names) else f"Zone_{agent_id}",
                bus_ids=self.zone_bus_ids.get(agent_id, []),
                boundary_line_ids=self.boundary_lines.get(agent_id, []),
                internal_line_ids=self.internal_lines.get(agent_id, []),
            )
        return zones

    # ======================================================================
    # Multi-Agent Reward Computation
    # ======================================================================

    def _compute_agent_reward(
        self,
        agent_id: int,
        base_reward: GridReward,
        safety_report: Optional[SafetyReport],
        oversight_report: OversightReport,
        is_blackout: bool,
    ) -> GridReward:
        """Compute per-agent reward with composable components.

        Components:
        - survival: shared team component (same for all)
        - frequency: shared (all agents affected equally)
        - local_congestion: penalty for overloads in agent's zone
        - safety_compliance: penalty if safety layer corrected the action
        - coordination: penalty from oversight for selfish/conflicting behavior
        - efficiency: small bonus for minimal actions
        """
        components = {}

        # Shared components (from base reward)
        components['survival'] = base_reward.components.get('survival', 1.0)
        components['frequency'] = base_reward.components.get('frequency', 0.0)

        # Global overload shared equally — ensures no line's penalty is lost
        components['overload_shared'] = base_reward.components.get('overload', 0.0) / max(self.num_agents, 1)

        # Local congestion: additional penalty for overloads on lines in agent's zone
        zone_overload = 0.0
        agent_lines = set(self.internal_lines.get(agent_id, []))
        agent_lines.update(self.boundary_lines.get(agent_id, []))
        for l in self.line_state:
            if l['id'] in agent_lines and l['connected']:
                limit = self._get_line_capacity(l['id'])
                rho = abs(l['flow']) / limit if limit > 0 else 0.0
                if rho > 1.0:
                    zone_overload -= (rho - 1.0) ** 2 * 10
                elif rho > 0.8:
                    zone_overload -= 0.05
        components['local_congestion'] = zone_overload

        # Safety compliance penalty
        if safety_report and safety_report.was_corrected:
            components['safety_compliance'] = -0.3 * (
                1 + safety_report.blocked_topology_actions
            )
        else:
            components['safety_compliance'] = 0.1  # Bonus for safe actions

        # Coordination penalty from oversight
        coord_penalty = oversight_report.coordination_penalties.get(agent_id, 0.0)
        components['coordination'] = -coord_penalty

        # Action cost
        components['action_cost'] = base_reward.components.get('action_cost', 0.0) / max(self.num_agents, 1)

        total = sum(components.values())
        return GridReward(value=round(total, 4), components=components)

    # ======================================================================
    # POMDP Observation
    # ======================================================================

    def _get_zone_obs(self, agent_id: int) -> ZoneObservation:
        """Build partial observation for one agent (POMDP).

        Each agent sees:
        - Only buses in their zone
        - Internal + boundary lines
        - Noisy global frequency
        - Limited neighbor signals
        """
        # Local buses
        zone_bus_ids = set(self.zone_bus_ids.get(agent_id, []))
        local_buses = []
        zone_load = 0.0
        zone_gen = 0.0
        for b in self.bus_state:
            if b['id'] in zone_bus_ids:
                b_cfg = self._find_bus_config(b['id'])
                if b_cfg is None:
                    continue
                local_buses.append(BusState(
                    id=b['id'], type=b_cfg['type'],
                    p_injection=round(b['p'], 4),
                    soc=round(b.get('soc', 0.0), 4),
                    ramp_rate=b_cfg.get('ramp_rate', 0.0),
                ))
                if b_cfg['type'] == 'load':
                    zone_load += abs(b['p'])
                elif b_cfg['type'] in ('generator', 'solar', 'wind', 'slack'):
                    zone_gen += b['p']
                # battery: not classified as load or gen

        # Internal lines (within zone)
        int_line_ids = set(self.internal_lines.get(agent_id, []))
        internal_lines = []
        for l in self.line_state:
            if l['id'] in int_line_ids:
                limit = self._get_line_capacity(l['id'])
                rho = abs(l['flow']) / limit if l['connected'] and limit > 0 else 0.0
                # Add noise to line readings
                noisy_rho = rho + self._rng.normal(0, self.LINE_NOISE_STD) if self._rng else rho
                noisy_rho = max(0.0, noisy_rho)
                internal_lines.append(LineStatus(
                    id=l['id'], connected=l['connected'],
                    flow=round(l['flow'], 4),
                    rho=round(noisy_rho, 4),
                ))

        # Boundary lines (connecting to other zones)
        bnd_line_ids = set(self.boundary_lines.get(agent_id, []))
        boundary_lines = []
        for l in self.line_state:
            if l['id'] in bnd_line_ids:
                limit = self._get_line_capacity(l['id'])
                rho = abs(l['flow']) / limit if l['connected'] and limit > 0 else 0.0
                noisy_rho = rho + self._rng.normal(0, self.LINE_NOISE_STD) if self._rng else rho
                noisy_rho = max(0.0, noisy_rho)
                boundary_lines.append(LineStatus(
                    id=l['id'], connected=l['connected'],
                    flow=round(l['flow'], 4),
                    rho=round(noisy_rho, 4),
                ))

        # Noisy frequency (POMDP — agents don't get perfect readings)
        true_freq = self._compute_frequency()
        noisy_freq = true_freq + (self._rng.normal(0, self.FREQ_NOISE_STD) if self._rng else 0.0)

        # Neighbor signals: average bus injection of other zones
        neighbor_signals = {}
        for other_id in range(self.num_agents):
            if other_id == agent_id:
                continue
            other_bus_ids = self.zone_bus_ids.get(other_id, [])
            if other_bus_ids:
                avg_inj = np.mean([
                    b['p'] for b in self.bus_state if b['id'] in other_bus_ids
                ])
                neighbor_signals[other_id] = round(float(avg_inj), 2)

        # Cooldowns for lines this agent can see
        visible_lines = int_line_ids | bnd_line_ids
        visible_cooldowns = {
            k: v for k, v in self.cooldowns.items() if k in visible_lines
        }

        zone_name = self.zone_names[agent_id] if agent_id < len(self.zone_names) else f"Zone_{agent_id}"

        return ZoneObservation(
            agent_id=agent_id,
            zone_name=zone_name,
            timestep=self.timestep,
            grid_frequency=round(noisy_freq, 4),
            local_buses=local_buses,
            boundary_lines=boundary_lines,
            internal_lines=internal_lines,
            neighbor_signals=neighbor_signals,
            cooldowns=visible_cooldowns,
            is_blackout=False,
            zone_load_mw=round(zone_load, 2),
            zone_gen_mw=round(zone_gen, 2),
        )

    # ======================================================================
    # Internal Methods (unchanged from original)
    # ======================================================================

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

        self.slack_injection = slack_inj
        slack_dyn = self._find_bus_state(self.slack_bus_id)
        if slack_dyn is not None:
            slack_dyn['p'] = slack_inj

        for l in self.line_state:
            if l['connected'] and l['id'] in flows:
                l['flow'] = flows[l['id']]
            elif not l['connected']:
                l['flow'] = 0.0

    def _compute_frequency(self) -> float:
        """Frequency proxy using droop model, calibrated to system size."""
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
            is_blackout=getattr(self, '_is_blackout', False)
        )

    # ---------- Lookup Helpers (O(1) indexed + guarded fallbacks) ----------

    def _find_line(self, line_id: str):
        # Use index if available (built in reset), fall back to linear scan
        idx = getattr(self, '_line_state_by_id', None)
        if idx is not None:
            return idx.get(line_id)
        return next((l for l in self.line_state if l['id'] == line_id), None)

    def _find_bus_config(self, bus_id: int):
        return self._bus_cfg_by_id.get(bus_id)

    def _find_bus_state(self, bus_id: int):
        idx = getattr(self, '_bus_state_by_id', None)
        if idx is not None:
            return idx.get(bus_id)
        return next((b for b in self.bus_state if b['id'] == bus_id), None)

    def _get_line_capacity(self, line_id: str) -> float:
        cfg = self._line_cfg_by_id.get(line_id)
        return cfg['capacity'] if cfg else 1.0