# train_model.py

import pandas as pd
import numpy as np
import lightgbm as lgb
import joblib

from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

np.random.seed(42)

data_size = 4000

# -----------------------------
# Generate dataset
# -----------------------------
data = pd.DataFrame({
    "rainfall": np.random.randint(0, 300, data_size),
    "future_rainfall": np.random.randint(0, 200, data_size),
    "elevation": np.random.randint(1, 30, data_size),
    "drainage_capacity": np.random.randint(20, 100, data_size),
    "vendor_density": np.random.randint(1, 4, data_size),
    "days_uncollected": np.random.randint(0, 7, data_size),
})

# -----------------------------
# Feature Engineering 🔥
# -----------------------------
data["rain_drain_ratio"] = data["rainfall"] / (data["drainage_capacity"] + 1)
data["waste_pressure"] = data["vendor_density"] * data["days_uncollected"]
data["rain_intensity"] = data["rainfall"] + data["future_rainfall"]

# -----------------------------
# Target (domain logic)
# -----------------------------
data["blockage_prob"] = (
    0.4 * np.sqrt(data["rain_intensity"]) * 10 +
    20 * data["vendor_density"] +
    18 * data["days_uncollected"] -
    0.9 * data["drainage_capacity"] -
    1.5 * data["elevation"]
)

# -----------------------------
# Add noise
# -----------------------------
noise = np.random.normal(0, 10, data_size)
data["blockage_prob"] += noise
data["blockage_prob"] = np.clip(data["blockage_prob"], 0, 100)

# -----------------------------
# Features / target
# -----------------------------
X = data.drop("blockage_prob", axis=1)
y = data["blockage_prob"]

# -----------------------------
# Train/Test split
# -----------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# -----------------------------
# Train model
# -----------------------------
model = lgb.LGBMRegressor(
    n_estimators=400,
    learning_rate=0.03,
    max_depth=8,
    num_leaves=60
)

model.fit(X_train, y_train)

# -----------------------------
# Predictions
# -----------------------------
train_preds = model.predict(X_train)
test_preds = model.predict(X_test)

train_rmse = np.sqrt(mean_squared_error(y_train, train_preds))
test_rmse = np.sqrt(mean_squared_error(y_test, test_preds))

print(f"✅ Train RMSE: {train_rmse:.2f}")
print(f"✅ Test RMSE: {test_rmse:.2f}")

# -----------------------------
# Feature Importance
# -----------------------------
importance = pd.DataFrame({
    "feature": X.columns,
    "importance": model.feature_importances_
}).sort_values(by="importance", ascending=False)

print("\n🔥 Feature Importance:")
print(importance)

# -----------------------------
# SAVE MODEL (VERY IMPORTANT)
# -----------------------------
joblib.dump({
    "model": model,
    "features": X.columns.tolist()
}, "flood_model.pkl")

print("\n✅ Model saved successfully")
