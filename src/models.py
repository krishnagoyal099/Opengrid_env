from typing import List, Dict, Literal, Optional
from pydantic import BaseModel, Field


class TopologyAction(BaseModel):
    """A topology switching action on a transmission line."""
    line_id: str
    action: Literal["open", "close"]


class BusAdjustment(BaseModel):
    """A power injection adjustment on a bus."""
    bus_id: int
    delta: float  # MW change (positive = inject more)


class GridAction(BaseModel):
    """Agent action: adjust bus injections and/or switch line topology."""
    bus_adjustments: List[BusAdjustment] = []
    topology_actions: List[TopologyAction] = []


class LineStatus(BaseModel):
    """Current state of a transmission line."""
    id: str
    connected: bool
    flow: float = 0.0
    rho: float = Field(0.0, ge=0.0, description="Loading percentage (flow/capacity)")


class BusState(BaseModel):
    """Current state of a bus (generator, load, battery, or renewable)."""
    id: int
    type: Literal["slack", "generator", "load", "battery", "solar", "wind"]
    p_injection: float
    soc: float = Field(0.0, ge=0.0, description="State of charge (MWh)")
    ramp_rate: float = 0.0


class GridObservation(BaseModel):
    """Full grid observation returned by reset()/step()/state()."""
    timestep: int
    grid_frequency: float
    buses: List[BusState]
    lines: List[LineStatus]
    cooldowns: Dict[str, int]
    is_blackout: bool = False

    def __repr__(self) -> str:
        return (
            f"GridObservation(t={self.timestep}, f={self.grid_frequency:.2f}, "
            f"buses={len(self.buses)}, lines={len(self.lines)}, "
            f"blackout={self.is_blackout})"
        )


class GridReward(BaseModel):
    """Reward signal with component breakdown."""
    value: float
    components: Dict[str, float]


class GridInfo(BaseModel):
    """Episode info (metadata alongside reward)."""
    task_id: str
    is_blackout: bool


# ---------------------------------------------------------------------------
# Multi-Agent POMDP Models
# ---------------------------------------------------------------------------

class ZoneInfo(BaseModel):
    """Metadata about an agent's zone."""
    agent_id: int
    zone_name: str
    bus_ids: List[int]
    boundary_line_ids: List[str]
    internal_line_ids: List[str]


class ZoneObservation(BaseModel):
    """Partial observation for one agent under POMDP.

    Each agent sees only:
    - Their local buses (within their zone)
    - Boundary lines (connecting to other zones)
    - Internal lines (within their zone)
    - A noisy estimate of global grid frequency
    - Limited communication signals from neighboring agents
    """
    agent_id: int
    zone_name: str
    timestep: int
    grid_frequency: float  # noisy — Gaussian noise added
    local_buses: List[BusState]
    boundary_lines: List[LineStatus]
    internal_lines: List[LineStatus]
    neighbor_signals: Dict[int, float] = Field(
        default_factory=dict,
        description="Limited info from other agents: {agent_id: their avg bus injection}"
    )
    cooldowns: Dict[str, int] = Field(default_factory=dict)
    is_blackout: bool = False
    zone_load_mw: float = 0.0
    zone_gen_mw: float = 0.0

    def __repr__(self) -> str:
        return (
            f"ZoneObservation(agent={self.agent_id}, zone={self.zone_name}, "
            f"t={self.timestep}, f={self.grid_frequency:.2f}, "
            f"buses={len(self.local_buses)}, blackout={self.is_blackout})"
        )


class SafetyReport(BaseModel):
    """Report from the safety layer about action corrections."""
    agent_id: int
    was_corrected: bool
    correction_reason: str = ""
    n1_violations_detected: int = 0
    proposed_topology_actions: int = 0
    blocked_topology_actions: int = 0
    original_total_delta_mw: float = 0.0
    corrected_total_delta_mw: float = 0.0


class OversightReport(BaseModel):
    """Report from the oversight agent about multi-agent coordination."""
    coordination_score: float = Field(
        1.0, description="1.0 = perfect cooperation, 0.0 = total conflict"
    )
    conflicting_actions_detected: int = 0
    selfish_actions_detected: int = 0
    coordination_penalties: Dict[int, float] = Field(default_factory=dict)
    global_frequency_contribution: Dict[int, float] = Field(
        default_factory=dict,
        description="Each agent's net impact on frequency deviation"
    )
    notes: List[str] = Field(default_factory=list)


class MultiAgentAction(BaseModel):
    """Request body for /step_multi: per-agent actions keyed by agent_id."""
    agent_actions: Dict[int, GridAction] = Field(
        default_factory=dict,
        description="Actions for each agent, keyed by agent_id"
    )


class MultiAgentStepResult(BaseModel):
    """Result of a multi-agent step — per-agent observations, rewards, reports."""
    observations: Dict[int, ZoneObservation]
    rewards: Dict[int, GridReward]
    team_reward: float
    done: bool
    safety_reports: Dict[int, SafetyReport] = Field(
        default_factory=dict,
        description="Per-agent safety reports, keyed by agent_id"
    )
    oversight_report: OversightReport
    info: GridInfo