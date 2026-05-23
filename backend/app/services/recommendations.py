"""
Rules-based recommendation engine.

Each rule is a plain function with signature:
    rule(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]

Add new rules by appending a function to RULES — no if/else chain required.
The engine runs every rule, collects non-None results, and deduplicates by
action_text before persisting.

site_data keys expected by rules:
    site, quarter, total_incidents_qtr, delta_qtr_pct, reporting_lag_p90,
    business_unit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------

@dataclass
class RecommendationSpec:
    action_text: str
    priority: str          # high / medium / low
    impact_estimate: str = ""
    suggested_owner: str = ""
    source: str = "rules"


# type alias for rule functions
RuleFn = Callable[[list[dict], dict], Optional[RecommendationSpec]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cat_match(driver_name: str, *keywords: str) -> bool:
    """True if ALL keywords appear in driver_name (case-insensitive)."""
    name_lower = (driver_name or "").lower()
    return all(kw.lower() in name_lower for kw in keywords)


def _find_driver(drivers: list[dict], *keywords: str) -> Optional[dict]:
    """Return the first driver whose name contains all keywords."""
    for d in drivers:
        if _cat_match(d.get("driver_name", ""), *keywords):
            return d
    return None


def _top_driver(drivers: list[dict]) -> Optional[dict]:
    """The driver with the highest impact_score."""
    return max(drivers, key=lambda d: d.get("impact_score", 0)) if drivers else None


# ---------------------------------------------------------------------------
# Individual rules (each is a self-contained function)
# ---------------------------------------------------------------------------

def rule_access_control(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Access Control trend up by >20% → physical security review."""
    d = _find_driver(drivers, "access control")
    if d and d.get("trend") == "up" and (d.get("pct_change_vs_last_qtr") or 0) > 20:
        return RecommendationSpec(
            action_text="Enhance access control and conduct CCTV coverage review",
            priority="high",
            impact_estimate="Could reduce access-control incidents 20-30% within 2 quarters",
            suggested_owner="Site Security Manager",
        )
    return None


def rule_ir_worker(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """IR/Worker driver with high impact → labour engagement programme."""
    d = _find_driver(drivers, "ir", "worker")
    if d and (d.get("impact_score") or 0) > 70:
        return RecommendationSpec(
            action_text="Initiate community/labour engagement programme",
            priority="medium",
            impact_estimate="Could reduce IR-related incidents 15-25% over 2 quarters",
            suggested_owner="HR & Community Relations",
        )
    return None


def rule_asset_property(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Asset/Property is top driver AND total incidents rising QoQ."""
    top = _top_driver(drivers)
    if (
        top
        and _cat_match(top.get("driver_name", ""), "asset")
        and (site_data.get("delta_qtr_pct") or 0) > 0
    ):
        return RecommendationSpec(
            action_text="Increase night patrol rotation and asset-tagging coverage",
            priority="high",
            impact_estimate="Could reduce asset/property incidents 15-20%",
            suggested_owner="Site Security Manager",
        )
    return None


def rule_reporting_lag(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """p90 reporting lag > 30 days → process review."""
    lag = site_data.get("reporting_lag_p90")
    if lag is not None and lag > 30:
        return RecommendationSpec(
            action_text="Review incident-reporting workflow to reduce p90 lag below 30 days",
            priority="medium",
            impact_estimate="Faster reporting enables quicker corrective action",
            suggested_owner="EHS Compliance Lead",
        )
    return None


def rule_process_deviations(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """SOP / LSR / Process-deviation driver trending up → refresher training."""
    d = _find_driver(drivers, "sop") or _find_driver(drivers, "lsr") or _find_driver(drivers, "deviation")
    if d and d.get("trend") == "up":
        return RecommendationSpec(
            action_text="Schedule SOP/LSR refresher training and update procedure notices",
            priority="medium",
            impact_estimate="Could reduce SOP-violation incidents 10-15%",
            suggested_owner="EHS Training Coordinator",
        )
    return None


def rule_generic_fallback(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Always fires: review and address the top driver."""
    top = _top_driver(drivers)
    if not top:
        return None
    score = top.get("impact_score", 0)
    priority = "high" if score >= 60 else ("medium" if score >= 30 else "low")
    return RecommendationSpec(
        action_text=f"Review and address root causes of '{top['driver_name']}' incidents",
        priority=priority,
        impact_estimate=f"Top driver accounts for {score:.0f}/100 of predicted risk",
        suggested_owner="Site EHS Manager",
    )


# ---------------------------------------------------------------------------
# Rule registry — add new rules here, order matters for priority resolution
# ---------------------------------------------------------------------------

RULES: list[RuleFn] = [
    rule_access_control,
    rule_ir_worker,
    rule_asset_property,
    rule_reporting_lag,
    rule_process_deviations,
    rule_generic_fallback,   # must be last (fallback)
]


# ---------------------------------------------------------------------------
# Engine entry point
# ---------------------------------------------------------------------------

def generate_recommendations(
    drivers: list[dict],
    site_data: dict,
    rules: list[RuleFn] = None,
) -> list[RecommendationSpec]:
    """
    Run every rule against driver data and site context.

    Parameters
    ----------
    drivers : List of driver dicts (from compute_drivers_for_site).
    site_data : Dict with site context (total_incidents_qtr, delta_qtr_pct,
                reporting_lag_p90, site, quarter, business_unit).
    rules : Override the default RULES list (useful for testing).

    Returns
    -------
    Deduplicated list of RecommendationSpec, ordered high → medium → low.
    """
    rule_set = rules if rules is not None else RULES
    seen: set[str] = set()
    results: list[RecommendationSpec] = []

    for rule_fn in rule_set:
        try:
            rec = rule_fn(drivers, site_data)
        except Exception:
            continue   # never let a buggy rule crash the engine

        if rec and rec.action_text not in seen:
            results.append(rec)
            seen.add(rec.action_text)

    _priority_order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda r: _priority_order.get(r.priority, 99))
    return results
