"""Turn hourly forecasts into rebalancing decisions and an (explicitly assumption-based) impact estimate.

Vocabulary
- net drain   = departures - arrivals over a window. Positive = the station loses bikes.
- drain ratio = net drain / dock capacity. 1.0 means the window would empty a full station.
"""
import numpy as np
import pandas as pd

WINDOWS = {  # name: (first hour, last hour inclusive)
    "Early (05-06)": (5, 6),
    "AM peak (07-09)": (7, 9),
    "Midday (10-15)": (10, 15),
    "PM peak (16-18)": (16, 18),
    "Evening (19-23)": (19, 23),
}


def assign_window(hour: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=hour.index, dtype="object")
    for name, (a, b) in WINDOWS.items():
        out[hour.between(a, b)] = name
    return out


def expected_arrivals(train: pd.DataFrame, weeks=8) -> pd.DataFrame:
    """Arrivals are not forecast by the model; use the recent typical profile
    (mean over the last `weeks` of training) per station x weekday/weekend x hour."""
    recent = train[train["hour_ts"] > train["hour_ts"].max() - pd.Timedelta(weeks=weeks)]
    return (recent.groupby(["station_id", "is_weekend", "hour"])["arrivals"].mean()
                  .rename("arrivals_expected").reset_index())


def risk_table(pred: pd.DataFrame, arrivals_exp: pd.DataFrame, forecast_col="lightgbm") -> pd.DataFrame:
    """Average daily forecast departures, expected arrivals and drain ratio per station x window x day type."""
    p = pred.merge(arrivals_exp, on=["station_id", "is_weekend", "hour"], how="left")
    p["window"] = assign_window(p["hour"])
    p = p.dropna(subset=["window"])
    n_days = p.groupby("is_weekend")["date"].nunique().rename("n_days")
    agg = (p.groupby(["station_id", "display_name", "nb_docks", "is_weekend", "window"])
             .agg(forecast_departures=(forecast_col, "sum"),
                  actual_departures=("departures", "sum"),
                  expected_arrivals=("arrivals_expected", "sum"),
                  peak_hour_forecast=(forecast_col, "max"))
             .reset_index().merge(n_days, on="is_weekend"))
    for c in ("forecast_departures", "actual_departures", "expected_arrivals"):
        agg[c] = agg[c] / agg["n_days"]
    agg["net_drain"] = agg["forecast_departures"] - agg["expected_arrivals"]
    agg["drain_ratio"] = agg["net_drain"] / agg["nb_docks"]
    agg["demand_to_capacity"] = agg["forecast_departures"] / agg["nb_docks"]
    agg["day_type"] = np.where(agg["is_weekend"] == 1, "Weekend", "Weekday")
    agg["risk_empty"] = pd.cut(agg["drain_ratio"], [-np.inf, 0.25, 0.5, 1.0, np.inf],
                               labels=["Low", "Moderate", "High", "Very high"])
    agg["risk_full"] = pd.cut(-agg["drain_ratio"], [-np.inf, 0.25, 0.5, 1.0, np.inf],
                              labels=["Low", "Moderate", "High", "Very high"])
    return agg.drop(columns="n_days").sort_values("drain_ratio", ascending=False)


# ---------------------------------------------------------------- impact simulation
def simulate_window(dep, arr, docks, start_stock):
    """Hour-by-hour stock simulation for one station on one day.

    Bikes available in an hour = stock at the start of the hour + that hour's arrivals
    (assumes arrivals land early enough to be re-hired: optimistic, so unmet trips are a
    lower bound). Returns (unmet departures, blocked arrivals)."""
    stock, unmet, blocked = start_stock, 0.0, 0.0
    for d, a in zip(dep, arr):
        s = stock + a - d
        if s < 0:
            unmet += -s; s = 0
        if s > docks:
            blocked += s - docks; s = docks
        stock = s
    return unmet, blocked


def simulate_refill(pred: pd.DataFrame, forecast_col: str, n_refill=10, start_fill=0.5,
                    refill_to=0.9, hours=(6, 9), days="weekday") -> pd.DataFrame:
    """For each day in `pred` of the chosen type:
      1. Rank stations by *forecast* net drain / capacity over `hours` (using `forecast_col`), pick top n.
      2. Simulate the window with ACTUAL departures and arrivals:
         - baseline: every station starts at `start_fill` of capacity, no van visits
         - scenario: the selected n stations are topped up to `refill_to` just before the window
      Return per-day unmet trips for both cases.
    The forecast decides *which* stations get the van; actual demand decides what happens.
    days: "weekday" = Mon-Fri excluding bank holidays; "weekend" = Sat/Sun plus bank holidays."""
    a, b = hours
    if days == "weekday":
        mask = (pred["is_weekend"] == 0) & (pred["is_bank_holiday"] == 0)
    else:
        mask = (pred["is_weekend"] == 1) | (pred["is_bank_holiday"] == 1)
    p = pred[mask & pred["hour"].between(a, b)].sort_values(["date", "station_id", "hour"])
    out = []
    for date, day in p.groupby("date"):
        st = day.groupby("station_id").agg(
            docks=("nb_docks", "first"),
            fc_dep=(forecast_col, "sum"), arr_exp=("arrivals_expected", "sum"))
        st["fc_ratio"] = (st["fc_dep"] - st["arr_exp"]) / st["docks"]
        chosen = set(st.nlargest(n_refill, "fc_ratio").index)
        base_unmet = scen_unmet = 0.0
        for sid, s in day.groupby("station_id"):
            docks = s["nb_docks"].iloc[0]
            dep, arr = s["departures"].to_numpy(), s["arrivals"].to_numpy()
            u0, _ = simulate_window(dep, arr, docks, start_fill * docks)
            start = max(start_fill, refill_to) * docks if sid in chosen else start_fill * docks
            u1, _ = simulate_window(dep, arr, docks, start)
            base_unmet += u0; scen_unmet += u1
        out.append({"date": date, "chosen": sorted(chosen), "unmet_no_van": base_unmet,
                    "unmet_with_van": scen_unmet, "trips_recovered": base_unmet - scen_unmet})
    return pd.DataFrame(out)


def simulate_am_refill(pred, forecast_col, **kw):
    """Weekday pre-AM-peak top-up (06:00-09:59)."""
    return simulate_refill(pred, forecast_col, hours=(6, 9), days="weekday", **kw)
