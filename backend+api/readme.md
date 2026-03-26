## Features you have right now (this version)

### 1) Mock “Flood Zone” monitoring (the Monitor)
- The app generates **monitoring points** (flood zones) with:
  - `name`, `latitude`, `longitude`
  - `current_water_level`
  - `risk_level` (`low/moderate/high/extreme`)
  - `last_updated`
- These are meant to be the points you show on a map (markers).

### 2) Mock “Traffic Status” tracking (the Command)
- For each flood zone, the app maintains a linked traffic record:
  - `status` (`normal/moderate/heavy/gridlocked/closed`)
  - `avg_delay_minutes`
  - `is_diversion_active`
- The traffic status updates based on the flood risk (more flooding → worse traffic).

### 3) Live simulator (automatic updates)
- A background loop runs every few seconds and **changes water levels**.
- From that it automatically recalculates:
  - flood `risk_level`
  - linked `traffic_status`
- This gives you “real-time feeling” telemetry without real sensors.

### 4) Alerts feed (auto-generated)
- The app builds an **alerts list** from current conditions:
  - Flood alerts when `risk_level` is `high` or `extreme`
  - Traffic alerts when traffic is `gridlocked` or `closed`
- Each alert includes zone name, severity, and a message.

### 5) Citizen Reports (the Grievance)
- You can submit a citizen report via API:
  - `reporter_name`, `category`, `location_text`, `description`
  - `status` defaults to `pending`
- You can list reports, and filter by status.

### 6) Usability features for frontend integration
- **Swagger UI**: you can test everything in the browser at `/docs`.
- **CORS enabled**: so a frontend (Next.js) can call the API without browser blocking.

## Endpoints (what you can actually call)
- `GET /api/health`
- `GET /api/flood-zones` (+ `limit`, `offset`)
- `GET /api/flood-zones/{zone_id}`
- `GET /api/traffic-status/{zone_id}`
- `GET /api/alerts`
- `POST /api/citizen-reports`
- `GET /api/citizen-reports` (optional `status` filter)

## What’s NOT in this version yet (important)
- No ward polygons or readiness score system
- No 2,500+ micro-hotspot GeoJSON generation
- No rainfall scenario input / digital twin flood propagation
- No safe-route routing lines on the map
- No real database persistence when `USE_DB=false` (data resets on restart)
