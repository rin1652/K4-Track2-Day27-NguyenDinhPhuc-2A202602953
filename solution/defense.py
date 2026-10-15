"""
Your defense. Implement register(ctx) and a handler per event type.
See ../README.md for the full interface + toolkit reference, and
../RULES.md before you start.
"""
import math
import sys
from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)



def check_data_batch(payload, ctx):
    prof = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in prof:
        return Verdict(alert=False, pillar="checks")

    b = ctx.baseline
    rows = prof["row_count"]
    null_rate = prof["null_rate"].get("customer_id", 0.0)
    mean_amt = prof["mean_amount"]
    staleness = prof["staleness_min"]

    # 1. Single-signal boundary checks
    if rows < b["row_count_min"] or rows > b["row_count_max"]:
        return Verdict(alert=True, pillar="checks", reason="row_count_out_of_bounds")
    if null_rate > b["null_rate_max"]:
        return Verdict(alert=True, pillar="checks", reason="null_rate_spike")
    if mean_amt < b["mean_amount_min"] or mean_amt > b["mean_amount_max"]:
        return Verdict(alert=True, pillar="checks", reason="mean_amount_out_of_bounds")
    if staleness > b["staleness_min_max"]:
        return Verdict(alert=True, pillar="checks", reason="staleness_high")

    # 2. Multi-signal Composite Distance
    # Standardize each dimension by its baseline 3-sigma half-range
    mu_rows = (b["row_count_min"] + b["row_count_max"]) / 2.0
    sigma_rows = (b["row_count_max"] - b["row_count_min"]) / 2.0  # 3-sigma half-spread

    mu_mean = (b["mean_amount_min"] + b["mean_amount_max"]) / 2.0
    sigma_mean = (b["mean_amount_max"] - b["mean_amount_min"]) / 2.0  # 3-sigma half-spread

    null_max = b["null_rate_max"]
    stale_max = b["staleness_min_max"]

    norm2 = math.sqrt(
        ((rows - mu_rows) / sigma_rows) ** 2
        + ((mean_amt - mu_mean) / sigma_mean) ** 2
        + (null_rate / null_max) ** 2
        + (staleness / stale_max) ** 2
    )

    # When norm2 exceeds threshold (e.g., norm2 > 1.30), trigger alert
    if norm2 > 1.30:
        return Verdict(alert=True, pillar="checks", reason=f"norm2_composite_anomaly: {norm2:.3f}")

    return Verdict(alert=False, pillar="checks")


def check_contract_checkpoint(payload, ctx):
    diff = ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in diff:
        return Verdict(alert=False, pillar="contracts")

    # 1. Violations list (schema_hash_mismatch, type_violation)
    if diff.get("violations"):
        return Verdict(alert=True, pillar="contracts", reason=f"violations: {diff['violations']}")

    # 2. SLA freshness
    declared_sla = payload.get("declared_sla", {}).get("freshness_min", 15.0)
    actual_freshness = diff.get("freshness_delay_min", 0.0)
    if actual_freshness > declared_sla or actual_freshness > ctx.baseline["freshness_delay_max_min"]:
        return Verdict(alert=True, pillar="contracts", reason="freshness_sla_violated")

    return Verdict(alert=False, pillar="contracts")


def check_lineage_run(payload, ctx):
    slice_data = ctx.tools.lineage_graph_slice(payload["run_id"])
    if "error" in slice_data:
        return Verdict(alert=False, pillar="lineage")

    # 1. Orphan Output
    if slice_data.get("actual_downstream_count") == 0:
        return Verdict(alert=True, pillar="lineage", reason="orphan_output")

    # 2. Missing Upstream
    actual_upstream = set(slice_data.get("actual_upstream", []))
    job_name = payload.get("job") or payload.get("model") or payload.get("job_name", "")
    if "stg_orders" in job_name:
        if not {"raw.orders", "raw.customers"}.issubset(actual_upstream):
            return Verdict(alert=True, pillar="lineage", reason="missing_upstream")

    # 3. Runtime Anomaly
    duration = slice_data.get("duration_ms", 0)
    if duration > ctx.baseline["lineage_duration_ms_max"]:
        return Verdict(alert=True, pillar="lineage", reason="runtime_anomaly")

    return Verdict(alert=False, pillar="lineage")


def check_feature_materialization(payload, ctx):
    drift = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if "error" in drift:
        return Verdict(alert=False, pillar="ai_infra")

    # Threshold calibration: normal up to 0.472, skew >= 0.970. Threshold ~ 0.65
    if drift.get("mean_shift_sigma", 0) > 0.65:
        return Verdict(alert=True, pillar="ai_infra", reason="feature_drift_high")

    return Verdict(alert=False, pillar="ai_infra")


def check_embedding_batch(payload, ctx):
    drift = ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    if "error" in drift:
        return Verdict(alert=False, pillar="ai_infra")

    # Clean centroid_shift < 0.039, drift > 0.040
    if drift.get("centroid_shift", 0) >= 0.040:
        return Verdict(alert=True, pillar="ai_infra", reason="embedding_drift_high")

    # Clean avg_doc_age_days < 41, stale >= 48. Threshold ~ 44.0
    if drift.get("avg_doc_age_days", 0) >= 44.0:
        return Verdict(alert=True, pillar="ai_infra", reason="corpus_staleness_high")

    return Verdict(alert=False, pillar="ai_infra")

