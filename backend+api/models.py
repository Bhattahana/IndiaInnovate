# backend/models.py
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class RiskLevel(str, enum.Enum):
    low = "low"
    moderate = "moderate"
    high = "high"
    extreme = "extreme"


class TrafficStatus(str, enum.Enum):
    gridlocked = "gridlocked"
    heavy = "heavy"
    moderate = "moderate"
    normal = "normal"
    closed = "closed"


class CitizenReportStatus(str, enum.Enum):
    pending = "pending"
    reviewed = "reviewed"
    resolved = "resolved"


class FloodZone(Base):
    __tablename__ = "flood_zones"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Stored as lat/lon for now; later you can migrate to PostGIS geometry.
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    risk_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel, name="risk_level"), nullable=False)
    current_water_level: Mapped[float] = mapped_column(Float, nullable=False)

    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    traffic: Mapped[list["TrafficStatusRow"]] = relationship(
        "TrafficStatusRow",
        back_populates="zone",
        cascade="all, delete-orphan",
    )


class TrafficStatusRow(Base):
    __tablename__ = "traffic_status"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("flood_zones.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[TrafficStatus] = mapped_column(SAEnum(TrafficStatus, name="traffic_status_enum"), nullable=False)
    avg_delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_diversion_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    zone: Mapped["FloodZone"] = relationship(back_populates="traffic")

    # If you want exactly one traffic status row per zone, uncomment this:
    # __table_args__ = (UniqueConstraint("zone_id", name="uq_traffic_status_zone_id"),)


class CitizenReport(Base):
    __tablename__ = "citizen_reports"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_name: Mapped[str] = mapped_column(String(255), nullable=False)

    category: Mapped[str] = mapped_column(String(100), nullable=False)  # waterlogging, power_outage, traffic
    location_text: Mapped[str] = mapped_column(String(500), nullable=True)  # user-entered landmark

    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[CitizenReportStatus] = mapped_column(
        SAEnum(CitizenReportStatus, name="citizen_report_status_enum"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)