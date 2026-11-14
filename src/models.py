"""Forecast models, metrics and the time-based train/test split."""
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler, FunctionTransformer

from config import TEST_START
from features import FEATURES, TARGET

LAG_COLS = ["lag_24", "lag_48", "lag_168", "same_hour_mean_7d", "roll_7d_mean"]


# ---------------------------------------------------------------- metrics
def mae(y, p):  return float(np.mean(np.abs(y - p)))
def rmse(y, p): return float(np.sqrt(np.mean((y - p) ** 2)))
def wape(y, p): return float(np.sum(np.abs(y - p)) / np.sum(y))


def score(y, p):
    return {"MAE": mae(y, p), "RMSE": rmse(y, p), "WAPE": wape(y, p)}


# ---------------------------------------------------------------- split
def split(df, test_start=TEST_START):
    """Time-based split. Rows with an unknown target (outage) or without a week of
    history (first 7 days) are dropped. Never a random split: neighbouring hours are
    strongly correlated, so a random split would leak the answer into training."""
    d = df.dropna(subset=[TARGET, "lag_168"]).copy()
    # remaining NaN lags (hours that point back into the outage day) -> station-hour 7-day mean
    for c in LAG_COLS:
        d[c] = d[c].fillna(d["same_hour_mean_7d"]).fillna(0)
    train = d[d["hour_ts"] < test_start]
    test = d[d["hour_ts"] >= test_start]
    return train, test


# ---------------------------------------------------------------- models
def naive_forecast(test):
    """Same hour, same weekday, last week."""
    return test["lag_168"].to_numpy()


def fit_poisson(train):
    cat = ["hour_x_weekend", "dow", "month", "station_code", "is_bank_holiday", "is_school_holiday"]
    num_log = LAG_COLS
    num = ["temperature", "precipitation", "wind_speed", "nb_docks", "lat", "lon"]
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat),
        ("lag", make_pipeline(FunctionTransformer(np.log1p), StandardScaler()), num_log),
        ("num", StandardScaler(), num),
    ])
    model = make_pipeline(pre, PoissonRegressor(alpha=1e-4, max_iter=500))
    model.fit(_poisson_frame(train), train[TARGET])
    return model


def _poisson_frame(d):
    d = d.copy()
    d["hour_x_weekend"] = d["hour"].astype(str) + "_" + d["is_weekend"].astype(str)
    return d


def predict_poisson(model, d):
    return model.predict(_poisson_frame(d))


def fit_random_forest(train, n_estimators=200, seed=42):
    rf = RandomForestRegressor(n_estimators=n_estimators, min_samples_leaf=3, max_features=0.5,
                               n_jobs=-1, random_state=seed)
    rf.fit(train[FEATURES], train[TARGET])
    return rf


LGB_PARAMS = dict(
    objective="poisson", learning_rate=0.05, num_leaves=63, min_data_in_leaf=40,
    feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0,
    verbose=-1, seed=42,
)


def fit_lightgbm(train, valid_weeks=4):
    """Early-stop on the last `valid_weeks` of the training period, then refit on all of it."""
    cut = train["hour_ts"].max() - pd.Timedelta(weeks=valid_weeks)
    tr, va = train[train["hour_ts"] <= cut], train[train["hour_ts"] > cut]
    dtr = lgb.Dataset(tr[FEATURES], tr[TARGET], categorical_feature=["station_code"])
    dva = lgb.Dataset(va[FEATURES], va[TARGET], reference=dtr)
    probe = lgb.train(LGB_PARAMS, dtr, num_boost_round=3000, valid_sets=[dva],
                      callbacks=[lgb.early_stopping(100, verbose=False)])
    best = probe.best_iteration
    full = lgb.Dataset(train[FEATURES], train[TARGET], categorical_feature=["station_code"])
    model = lgb.train(LGB_PARAMS, full, num_boost_round=int(best * 1.1))
    model.best_iteration_probe = best
    return model


# ---------------------------------------------------------------- error analysis
def segment_errors(pred: pd.DataFrame, models) -> pd.DataFrame:
    """WAPE by condition, so we can see *where* each model fails."""
    p = pred.copy()
    segs = {
        "All hours": p.index == p.index,
        "Weekday": p["is_weekend"] == 0,
        "Weekend": p["is_weekend"] == 1,
        "Bank holiday": p["is_bank_holiday"] == 1,
        "Weekday AM peak (07-09)": (p["is_weekend"] == 0) & p["hour"].between(7, 9),
        "Weekday PM peak (16-18)": (p["is_weekend"] == 0) & p["hour"].between(16, 18),
        "Dry hour": p["precipitation"] == 0,
        "Rain > 1 mm/h": p["precipitation"] > 1,
        "Warm (>= 22C)": p["temperature"] >= 22,
        "Cold (<= 6C)": p["temperature"] <= 6,
    }
    rows = []
    for name, m in segs.items():
        sub = p[m]
        r = {"segment": name, "hours": int(m.sum()), "actual_mean": sub[TARGET].mean()}
        for mdl in models:
            r[mdl] = wape(sub[TARGET], sub[mdl])
        rows.append(r)
    return pd.DataFrame(rows)
