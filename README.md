# Home battery + solar simulation: minimising grid use during peak hours

Year-long (2024) simulation, at 15-minute resolution, of a household with rooftop solar panels and a home battery.
Every night at midnight a controller decides when the grid peak will be and how much to charge the battery
(from solar and from the grid) so that the house draws as little as possible from the grid during the peak.
The simulation is run for 300 real households, for every combination of panel count and battery size.

---

## 1. Setup

### Requirements
- Python 3.11+ (developed with Python 3.13)
- Packages for the simulation: `numpy`, `pandas`, `matplotlib`
- Extra packages only to re-download the data: `requests`, `pvlib`

All are listed in `requirements.txt`:
```
python -m pip install -r requirements.txt
```

> On Windows, if `python` is not found, call the interpreter by its full path, e.g. in PowerShell:
> `$py = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"; & $py run_single_household.py`

### Input data (`datasources/`)
All files cover 2024 in local Dutch/Belgian time (CET/CEST): 366 days x 96 quarter-hours = 35,136 rows.

| File | Content | Source |
|---|---|---|
| `fluvius_household_data.csv` | Consumption of 300 Flemish households without solar panels, kWh per 15 min | [Fluvius open data](https://opendata.fluvius.be) via `data_fetch/fetch_flanders_household_data.py` |
| `pvgis_solar_panel.csv` | Output of **one** 400 Wp south-facing panel in Delft (37° tilt), W per 15 min | PVGIS via `data_fetch/fetch_delft_solar.py` |
| `entsoe_grid_load.csv` | Actual total load of the Dutch grid (BZN\|NL), MW per 15 min | Export from the [ENTSO-E Transparency Platform](https://transparency.entsoe.eu) |
| `entsoe_energy_prices.csv` | Dutch day-ahead price, EUR/MWh per hour | Export from the ENTSO-E Transparency Platform |

The household file (790 MB) is too large for git and must be downloaded once:
```
cd data_fetch
python fetch_flanders_household_data.py
```
This downloads and unzips the Fluvius files into `data_fetch/fluvius_raw/`. Copy
`P6269_Open_Data_geen_ZP.csv` ("geen ZP" = no solar panels) to `datasources/fluvius_household_data.csv`.

The first simulation run converts this CSV into a compact cache (`datasources/cache/fluvius_households_kwh.npz`,
~15 s once); later runs load in under a second.

---

## 2. Running

### One household
```
python run_single_household.py --household 301
```
Simulates all scenarios (default: 0-16 panels in steps of 2 x batteries of 0/5/10/15 kWh) for one household and
writes `results/household_301/`: `scenarios.csv` plus figures (`sweep.png`, `heatmap_peak_import.png`,
`heatmap_export.png`, `week.png`). Takes ~6 s.

Useful options:

| Option | Default | Meaning |
|---|---|---|
| `--household` | 301 | Household ID (301-600) |
| `--panels` | `0,2,...,16` | Panel counts to simulate |
| `--batteries` | `0,5,10,15` | Usable battery capacities, kWh |
| `--peak-method` | `threshold` | `threshold` (dynamic window) or `fixed` |
| `--peak-threshold` | 0.8 | Threshold θ of the dynamic window (see 3.2) |
| `--peak-hours` | 4 | Window length for `--peak-method fixed` |
| `--c-rate` | 0.5 | Max battery power per kWh of capacity (kW/kWh) |
| `--target` | `full` | `full`: fill the battery before the peak; `need`: only the forecast peak need |
| `--plot-scenario` | `10,10` | `panels,battery` shown in `week.png` |
| `--plot-day` | 160 | First day (0 = 1 Jan) of `week.png` |
| `--show` | off | Also open the figures |

### All 300 households
```
python run_all_households.py --out all_full
```
Runs every household in parallel (`--workers 4` by default, ~9 min) and accepts the same options as above.
Each household is saved as soon as it is done; re-running the same command skips finished households
(`--overwrite` to redo them). Failed households are listed in `errors.log` without stopping the run.

The three runs used in the report:
```
python run_all_households.py --out all_full
python run_all_households.py --target need --out all_need
python run_all_households.py --peak-method fixed --peak-hours 4 --out all_fixed4h
```

Output in `results/<out>/`:

| File | Content |
|---|---|
| `scenarios.csv` | One row per household x scenario with all annual statistics (section 3.6) |
| `monthly.csv` | Same, per month |
| `households/<id>_daily.csv.gz` | Per household, one row per scenario x day |
| `median_per_scenario.csv` | Median household per scenario |
| `forecast_quality.csv` | Forecast accuracy per household |
| `run_config.json` | All settings, git commit, start/end time |

Load all daily files at once with
`pd.concat(pd.read_csv(f) for f in glob.glob("results/all_full/households/*_daily.csv.gz"))`.

### Figures across households
```
python make_summary_plots.py --run all_full
python make_summary_plots.py --compare all_full,all_need,all_fixed4h
```
The first writes `results/<run>/figures/` (`kpi_bands.png`, `peak_draw_yearly.png`, `monthly_peak_draw.png`,
`household_size.png`, `sufficient_battery.png`); the second writes `results/comparison/compare_runs.png`.
`--scatter-panels` selects the panel count used in the monthly and household-size figures (default 8).

---

## 3. Components and formulas

### Notation and sign convention
- Time step Δt = 0.25 h; day *d* = 0..365; quarter-hour *q* = 0..95.
- Powers in kW, energies in kWh.
- $P_\text{cons}$: household consumption, $P_\text{sol}$: solar generation,
  $P_\text{bat}$: battery power (**> 0 discharging**, < 0 charging),
  $P_\text{grid}$: grid power (**> 0 import**, < 0 export).

Power balance at every step (same convention as the earlier `framework.py`):

$$P_\text{grid} = P_\text{cons} - P_\text{sol} - P_\text{bat}$$

### Modules

| File | Role |
|---|---|
| `year_data.py` | Loads and aligns the four data sources (3.1) |
| `forecasting.py` | Midnight forecasts: peak window, household demand, solar (3.2-3.4) |
| `peak_shaving_controller.py` | Daily charging plan and battery operating modes (3.5) |
| `year_simulation.py` | Year simulation loop, statistics, scenario sweep (3.6) |
| `year_plots.py`, `make_summary_plots.py` | Figures |
| `run_single_household.py`, `run_all_households.py` | Command-line entry points |
| `framework.py`, `controllers.py`, `main.py` | Earlier single-day prototype (not used by the year simulation) |

### 3.1 Data (`year_data.py`)
- Household: $P_\text{cons} = E_\text{15min} / Δt$ (kWh per quarter → kW). The households have no PV, so the
  energy taken from the grid equals their consumption.
- Solar for *n* panels: $P_\text{sol} = n \cdot P_\text{panel}$, with $P_\text{panel}$ the PVGIS output of one
  400 Wp panel (~423 kWh/year).
- Prices: hourly day-ahead price repeated over its four quarter-hours, converted to EUR/kWh.
- All sources share the same daylight-saving convention (hour missing on 31 Mar, repeated on 27 Oct), so the rows
  align one to one.

### 3.2 Peak window (F1.4, `forecasting.py`)
Chosen at midnight from the **Dutch grid load** $L$ of the previous $N = 7$ days.

1. Average load profile per quarter-hour:
   $$\bar L_d(q) = \frac{1}{N}\sum_{k=1}^{N} L_{d-k}(q)$$
2. Threshold relative to the day's range, with θ = 0.8:
   $$T_d = \min_q \bar L_d(q) + θ\,\big(\max_q \bar L_d(q) - \min_q \bar L_d(q)\big)$$
3. Highest point: $q^* = \arg\max_q \bar L_d(q)$.
4. The peak window $[s, e)$ is the contiguous block around $q^*$ where $\bar L_d(q) \ge T_d$ (extended in both
   directions until the first quarter below $T_d$, or midnight).

The window length therefore varies per day (2.75-14.25 h in 2024, median 3.75 h). A higher θ gives shorter
windows. Day 0 (no history) uses 17:00-21:00. With `--peak-method fixed` the window is instead the `peak_hours`
consecutive hours with the highest $\sum \bar L_d(q)$.

For evaluation, the **actual** peak window of each day is computed with the same rule on that day's own load
$L_d(q)$ (known only in hindsight).

### 3.3 Household demand forecast (F1.1)
Average of the same weekday over the previous 4 weeks:
$$\hat P_{\text{cons},d}(q) = \frac{1}{4}\sum_{k=1}^{4} P_{\text{cons},d-7k}(q)$$
During the first week (no same weekday yet) the average of all previous days is used; day 0 has no forecast (zero).

### 3.4 Solar forecast (F1.2)
Season-based profile: average daily profile of the previous 14 days,
$$\hat P_{\text{sol},d}(q) = \frac{1}{14}\sum_{k=1}^{14} P_{\text{sol},d-k}(q)$$
(fewer days at the start of the year; zero on day 0).

### 3.5 Battery controller (F1.6, `peak_shaving_controller.py`)
Battery: usable capacity $C$ (kWh), max power $P_\text{max} = c_\text{rate} \cdot C$ (default 0.5 kW/kWh),
stored energy $E$. Lossless, fully usable from 0 to $C$.

**Daily plan at midnight** (stored energy $E_0$, peak window $[s, e)$):

1. Target energy at peak start:
   - `full`: $E_\text{target} = C$
   - `need`: $E_\text{target} = \min\big(C,\; Δt \sum_{q=s}^{e-1} \max(0,\, \hat P_\text{cons}(q) - \hat P_\text{sol}(q))\big)$
2. Expected solar charging before the peak (surplus capped by the inverter):
   $$\hat P_\text{solchg}(q) = \min\big(P_\text{max},\, \max(0,\, \hat P_\text{sol}(q) - \hat P_\text{cons}(q))\big), \quad q < s$$
3. Energy to buy from the grid:
   $$E_\text{grid} = \max\Big(0,\; E_\text{target} - E_0 - Δt \sum_{q<s} \hat P_\text{solchg}(q)\Big)$$
4. Schedule: sort the pre-peak quarters by day-ahead price (cheapest first) and fill them in that order with
   $$P_\text{gridchg}(q) = \min\big(P_\text{max} - \hat P_\text{solchg}(q),\; E_\text{remaining} / Δt\big)$$
   until $E_\text{grid}$ is covered.

The plan is fixed for the day (open-loop); forecast errors show up as a battery that is not completely full, or
full earlier than planned.

**Operating modes**, every quarter-hour, with net demand $P_\text{net} = P_\text{cons} - P_\text{sol}$:

| Period | Mode | Requested battery power |
|---|---|---|
| Before the peak ($q < s$) | Hold and charge: no discharging; store solar surplus + planned grid charging | $P_\text{bat} = -\big(\max(0, -P_\text{net}) + P_\text{gridchg}(q)\big)$ |
| During the peak ($s \le q < e$) | Cover the house: battery supplies what solar does not; surplus solar charges it | $P_\text{bat} = P_\text{net}$ |
| After the peak ($q \ge e$) | Self-consumption until midnight | $P_\text{bat} = P_\text{net}$ |

**Limits** applied to the requested power, then the battery is updated:
$$P_\text{bat} \leftarrow \text{clip}\big(P_\text{bat},\, -P_\text{max},\, P_\text{max}\big), \qquad
P_\text{bat} \leftarrow \text{clip}\Big(P_\text{bat},\, -\frac{C - E}{Δt},\, \frac{E}{Δt}\Big)$$
$$E_{t+1} = E_t - P_\text{bat} \cdot Δt$$

The simulation starts at $E = 0.5\,C$ on 1 January.

### 3.6 Statistics (`year_simulation.py`)
With $\mathbb{1}_\text{peak}$ marking the planned peak quarters, $p$ the day-ahead price (EUR/kWh) and sums over the
year:

| Statistic | Formula |
|---|---|
| Grid import / export | $\sum \max(0, P_\text{grid})Δt$ / $\sum \max(0, -P_\text{grid})Δt$ |
| Peak-hour grid draw | $\sum \max(0, P_\text{grid})\,Δt\,\mathbb{1}_\text{peak}$ |
| Off-peak grid draw | $\sum \max(0, P_\text{grid})\,Δt\,(1 - \mathbb{1}_\text{peak})$ |
| Peak draw reduction | $1 - \dfrac{\text{peak-hour grid draw}}{\sum P_\text{cons}\,Δt\,\mathbb{1}_\text{peak}}$ (vs the same house without panels or battery) |
| Off-peak draw change | off-peak grid draw $- \sum P_\text{cons}\,Δt\,(1 - \mathbb{1}_\text{peak})$ (> 0 when the battery charges from the grid) |
| Energy cost | $\sum P_\text{grid}\,Δt\,p$ (export paid at the import price, net metering) |
| Savings | $\sum P_\text{cons}\,Δt\,p - \text{energy cost}$ |
| Battery savings / peak reduction | Difference with the same panel count and no battery |
| Self-consumption | $1 - \text{export} / \text{solar energy}$ |
| Self-sufficiency | $1 - \text{import} / \text{consumption}$ |
| Highest grid draw | $\max P_\text{grid}$ (also per month: basis of the Flemish capacity tariff) |
| Battery grid charging | $\sum \max\big(0,\, -P_\text{bat} - \max(0, P_\text{sol} - P_\text{cons})\big)Δt$ |
| Equivalent full cycles | $\sum \max(0, P_\text{bat})Δt \,/\, C$ |
| Days peak fully covered | days with zero peak-hour grid draw |
| Battery full at peak start | days with $E \ge 0.99\,C$ when the peak starts |

Forecast quality (`forecast_quality.csv`): mean absolute error of the demand forecast (kW), error of the daily
solar energy forecast (%), overlap between planned and actual peak windows (%), and min/median/max window length.

---

## 4. Assumptions and limitations
- Export is paid at the same price as import (net metering at the wholesale day-ahead price; no taxes or grid fees).
- Battery and solar panels are lossless; the full battery capacity is usable; no cooling or standby losses.
- State of charge is known exactly (F1.3 frozen); grid impedance (F1.5) and fault handling (F5) are not modelled,
  except the inverter power limit.
- Households are Flemish (no Dutch per-household data is public), the grid load and prices are Dutch.
- PVGIS hourly weather data stops at 2023, so 2023 solar weather is mapped onto the 2024 calendar: seasonal yields
  are realistic, but day-to-day weather is not correlated with the 2024 consumption and grid data.
- Forecasts are simple averages; the plan is made once at midnight and not corrected during the day.
- Peak statistics depend on the peak window definition: only compare runs that use the same definition.
