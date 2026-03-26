import os
import random
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import Base, SessionLocal, engine
from models import CitizenReport, CitizenReportStatus, FloodZone, RiskLevel, TrafficStatus, TrafficStatusRow
from schemas import (
    CitizenReportCreate,
    CitizenReportRead,
    FloodZoneRead,
    TrafficStatusRowRead,
)

def _env_truthy(name: str, default: str = "true") -> bool:
    val = os.getenv(name, default).strip().lower()
    return val not in {"0", "false", "no", "off"}


# If Postgres isn't available on the machine, set `USE_DB=false` and the API
# will run using an in-memory mock store.
USE_DB = _env_truthy("USE_DB", "true")

# ---- In-memory mock store (used when USE_DB=false) ----
_MEMORY_LOCK = threading.Lock()
_MEM_ZONES: dict[UUID, dict] = {}
_MEM_TRAFFIC: dict[UUID, dict] = {}
_MEM_CITIZEN_REPORTS: list[dict] = []


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def risk_from_water_level(water_level: float) -> RiskLevel:
    # Mock thresholds; tweak later with real calibration.
    if water_level < 1.0:
        return RiskLevel.low
    if water_level < 2.0:
        return RiskLevel.moderate
    if water_level < 3.0:
        return RiskLevel.high
    return RiskLevel.extreme


def traffic_from_risk(risk: RiskLevel) -> TrafficStatus:
    # Mock mapping from flood risk to traffic impact.
    if risk == RiskLevel.low:
        return TrafficStatus.normal
    if risk == RiskLevel.moderate:
        return random.choice([TrafficStatus.moderate, TrafficStatus.heavy])
    if risk == RiskLevel.high:
        return TrafficStatus.gridlocked
    return TrafficStatus.closed


def ensure_seed_data(db: Session, zone_count: int) -> None:
    existing = db.query(FloodZone).count()
    if existing > 0:
        return

    # Mock city center (swap with your city bounding box later).
    center_lat = float(os.getenv("CITY_CENTER_LAT", "28.6139"))  # Delhi-ish
    center_lon = float(os.getenv("CITY_CENTER_LON", "77.2090"))
    lat_spread = float(os.getenv("CITY_LAT_SPREAD", "0.08"))
    lon_spread = float(os.getenv("CITY_LON_SPREAD", "0.08"))

    now = datetime.now(timezone.utc)

    zones: list[FloodZone] = []
    traffic_rows: list[TrafficStatusRow] = []

    for i in range(zone_count):
        zone_name = f"Monitoring Point {i + 1}"
        lat = center_lat + random.uniform(-lat_spread, lat_spread)
        lon = center_lon + random.uniform(-lon_spread, lon_spread)

        water_level = max(0.0, random.uniform(0.2, 3.6))
        risk = risk_from_water_level(water_level)
        traffic_status = traffic_from_risk(risk)

        zone = FloodZone(
            name=zone_name,
            latitude=lat,
            longitude=lon,
            risk_level=risk,
            current_water_level=water_level,
            last_updated=now,
        )
        zones.append(zone)

        # One traffic row per zone (mock).
        delay = None
        is_diversion = False
        if traffic_status in (TrafficStatus.moderate, TrafficStatus.heavy):
            delay = random.randint(5, 25)
        elif traffic_status == TrafficStatus.gridlocked:
            delay = random.randint(20, 60)
            is_diversion = True
        elif traffic_status == TrafficStatus.closed:
            delay = random.randint(40, 120)
            is_diversion = True

        traffic_rows.append(
            TrafficStatusRow(
                zone=zone,
                status=traffic_status,
                avg_delay_minutes=delay,
                is_diversion_active=is_diversion,
            )
        )

    db.add_all(zones)
    db.add_all(traffic_rows)
    db.commit()


def ensure_seed_data_memory(zone_count: int) -> None:
    """Seed in-memory data so the API can run without Postgres."""
    with _MEMORY_LOCK:
        if len(_MEM_ZONES) > 0:
            return

        # Mock city center (swap with your city bounding box later).
        center_lat = float(os.getenv("CITY_CENTER_LAT", "28.6139"))  # Delhi-ish
        center_lon = float(os.getenv("CITY_CENTER_LON", "77.2090"))
        lat_spread = float(os.getenv("CITY_LAT_SPREAD", "0.08"))
        lon_spread = float(os.getenv("CITY_LON_SPREAD", "0.08"))

        now = datetime.now(timezone.utc)

        for i in range(zone_count):
            zone_id = uuid4()
            zone_name = f"Monitoring Point {i + 1}"
            lat = center_lat + random.uniform(-lat_spread, lat_spread)
            lon = center_lon + random.uniform(-lon_spread, lon_spread)

            water_level = max(0.0, random.uniform(0.2, 3.6))
            risk = risk_from_water_level(water_level)
            traffic_status = traffic_from_risk(risk)

            _MEM_ZONES[zone_id] = {
                "id": zone_id,
                "name": zone_name,
                "latitude": lat,
                "longitude": lon,
                "risk_level": risk.value,
                "current_water_level": water_level,
                "last_updated": now,
            }

            delay: int | None = None
            is_diversion = False
            if traffic_status in (TrafficStatus.moderate, TrafficStatus.heavy):
                delay = random.randint(5, 25)
            elif traffic_status == TrafficStatus.gridlocked:
                delay = random.randint(20, 60)
                is_diversion = True
            elif traffic_status == TrafficStatus.closed:
                delay = random.randint(40, 120)
                is_diversion = True

            _MEM_TRAFFIC[zone_id] = {
                "id": uuid4(),
                "zone_id": zone_id,
                "status": traffic_status.value,
                "avg_delay_minutes": delay,
                "is_diversion_active": is_diversion,
            }


def mock_update_memory_loop(stop_event: threading.Event, interval_seconds: float) -> None:
    while not stop_event.is_set():
        with _MEMORY_LOCK:
            for zone_id, zone in _MEM_ZONES.items():
                # Gentle drift + noise to simulate telemetry changes.
                delta = random.uniform(-0.25, 0.45)
                zone["current_water_level"] = max(0.0, float(zone["current_water_level"]) + delta)

                new_risk = risk_from_water_level(zone["current_water_level"])
                zone["risk_level"] = new_risk.value
                zone["last_updated"] = datetime.now(timezone.utc)

                tr = _MEM_TRAFFIC.get(zone_id)
                if tr is None:
                    tr = {"id": uuid4(), "zone_id": zone_id}
                    _MEM_TRAFFIC[zone_id] = tr

                new_traffic = traffic_from_risk(new_risk)
                tr["status"] = new_traffic.value
                tr["is_diversion_active"] = new_traffic in (TrafficStatus.gridlocked, TrafficStatus.closed)

                if new_traffic in (TrafficStatus.moderate, TrafficStatus.heavy):
                    tr["avg_delay_minutes"] = random.randint(5, 25)
                elif new_traffic == TrafficStatus.gridlocked:
                    tr["avg_delay_minutes"] = random.randint(20, 60)
                elif new_traffic == TrafficStatus.closed:
                    tr["avg_delay_minutes"] = random.randint(40, 120)
                else:
                    tr["avg_delay_minutes"] = random.randint(0, 3)

        stop_event.wait(interval_seconds)


def mock_update_loop(stop_event: threading.Event, interval_seconds: float) -> None:
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            zones = db.query(FloodZone).all()
            for zone in zones:
                # Gentle drift + noise to simulate telemetry changes.
                delta = random.uniform(-0.25, 0.45)
                zone.current_water_level = max(0.0, float(zone.current_water_level) + delta)

                new_risk = risk_from_water_level(zone.current_water_level)
                zone.risk_level = new_risk
                zone.last_updated = datetime.now(timezone.utc)

                tr = db.query(TrafficStatusRow).filter(TrafficStatusRow.zone_id == zone.id).one_or_none()
                if tr is None:
                    tr = TrafficStatusRow(zone_id=zone.id)
                    db.add(tr)

                tr.status = traffic_from_risk(new_risk)
                tr.is_diversion_active = tr.status in (TrafficStatus.gridlocked, TrafficStatus.closed)

                if tr.status in (TrafficStatus.moderate, TrafficStatus.heavy):
                    tr.avg_delay_minutes = random.randint(5, 25)
                elif tr.status == TrafficStatus.gridlocked:
                    tr.avg_delay_minutes = random.randint(20, 60)
                elif tr.status == TrafficStatus.closed:
                    tr.avg_delay_minutes = random.randint(40, 120)
                else:
                    tr.avg_delay_minutes = random.randint(0, 3)

            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

        stop_event.wait(interval_seconds)


class AlertRead(BaseModel):
    type: str  # "flood" | "traffic"
    severity: str  # "warning" | "critical" | "extreme"
    zone_id: UUID
    zone_name: str
    message: str
    updated_at: datetime


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_zones = int(os.getenv("SEED_ZONE_COUNT", "30"))
    seed_interval = float(os.getenv("MOCK_SIM_INTERVAL_SECONDS", "5"))

    stop_event = threading.Event()
    if USE_DB:
        Base.metadata.create_all(bind=engine)

        db = SessionLocal()
        try:
            ensure_seed_data(db, zone_count=seed_zones)
        finally:
            db.close()

        thread = threading.Thread(
            target=mock_update_loop,
            args=(stop_event, seed_interval),
            daemon=True,
        )
    else:
        ensure_seed_data_memory(zone_count=seed_zones)
        thread = threading.Thread(
            target=mock_update_memory_loop,
            args=(stop_event, seed_interval),
            daemon=True,
        )

    thread.start()
    yield
    stop_event.set()


app = FastAPI(title="Urban Flood Mock Data API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/flood-zones", response_model=list[FloodZoneRead])
def list_flood_zones(
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    if USE_DB:
        db = SessionLocal()
        try:
            zones = (
                db.query(FloodZone)
                .order_by(FloodZone.last_updated.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return zones
        finally:
            db.close()

    with _MEMORY_LOCK:
        all_zones = list(_MEM_ZONES.values())
        # Sort newest first for the API response ordering.
        all_zones.sort(key=lambda z: z["last_updated"], reverse=True)
        sliced = all_zones[offset : offset + limit]
        return [FloodZoneRead(**z) for z in sliced]


@app.get("/api/flood-zones/{zone_id}", response_model=FloodZoneRead)
def get_flood_zone(zone_id: UUID):
    if USE_DB:
        db = SessionLocal()
        try:
            zone = db.query(FloodZone).filter(FloodZone.id == zone_id).one_or_none()
            if zone is None:
                raise HTTPException(status_code=404, detail="Flood zone not found")
            return zone
        finally:
            db.close()

    with _MEMORY_LOCK:
        zone = _MEM_ZONES.get(zone_id)
        if zone is None:
            raise HTTPException(status_code=404, detail="Flood zone not found")
        return FloodZoneRead(**zone)


@app.get("/api/traffic-status/{zone_id}", response_model=TrafficStatusRowRead)
def get_traffic_status(zone_id: UUID):
    if USE_DB:
        db = SessionLocal()
        try:
            tr = db.query(TrafficStatusRow).filter(TrafficStatusRow.zone_id == zone_id).one_or_none()
            if tr is None:
                raise HTTPException(status_code=404, detail="Traffic status not found for zone")
            return tr
        finally:
            db.close()

    with _MEMORY_LOCK:
        tr = _MEM_TRAFFIC.get(zone_id)
        if tr is None:
            raise HTTPException(status_code=404, detail="Traffic status not found for zone")
        return TrafficStatusRowRead(**tr)


@app.post("/api/citizen-reports", response_model=CitizenReportRead)
def create_citizen_report(payload: CitizenReportCreate):
    if USE_DB:
        db = SessionLocal()
        try:
            report = CitizenReport(
                reporter_name=payload.reporter_name,
                category=payload.category,
                location_text=payload.location_text,
                description=payload.description,
                status=payload.status,
            )
            db.add(report)
            db.commit()
            db.refresh(report)
            return report
        finally:
            db.close()

    # In-memory mode
    with _MEMORY_LOCK:
        report_id = uuid4()
        now = datetime.now(timezone.utc)
        report = {
            "id": report_id,
            "reporter_name": payload.reporter_name,
            "category": payload.category,
            "location_text": payload.location_text,
            "description": payload.description,
            "status": payload.status.value if hasattr(payload.status, "value") else payload.status,
            "created_at": now,
        }
        _MEM_CITIZEN_REPORTS.append(report)
        return CitizenReportRead(**report)


@app.get("/api/citizen-reports", response_model=list[CitizenReportRead])
def list_citizen_reports(
    status: Optional[CitizenReportStatus] = None,
):
    if USE_DB:
        db = SessionLocal()
        try:
            q = db.query(CitizenReport)
            if status is not None:
                q = q.filter(CitizenReport.status == status)
            return q.order_by(CitizenReport.created_at.desc()).all()
        finally:
            db.close()

    with _MEMORY_LOCK:
        reports = list(_MEM_CITIZEN_REPORTS)
        if status is not None:
            status_value = status.value if hasattr(status, "value") else status
            reports = [r for r in reports if r.get("status") == status_value]
        reports.sort(key=lambda r: r["created_at"], reverse=True)
        return [CitizenReportRead(**r) for r in reports]


@app.get("/api/alerts", response_model=list[AlertRead])
def get_alerts():
    results: list[AlertRead] = []

    if USE_DB:
        db = SessionLocal()
        try:
            zones = db.query(FloodZone).all()
            for zone in zones:
                # Flood alerts
                if zone.risk_level in (RiskLevel.high, RiskLevel.extreme):
                    severity = "critical" if zone.risk_level == RiskLevel.high else "extreme"
                    results.append(
                        AlertRead(
                            type="flood",
                            severity=severity,
                            zone_id=zone.id,
                            zone_name=zone.name,
                            message=f"{severity.upper()}: {zone.name} water level {zone.current_water_level:.2f}m",
                            updated_at=zone.last_updated,
                        )
                    )

                # Traffic alerts
                tr = db.query(TrafficStatusRow).filter(TrafficStatusRow.zone_id == zone.id).one_or_none()
                if tr is not None and tr.status in (TrafficStatus.gridlocked, TrafficStatus.closed):
                    severity = "critical" if tr.status == TrafficStatus.gridlocked else "extreme"
                    results.append(
                        AlertRead(
                            type="traffic",
                            severity=severity,
                            zone_id=zone.id,
                            zone_name=zone.name,
                            message=f"{severity.upper()}: Traffic {tr.status.value} (avg delay {tr.avg_delay_minutes} min)",
                            updated_at=zone.last_updated,
                        )
                    )
        finally:
            db.close()
    else:
        with _MEMORY_LOCK:
            for zone_id, zone in _MEM_ZONES.items():
                risk_level = zone["risk_level"]
                # In-memory uses string risk_level.
                if risk_level in (RiskLevel.high.value, RiskLevel.extreme.value):
                    severity = "critical" if risk_level == RiskLevel.high.value else "extreme"
                    results.append(
                        AlertRead(
                            type="flood",
                            severity=severity,
                            zone_id=zone_id,
                            zone_name=zone["name"],
                            message=f"{severity.upper()}: {zone['name']} water level {zone['current_water_level']:.2f}m",
                            updated_at=zone["last_updated"],
                        )
                    )

                tr = _MEM_TRAFFIC.get(zone_id)
                if tr is not None:
                    status_value = tr.get("status")
                    if status_value in (TrafficStatus.gridlocked.value, TrafficStatus.closed.value):
                        severity = "critical" if status_value == TrafficStatus.gridlocked.value else "extreme"
                        results.append(
                            AlertRead(
                                type="traffic",
                                severity=severity,
                                zone_id=zone_id,
                                zone_name=zone["name"],
                                message=f"{severity.upper()}: Traffic {status_value} (avg delay {tr.get('avg_delay_minutes')} min)",
                                updated_at=zone["last_updated"],
                            )
                        )

    results.sort(key=lambda a: a.updated_at, reverse=True)
    return results

