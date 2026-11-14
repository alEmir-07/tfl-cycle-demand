# Power BI dashboard

Three pages: **Demand patterns**, **Forecast vs actual** and **Rebalancing plan**.

> **Status:** the data model, measures and page specs below are complete, and every CSV is produced by
> `notebooks/04_rebalancing.ipynb`. The `.pbix` file itself must be built in **Power BI Desktop, which is
> Windows-only**. On a Mac, use a Windows VM (Parallels/UTM) or upload the CSVs to the Power BI web service
> (app.powerbi.com → *Create* → *Paste or manually enter data* / *Upload*). Save the finished file here as
> `tfl_cycle_demand.pbix` and add screenshots as `page1_demand.png`, `page2_forecast.png` and `page3_rebalancing.png`.

## 1. Load the data (`dashboard/data/`)

| File | Grain | Rows | Role |
|---|---|---|---|
| `dim_station.csv` | station | 40 | dimension: name, type, docks, lat/lon, profile shares |
| `fact_demand_hourly.csv` | station × hour, Jun 2025 - May 2026 | ~350k | actual departures/arrivals + weather + calendar |
| `fact_forecast_vs_actual.csv` | station × hour, Apr-May 2026 | ~58k | actual vs naive / Poisson / RF / LightGBM |
| `rebalancing_recommendations.csv` | station × day type × window | 400 | forecast drain, risk levels, recommended action |
| `model_metrics.csv` | model | 4 | MAE / RMSE / WAPE, hourly and planning level |
| `impact_estimate.csv` | selector × starting fill | 15 | simulated trips served per week |

**Power Query steps**
* Set `station_id` to **Text** in every table. The leading zeros matter (`001072`).
* Set `hour_ts` to Date/Time and `date` to Date.
* Add a `dim_date` table (DAX below) and relate it to `date` in both fact tables.

**Relationships (single direction, one-to-many)**
`dim_station[station_id]` → `fact_demand_hourly`, `fact_forecast_vs_actual`, `rebalancing_recommendations`
`dim_date[date]` → `fact_demand_hourly[date]`, `fact_forecast_vs_actual[date]`

```DAX
dim_date =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2025, 6, 1 ), DATE ( 2026, 5, 31 ) ),
    "Month", FORMAT ( [Date], "mmm yy" ),
    "MonthSort", YEAR ( [Date] ) * 100 + MONTH ( [Date] ),
    "Weekday", FORMAT ( [Date], "ddd" ),
    "WeekdaySort", WEEKDAY ( [Date], 2 ),
    "Day type", IF ( WEEKDAY ( [Date], 2 ) >= 6, "Weekend", "Weekday" )
)
```

## 2. Measures

```DAX
Departures            = SUM ( fact_demand_hourly[departures] )
Arrivals              = SUM ( fact_demand_hourly[arrivals] )
Net flow              = [Arrivals] - [Departures]
Days                  = DISTINCTCOUNT ( fact_demand_hourly[date] )
Departures per day    = DIVIDE ( [Departures], [Days] )
Rain share of hours   = DIVIDE ( CALCULATE ( COUNTROWS ( fact_demand_hourly ), fact_demand_hourly[precipitation] > 0 ),
                                 COUNTROWS ( fact_demand_hourly ) )

-- Forecast page
Actual (test)         = SUM ( fact_forecast_vs_actual[departures] )
Forecast LightGBM     = SUM ( fact_forecast_vs_actual[lightgbm] )
Forecast naive        = SUM ( fact_forecast_vs_actual[naive] )
Abs error LightGBM    = SUMX ( fact_forecast_vs_actual, ABS ( fact_forecast_vs_actual[lightgbm] - fact_forecast_vs_actual[departures] ) )
Abs error naive       = SUMX ( fact_forecast_vs_actual, ABS ( fact_forecast_vs_actual[naive] - fact_forecast_vs_actual[departures] ) )
WAPE LightGBM         = DIVIDE ( [Abs error LightGBM], [Actual (test)] )
WAPE naive            = DIVIDE ( [Abs error naive], [Actual (test)] )
Error reduction vs naive = 1 - DIVIDE ( [WAPE LightGBM], [WAPE naive] )
Bias LightGBM         = DIVIDE ( [Forecast LightGBM] - [Actual (test)], [Actual (test)] )

-- Rebalancing page
Stations needing refill = CALCULATE ( DISTINCTCOUNT ( rebalancing_recommendations[station_id] ),
                                      rebalancing_recommendations[drain_ratio] > 0.5 )
Bikes to move           = SUM ( rebalancing_recommendations[bikes_to_move] )
Trips served per week (LightGBM, 50% fill) =
    CALCULATE ( SUM ( impact_estimate[trips_served_per_week] ),
                impact_estimate[selector] = "LightGBM", impact_estimate[start_fill] = 0.5 )
```

**Sort-by columns:** sort `window` by its start hour. Add a calculated column: `WindowSort = VALUE ( MID ( [window], SEARCH ( "(", [window] ) + 1, 2 ) )`.

## 3. Page specs

### Page 1: Demand patterns
*Question: when and where does demand happen?*
* **Slicers (top row):** date range, station type, station.
* **KPI cards:** Departures per day · busiest station · weekday AM-peak share · rain share of hours.
* **Line chart:** `Departures per day` by `hour` with legend = `dim_date[Day type]`. Shows the two weekday commuter peaks against the single weekend hump.
* **Column chart:** `Departures per day` by `dim_date[Month]` (seasonality).
* **Map (Azure/ArcGIS):** `dim_station` lat/lon, size = Departures, colour = station type.
* **Matrix heatmap:** rows = station, columns = hour, values = `Net flow`, weekday filter, conditional formatting with a diverging red→white→blue scale centred on 0.

### Page 2: Forecast vs actual
*Question: can we trust the forecast?*
* **KPI cards:** WAPE LightGBM · WAPE naive · Error reduction vs naive · Bias LightGBM.
* **Line chart:** `Actual (test)`, `Forecast LightGBM` and `Forecast naive` by `hour_ts`, with a station slicer (default: Waterloo Station 3).
* **Clustered bar:** `model_metrics` hourly WAPE and window WAPE by model.
* **Table: where it fails.** Rows = day type / bank holiday / rain bucket, values = WAPE LightGBM and WAPE naive.
* **Column chart:** daily `Bias LightGBM` by date, with bank holidays highlighted (conditional colour on `is_bank_holiday`).

### Page 3: Rebalancing plan
*Question: where should the vans go tomorrow?*
* **Slicers:** day type (default Weekday), window (default AM peak).
* **KPI cards:** Stations needing refill · Bikes to move · Trips served per week (estimate, labelled as such).
* **Table (main visual):** station, window, docks, forecast departures, expected arrivals, net drain, drain ratio (data bars), `risk_empty` (red/amber icons), recommended action. Sorted by drain ratio, descending.
* **Map:** stations coloured by `risk_empty` for the selected window.
* **Bar chart:** `impact_estimate` trips served per week by selector, at 50% starting fill (naive vs LightGBM vs perfect foresight).
* **Text box (assumptions):** docks start at 50% full, top 10 stations get one top-up to 90% before 06:00, actual Apr-May 2026 flows, and lost trips are counted when a dock is empty. "Estimate, not a measured result."

## Design notes
* Use one colour per station type everywhere (Morning origin = blue, Office/City = orange, Leisure/park = green, Mixed = grey). Keep red/amber only for risk levels.
* Never put two measures on twin y-axes. Use separate visuals.
