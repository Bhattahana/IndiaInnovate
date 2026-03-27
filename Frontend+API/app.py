# app.py

from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import numpy as np

app = FastAPI(title="AquaShield AI API")

saved = joblib.load("flood_model.pkl")
model = saved["model"]

# -----------------------------
# Input schema
# -----------------------------
class PredictionInput(BaseModel):
    rainfall: float
    future_rainfall: float
    elevation: float
    drainage_capacity: float
    vendor_density: int
    days_uncollected: int


@app.get("/")
def home():
    return {"status": "AquaShield AI running 🚀"}


@app.post("/predict")
def predict(data: PredictionInput):

    # --- Feature engineering (must match training) ---
    rain_drain_ratio = data.rainfall / (data.drainage_capacity + 1)
    waste_pressure = data.vendor_density * data.days_uncollected
    rain_intensity = data.rainfall + data.future_rainfall

    features = np.array([[ 
        data.rainfall,
        data.future_rainfall,
        data.elevation,
        data.drainage_capacity,
        data.vendor_density,
        data.days_uncollected,
        rain_drain_ratio,
        waste_pressure,
        rain_intensity
    ]])

    prediction = model.predict(features)[0]
    prob = float(np.clip(prediction, 0, 100))

    # -----------------------------
    # Risk classification
    # -----------------------------
    if prob > 80:
        status = "Extreme"
    elif prob > 60:
        status = "High"
    elif prob > 30:
        status = "Moderate"
    else:
        status = "Low"

    # -----------------------------
    # Explainability (simple but powerful)
    # -----------------------------
    reasons = []

    if waste_pressure > 6:
        reasons.append("High waste accumulation pressure")

    if rain_intensity > 120:
        reasons.append("Heavy rainfall intensity")

    if data.drainage_capacity < 40:
        reasons.append("Low drainage capacity")

    if data.elevation < 10:
        reasons.append("Low elevation area")

    return {
        "blockage_probability": round(prob, 2),
        "risk_level": status,
        "reasons": reasons
    }
