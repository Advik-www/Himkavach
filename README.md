# HimKavach: Polar Energy Flight-Planner

**HimKavach** (Smart India Hackathon PS 26061) is an intelligent, resilience-first energy management system and flight-planner designed for isolated polar research stations (MoES / NCPOR, e.g., Maitri and Bharati in Antarctica).

In isolated polar microgrids, fuel resupply is an annual high-risk event, storms represent correlated severe shocks (turbine cut-outs, zero solar, sub-zero battery throttling, and escalating thermal load), and life support must never fail. HimKavach couples long-horizon fuel glide paths, storm-conditioned joint scenario trees, rolling-horizon scenario MPC (MILP), and a deterministic, fail-safe safety supervisor.

## Architecture

```
PLANT (digital twin / real station telemetry)
   ^ setpoints                          | telemetry (1 min)
SAFETY SUPERVISOR  <-- plan --  OPTIMIZER (glide path LP + 72h scenario MPC)
                                        ^
                                SCENARIO GENERATOR (copula, K~15 + stress case)
                                        ^
                                FORECAST ENGINE (storm clf, quantile models, conformal)
                                        ^
                                STATE & HEALTH ESTIMATION
                                        ^
                                INGEST + QC
```

## Quick Start

### Installation
```bash
make setup
```

### Run Tests
```bash
make test
```

### Run Demo ("Storm Night")
```bash
make demo
```

## Repository Structure

```
himkavach/
  packages/
    core/          # Pydantic contracts, units, config loading
    twin/          # weather, pv, wind, battery, genset, fuel, loads, thermal, faults, storms
    forecast/      # features, storm clf, quantile models, conformal, scenario gen, eval
    optimizer/     # model builders, glide path, solver wrappers, fallbacks
    control/       # supervisor, baselines B1-B4, mode manager, decision cards
    health/        # state estimation, anomaly detection
    evaluation/    # closed-loop harness, monte carlo, metrics, reports
  services/api/    # FastAPI, WebSockets, DB access
  web/             # React console
  configs/         # station YAMLs, scenarios, experiment definitions
  experiments/     # reproducible runs and stored result artifacts
  docs/            # SPEC.md, DECISIONS.md, optimization_model.md
  tests/           # unit, property-based, integration, performance
```
