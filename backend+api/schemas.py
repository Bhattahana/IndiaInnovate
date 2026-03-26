# backend/schemas.py
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    extreme = "extreme"


class TrafficStatus(str, Enum):
    gridlocked = "gridlocked"
    heavy = "heavy"
    moderate = "moderate"
    normal = "normal"
    closed = "closed"


class CitizenReportStatus(str, Enum):
    pending = "pending"
    reviewed = "reviewed"
    resolved = "resolved"


class FloodZoneBase(BaseModel):
    name: str
    latitude: float
    longitude: float
    risk_level: RiskLevel
    current_water_level: float
    last_updated: datetime


class FloodZoneCreate(FloodZoneBase):
    pass


class FloodZoneRead(FloodZoneBase):
    id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class TrafficStatusRowBase(BaseModel):
    zone_id: uuid.UUID
    status: TrafficStatus
    avg_delay_minutes: int | None = None
    is_diversion_active: bool = False


class TrafficStatusRowCreate(TrafficStatusRowBase):
    pass


class TrafficStatusRowRead(TrafficStatusRowBase):
    id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class CitizenReportBase(BaseModel):
    reporter_name: str
    category: str = Field(..., description="waterlogging, power_outage, traffic")
    location_text: str | None = None
    description: str
    # Default to "pending" so the frontend doesn't need to send status explicitly.
    status: CitizenReportStatus = CitizenReportStatus.pending


class CitizenReportCreate(CitizenReportBase):
    pass


class CitizenReportRead(CitizenReportBase):
    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)