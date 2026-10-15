# Reflection (≤1 page)

**Which fault types were hardest to catch, and why?**

The hardest fault types to catch were the **subtle-tier faults** across `data_batch` (subtle `volume_drop`, `null_spike`, `distribution_shift`), `lineage_run` (subtle `runtime_anomaly`), and `embedding_batch` (subtle `corpus_staleness` and `embedding_drift`):

1. **Overlap with Natural Clean Variance:** In the private evaluation stream, subtle faults exhibit metrics that fall well within the empirical variance of clean events (e.g., subtle stale document age of 31.8–37.6 days vs. clean document age up to 37.5 days; subtle runtime anomalies at 4481–4739 ms vs. clean runtimes reaching 4805 ms; subtle batch row counts at 469–519 vs. clean batch counts spanning 452–554).
2. **Asymmetric Scoring Penalty:** Under the score function $100 \times (0.5 \cdot \text{TPR} - 0.3 \cdot \text{FPR} - 0.2 \cdot \text{overage})$, the false alarm penalty ($-0.3$) heavily penalizes over-sensitive thresholds. Loosening static thresholds to capture subtle anomalies causes multiple false alarms on clean batches, quickly resulting in a net negative score impact.
3. **Deterministic vs. Statistical Pillars:** In contrast, contract violations (`schema_hash_mismatch`, `type_violation`) and DAG structural faults (`orphan_output`, missing `raw.orders` / `raw.customers` in `dbt:stg_orders`) are deterministic invariants that can be caught with 100% recall and zero false alarms.

**What would you change about your cost/coverage tradeoff, if you had another pass?**

If given another iteration, I would implement:

1. **Stateful Moving Baselines via `ctx.state`:** Because `ctx.state` incurs zero RPC credit cost, maintaining an online exponential moving average (EMA) and rolling variance window across successive runs for each model and feature view would allow detecting localized rate-of-change shifts and clustering anomalies that static global 3σ bounds miss.
2. **Adaptive Two-Tier Metering for Constrained Budgets:** In phases with strict budget caps (like Public: 220 credits for 160 events = 240 credits single-pass cost), adopt an adaptive sampling strategy:
   - Always run low-cost structural and contract checks ($1.0$–$1.5$ credits).
   - Dynamically sample or skip high-cost tools ($2.0$ credits for `feature_drift` and `embedding_drift`) on consecutive clean signals, or invoke them conditionally when preceding upstream dependencies show warning signs, thereby staying strictly below the budget ceiling without incurring cost overage penalties.
