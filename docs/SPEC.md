# HimKavach: Architectural & Technical Specification

## 1. System Mission & Context
- **Target Domain:** Smart Energy Management System for isolated polar research stations (MoES / NCPOR, e.g., Maitri 70.8°S 11.7°E, Bharati 69.4°S 76.2°E).
- **Core Challenge:** Polar stations face harsh katabatic storms, blizzards, multi-day wind turbine cutouts, zero solar generation in polar night, sub-zero battery throttling, and high fuel delivery logistics costs with annual resupply vulnerability.
- **Mission:** Guarantee zero interruption of Tier 0 life support under all physically serviceable conditions, minimize diesel fuel burn via predictive multi-energy dispatch, maximize renewable penetration, and maintain survival reserves ahead of correlated storm shocks.

## 2. Tiered System Architecture
1. **Digital Twin Environment (`packages/twin`)**:
   - Higher-fidelity physics-based simulation with nonlinear fuel consumption, generator startup lags and wear, cold-temperature battery electrochemical constraints, PV snow burial and shedding, wind turbine cut-in/rated/cut-out hysteresis, building RC thermal model, and stochastic fault injection.
2. **State & Health Estimation (`packages/health`)**:
   - Ingests 1-minute telemetry.
   - Monitors fuel accounting (tank drop vs expected engine fuel burn).
   - Detects genset drift, turbine icing, and sensor dropouts using residual CUSUM and Isolation Forest.
3. **Forecasting & Scenario Engine (`packages/forecast`)**:
   - Quantile regression (XGBoost) for wind, solar, and thermal/electrical loads.
   - Calibrated storm onset probability classifier.
   - Conformal calibration ensuring empirical coverage matches nominal prediction intervals.
   - Regime-conditioned Gaussian copula generating $K \approx 15$ correlated scenarios plus one designated P90 stress scenario.
4. **Strategic Planning Layer (Fuel Glide Path LP) (`packages/optimizer`)**:
   - Coarse daily-resolution LP to resupply day + contingency buffer.
   - Calculates dynamic fuel shadow price $\lambda_{\text{fuel}}$ reflecting station fuel status relative to nominal glide path.
5. **Tactical Planning Layer (Scenario-based MPC MILP) (`packages/optimizer`)**:
   - 72-hour horizon (24 steps @ 15 min, 66 steps @ 60 min = 90 steps).
   - Non-anticipative binary commitment decisions for generators shared across all scenarios.
   - Scenario-specific continuous dispatch for generators, battery, thermal storage, and load shedding.
   - Rockafellar-Uryasev CVaR risk formulation on unserved energy and reserve violation.
   - Pyomo formulation solved with HiGHS (`appsi_highs`).
6. **Deterministic Safety Supervisor (`packages/control`)**:
   - Independent 1-minute execution layer.
   - Enforces SoC safety floors and generator auto-start.
   - Strictly enforces shed priority: Tier 3 (deferrable) -> Tier 2 (comfort) -> Tier 1 (science) -> Tier 0 (life support - never shed unless physically impossible).
   - Watchdog heartbeat monitoring on the optimizer; falls back to conservative rule-based mode if the optimizer stalls.
7. **Evaluation Harness & Baselines (`packages/evaluation`)**:
   - Baselines: B1 (Naive Rule), B2 (Tuned Smart Rule), B3 (Deterministic MPC), B4 (Oracle MPC).
   - Seeded Monte Carlo evaluator, KPI waterfall attribution, automated report generation.
8. **Serving & UI (`services/api`, `web`)**:
   - FastAPI REST and WebSocket telemetry/plan feed.
   - PostgreSQL persistence + Parquet bulk telemetry.
   - React + Vite + TypeScript + ECharts dashboard.

## 3. Units & Data Conventions
- Power: Kilowatts (kW)
- Energy: Kilowatt-hours (kWh)
- Fuel Volume: Litres (L)
- Temperature: Degrees Celsius (°C)
- Wind Speed: Metres per second (m/s)
- Pressure: Hectopascals (hPa)
- Solar Irradiance: Watts per square metre (W/m²)
- Time: UTC timezone-aware ISO 8601 strings or epoch seconds
- Seeded pseudo-randomness: Explicit `numpy.random.Generator` across all stochastic processes.
