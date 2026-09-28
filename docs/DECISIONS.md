# Architectural Decision Records (ADRs)

## ADR-001: Pydantic v2 as Unified Contract Framework
- **Date:** 2026-09-29
- **Status:** Accepted
- **Context:** Modules across twin, forecasting, optimization, control, health, and API must share domain entities (`StationConfig`, `StationState`, `WeatherObs`, `Forecast`, `ScenarioSet`, `Plan`, `Action`, `DecisionCard`, `HealthReport`, `Metrics`, `ExperimentConfig`).
- **Decision:** Implement all domain contracts in `packages/core/src/himkavach_core/contracts/` using Pydantic v2 `BaseModel` with strict type validation, frozen/immutable definitions where appropriate, and explicit JSON serialization schemas.
- **Consequences:** Ensures single source of truth across Python backend, database serialization, and TypeScript interfaces via JSON schema generation. High validation speed via `pydantic-core`.

## ADR-002: Variable-Resolution Time Grid for 72h MPC
- **Date:** 2026-09-29
- **Status:** Accepted
- **Context:** A uniform 15-minute resolution across 72 hours requires 288 steps. Multiplied by $K \approx 15$ scenarios, this leads to over 4,320 scenario-time slices, creating solve-time bottlenecks for MILP.
- **Decision:** Adopt a hybrid grid:
  - First 6 hours: 24 steps @ 15 min ($\Delta t = 0.25\text{ h}$) for responsive intra-day battery and generator dispatch.
  - Remaining 66 hours: 66 steps @ 60 min ($\Delta t = 1.0\text{ h}$) for multi-day storm ride-through.
  - Total: 90 steps.
- **Consequences:** Reduces decision variable space by ~68% while preserving granular control during the imminent re-planning horizon.

## ADR-003: Pre-computation of Nonlinear Weather Physics for Scenario Inputs
- **Date:** 2026-09-29
- **Status:** Accepted
- **Context:** Turbine cut-out at high wind speeds ($\sim 25\text{ m/s}$), hysteresis lockouts, PV snow burial, and clear-sky solar curves introduce non-convexities that would make the optimizer non-linear or intractable if solved inside the MPC.
- **Decision:** Apply nonlinear physics during scenario generation in `packages/forecast`. The scenario generator outputs deterministic effective renewable power bounds ($P_{wind, s, t}^{max}, P_{pv, s, t}^{max}$) and ambient temperature $T_{amb, s, t}$ for each scenario $s$ and step $t$.
- **Consequences:** The MPC remains a tractable Mixed-Integer Linear Program (MILP) solvable within seconds via HiGHS.

## ADR-004: Two-Stage Stochastic Formulation with Non-anticipative Here-and-Now Generator Binaries
- **Date:** 2026-09-29
- **Status:** Accepted
- **Context:** Generator startup and shutdown decisions must be committed before the actual realized weather scenario unfolds.
- **Decision:** Generator on/off commitment binaries $u_{g, t} \in \{0, 1\}$ are first-stage decisions, identical across all scenarios $s$. Scenario-specific dispatch $P_{g, s, t}$, battery power $P_{bat, s, t}$, and load shedding $S_{tier, s, t}$ are second-stage recourse variables.
- **Consequences:** Binaries do not scale with $K$, keeping the branch-and-bound search space small and preventing foresight leakage.

## ADR-005: Decoupled Deterministic Safety Supervisor
- **Date:** 2026-09-29
- **Status:** Accepted
- **Context:** MILP solvers can time out, become infeasible under unexpected edge states, or face process crashes. Life-support power at $-40^\circ\text{C}$ cannot depend on solver liveness.
- **Decision:** Implement a standalone, deterministic `SafetySupervisor` executing at the 1-minute cadence that enforces hard invariants (SoC bounds, generator auto-start, strict tier shedding) and monitors an EMS heartbeat watchdog.
- **Consequences:** Formally verifiable using property-based testing (`hypothesis`); guarantees zero Tier 0 unserved load whenever physically feasible regardless of optimizer status.
