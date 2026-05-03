# Implementation Plan
**Date:** 2026-05-03

This plan aligns the Phase 1 objectives (see Phase1_Report.md) with the current codebase status and defines the steps to complete the project for publication and production readiness.

---

## 1) Current Scope vs. Phase 1 Objectives

### Phase 1 Objectives (from Phase1_Report.md)
- EGARCH(1,1) volatility forecasting
- Black-Scholes fair pricing
- Mispricing detection (threshold-based)
- Volatility regime classification
- Strategy recommendation (rule-based)
- REST API (FastAPI)
- Multi-timeframe support (1m to weekly)
- Broker integration for live data

### Current Implementation Status (verified from code)
- EGARCH(1,1): Implemented and used in pipeline
- Black-Scholes pricing: Implemented
- Mispricing detection: Implemented (±5% threshold)
- Regime classification: Implemented
- Strategy generation: Implemented (rule-based)
- FastAPI endpoints: Implemented (15 endpoints)
- Multi-timeframe support: Implemented infrastructure, not fully validated on real data
- Upstox option chain: Implemented for live data
- Dhan adapter: Present but not wired
- Validation: Daily validator exists, but uses simulated option prices (not real option history)

---

## 2) Completion Phases

### Phase A: Data Ground Truth (Highest Priority)
Goal: Ensure all validation uses real option prices (no synthetic pricing).

Tasks:
- Use Upstox v3 historical candles for NIFTY spot (1m/5m/daily).
- Build an option-chain snapshot collector:
  - Call /v2/option/chain every 1m or 5m.
  - Store snapshots to local DB (SQLite/Postgres).
  - Schema: timestamp, expiry, strike, call/put price, IV, OI, volume.
- Add /v2/option/contract usage to map instrument keys and strike universe.

Acceptance criteria:
- At least 4 weeks of real option chain snapshots collected.
- Ability to query historical option prices by timestamp.

---

### Phase B: Validation (Publication-Ready)
Goal: Replace synthetic validation with real option data.

Tasks:
- Re-run mispricing validation using real historical option snapshots.
- Validate at daily and 5m granularities:
  - Daily: end-of-day option chain vs fair price.
  - Intraday: option chain snapshots at 5m intervals.
- Compute metrics: precision, recall, F1, ROC-AUC, confusion matrix.
- Add cross-expiry testing: weekly and monthly expiries.

Acceptance criteria:
- Validation metrics computed on real option prices.
- Results documented in VALIDATION_EXPLANATION.md (real data section).

---

### Phase C: Pipeline Quality & Risk Controls
Goal: Improve robustness and align with IEEE standards.

Tasks:
- Add transaction cost modeling (bid/ask + slippage).
- Add risk management module (position sizing, stop-loss rules).
- Implement multi-symbol support (future extension beyond NIFTY).
- Add automated unit/integration tests for each service module.

Acceptance criteria:
- Unit tests for data_service, volatility_service, pricing_service.
- CI-ready test suite with deterministic outputs.

---

### Phase D: API & Productization
Goal: Make the pipeline deployable and user-facing.

Tasks:
- Add DB persistence for pipeline outputs.
- Add authentication for API endpoints.
- Provide minimal frontend dashboard or reporting page.
- Add system metrics (latency, uptime, request counts).

Acceptance criteria:
- Stable deployment in Docker with persistent storage.
- Authentication gate for /strategy and /option-chain.

---

### Phase E: Publication
Goal: Produce a submission-ready paper.

Tasks:
- Integrate final validation tables and figures.
- Add ablation study (EGARCH vs historical vol vs implied vol).
- Write Results and Discussion section.
- Peer review and revision.

Acceptance criteria:
- IEEE paper draft with reproducible methods and results.

---

## 3) Engineering Checklist

### Data
- [ ] Option chain snapshot collector (cron or service loop)
- [ ] Historical spot candles via Upstox v3 API
- [ ] Storage schema for snapshot history

### Validation
- [ ] Replace synthetic validation with real option prices
- [ ] Intraday validation (5m) and daily validation
- [ ] Results tables and figures

### Pipeline
- [ ] Multi-timeframe robustness testing
- [ ] Dhan adapter wiring or removal
- [ ] Configurable mispricing threshold

### Delivery
- [ ] Update README with accurate status
- [ ] Update documentation in Phase1_Report.md if scope changes
- [ ] Prepare publication assets (figures, charts, tables)

---

## 4) Timeline (Realistic)

- Phase A: 2-4 weeks (data collection)
- Phase B: 2 weeks (validation on real data)
- Phase C: 2-3 weeks (risk + tests)
- Phase D: 2 weeks (API/DB/frontend)
- Phase E: 4-6 weeks (writing + review)

**Total:** 12-17 weeks for full publication readiness.
