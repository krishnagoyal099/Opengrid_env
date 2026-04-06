from typing import List, Dict, Literal
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
    rho: float = Field(0.0, description="Loading percentage (flow/capacity)")


class BusState(BaseModel):
    """Current state of a bus (generator, load, battery, or renewable)."""
    id: int
    type: Literal["slack", "generator", "load", "battery", "solar", "wind"]
    p_injection: float
    soc: float = 0.0
    ramp_rate: float = 0.0


class GridObservation(BaseModel):
    """Full grid observation returned by reset()/step()/state()."""
    timestep: int
    grid_frequency: float
    buses: List[BusState]
    lines: List[LineStatus]
    cooldowns: Dict[str, int]
    is_blackout: bool = False


class GridReward(BaseModel):
    """Reward signal with component breakdown."""
    value: float
    components: Dict[str, float]


class GridInfo(BaseModel):
    """Episode info (metadata alongside reward)."""
    task_id: str
    is_blackout: bool
    n1_survival: bool = True