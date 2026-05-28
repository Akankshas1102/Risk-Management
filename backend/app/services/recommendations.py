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

Driver dict keys (from compute_drivers_for_site):
    driver_name, category, impact_score, trend, pct_change_vs_last_qtr,
    sparkline_data, quarter, computed_at
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
    priority: str           # high / medium / low
    impact_estimate: str = ""
    suggested_owner: str = ""
    source: str = "rules"
    driver_link: str = ""   # category / driver name that triggered this rule


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


def _find_exact(drivers: list[dict], name: str) -> Optional[dict]:
    """
    Return the first driver whose name EXACTLY equals `name` (case-insensitive).
    Used for short ambiguous category codes like 'IR' where a substring match
    would wrongly hit 'Fire' etc.
    """
    target = name.strip().lower()
    for d in drivers:
        if (d.get("driver_name", "") or "").strip().lower() == target:
            return d
    return None


def _top_driver(drivers: list[dict]) -> Optional[dict]:
    """The driver with the highest impact_score."""
    return max(drivers, key=lambda d: d.get("impact_score", 0)) if drivers else None


def _driver_name(d: Optional[dict]) -> str:
    """Safe driver name extraction for driver_link."""
    return (d or {}).get("driver_name", "") or ""


# ---------------------------------------------------------------------------
# Individual rules (each is a self-contained function)
# ---------------------------------------------------------------------------

def rule_high_velocity(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Any driver with QoQ change > 20% — rapid escalation flag."""
    sharp = [d for d in drivers if (d.get("pct_change_vs_last_qtr") or 0) > 20]
    if not sharp:
        return None
    worst = max(sharp, key=lambda d: d.get("pct_change_vs_last_qtr", 0))
    return RecommendationSpec(
        action_text=(
            f"Investigate rapid rise in '{worst['driver_name']}' incidents "
            f"({worst.get('pct_change_vs_last_qtr', 0):.0f}% QoQ) — trigger root-cause analysis"
        ),
        priority="high",
        impact_estimate="Rapid escalation; early intervention can prevent repeat incidents",
        suggested_owner="Site EHS Manager",
        driver_link=_driver_name(worst),
    )


def rule_access_control(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Access & Intrusion driver with notable impact → physical security review."""
    d = _find_driver(drivers, "access")   # matches CATEGORY_GROUP "Access & Intrusion"
    if d and (d.get("impact_score") or 0) > 15:
        return RecommendationSpec(
            action_text="Enhance access control and conduct CCTV coverage review",
            priority="high",
            impact_estimate="Could reduce access-control incidents 20-30% within 2 quarters",
            suggested_owner="Site Security Manager",
            driver_link=_driver_name(d),
        )
    return None


def rule_material_handling(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Material driver with notable impact → safe-handling refresher."""
    d = _find_driver(drivers, "material")   # matches CATEGORY_GROUP "Material"
    if d and (d.get("impact_score") or 0) > 15:
        return RecommendationSpec(
            action_text="Audit material handling procedures and schedule safe-handling refresher",
            priority="high" if (d.get("impact_score") or 0) >= 60 else "medium",
            impact_estimate="Material incidents are high-impact; 20-30% reduction possible with controls",
            suggested_owner="Operations & EHS Manager",
            driver_link=_driver_name(d),
        )
    return None


def rule_ir_worker(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Industrial Relations driver with notable impact → labour engagement programme."""
    # Matches the CATEGORY_GROUP "Industrial Relations" AND the raw categories
    # "IR" / "IR - Worker/ Union/ Transporters".  ('ir' alone is avoided — it
    # would substring-match 'Fire'; we use exact 'IR' + worker/union instead.)
    d = (
        _find_driver(drivers, "industrial")
        or _find_driver(drivers, "worker")
        or _find_driver(drivers, "union")
        or _find_exact(drivers, "IR")
    )
    if d and (d.get("impact_score") or 0) > 15:
        return RecommendationSpec(
            action_text="Initiate community/labour engagement programme",
            priority="medium",
            impact_estimate="Could reduce IR-related incidents 15-25% over 2 quarters",
            suggested_owner="HR & Community Relations",
            driver_link=_driver_name(d),
        )
    return None


def rule_community_pr(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Community & PR driver with notable impact → community engagement programme."""
    # Matches CATEGORY_GROUP "Community & PR" AND raw categories
    # "PR - Villagers/ Neighborhood" / "Agitation by community and workers".
    d = (
        _find_driver(drivers, "community")
        or _find_driver(drivers, "villagers")
        or _find_driver(drivers, "neighbo")
    )
    if d and (d.get("impact_score") or 0) > 20:
        return RecommendationSpec(
            action_text=(
                "Initiate community engagement programme — schedule quarterly dialogues "
                "with village leaders and address top grievances from incident records"
            ),
            priority="medium",
            impact_estimate="Could reduce community/PR incidents 15-25% over 2 quarters",
            suggested_owner="Site HSE Head",
            driver_link=_driver_name(d),
        )
    return None


def rule_asset_property(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Asset & Property is top driver OR has notable impact → asset security audit."""
    d = _find_driver(drivers, "asset")   # matches CATEGORY_GROUP "Asset & Property"
    top = _top_driver(drivers)
    is_top = top is not None and _cat_match(top.get("driver_name", ""), "asset")
    if d and (is_top or (d.get("impact_score") or 0) > 25):
        return RecommendationSpec(
            action_text=(
                "Conduct full asset security audit — review perimeter fencing, CCTV "
                "coverage, and access logs for the affected zones"
            ),
            priority="high",
            impact_estimate="Could reduce asset/property incidents 15-20%",
            suggested_owner="Site Security Manager",
            driver_link=_driver_name(d),
        )
    return None


def rule_traffic_transit(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Traffic & Transit driver with notable impact → vehicle movement review."""
    d = _find_driver(drivers, "traffic")   # matches CATEGORY_GROUP "Traffic & Transit"
    if d and (d.get("impact_score") or 0) > 20:
        return RecommendationSpec(
            action_text=(
                "Review vehicle movement protocols — enforce speed limits, update gate "
                "entry registers, and increase spot checks on contractor vehicles"
            ),
            priority="medium",
            impact_estimate="Could reduce traffic/transit incidents 15-20%",
            suggested_owner="Operations Manager",
            driver_link=_driver_name(d),
        )
    return None


def rule_safety_sop(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Safety & SOP Violation driver with notable impact → mandatory SOP refresher."""
    d = _find_driver(drivers, "sop") or _find_driver(drivers, "safety")
    if d and (d.get("impact_score") or 0) > 20:
        return RecommendationSpec(
            action_text=(
                "Schedule mandatory SOP refresher training for all site personnel — focus "
                "on the top-violated procedures identified in recent incident reports"
            ),
            priority="high",
            impact_estimate="Could reduce SOP-violation incidents 10-20%",
            suggested_owner="Site HSE Head",
            driver_link=_driver_name(d),
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
            driver_link="",   # lag is a process metric, not a specific driver category
        )
    return None


def rule_process_deviations(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Safety & SOP Violation driver trending UP → refresher training & notices."""
    d = _find_driver(drivers, "sop") or _find_driver(drivers, "safety")
    if d and d.get("trend") == "up":
        return RecommendationSpec(
            action_text="Schedule SOP/LSR refresher training and update procedure notices",
            priority="medium",
            impact_estimate="Could reduce SOP-violation incidents 10-15%",
            suggested_owner="EHS Training Coordinator",
            driver_link=_driver_name(d),
        )
    return None


def rule_generic_fallback(drivers: list[dict], site_data: dict) -> Optional[RecommendationSpec]:
    """Always fires: structured root-cause action for the top driver."""
    top = _top_driver(drivers)
    if not top:
        return None
    score = top.get("impact_score", 0)
    priority = "high" if score > 70 else ("medium" if score >= 40 else "low")
    return RecommendationSpec(
        action_text=(
            f"Investigate recurring '{top['driver_name']}' incidents this quarter — "
            f"assign a root-cause analysis owner, document findings, and present "
            f"corrective actions at the next site safety review meeting"
        ),
        priority=priority,
        impact_estimate=f"Top driver accounts for {score:.0f}/100 of predicted risk",
        suggested_owner="Site EHS Manager",
        driver_link=_driver_name(top),
    )


# ---------------------------------------------------------------------------
# Rule registry — add new rules here; order matters for dedup precedence.
# rule_generic_fallback must remain last (it always fires as a safety net).
# ---------------------------------------------------------------------------

RULES: list[RuleFn] = [
    rule_high_velocity,          # any driver QoQ > 20%
    rule_access_control,         # Access & Intrusion impact > 15
    rule_material_handling,      # Material impact > 15
    rule_ir_worker,              # Industrial Relations impact > 15
    rule_community_pr,           # Community & PR impact > 20
    rule_asset_property,         # Asset & Property top driver or impact > 25
    rule_traffic_transit,        # Traffic & Transit impact > 20
    rule_safety_sop,             # Safety & SOP Violation impact > 20
    rule_reporting_lag,          # p90 lag > 30 days
    rule_process_deviations,     # Safety & SOP Violation trending up
    rule_generic_fallback,       # always last
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
    drivers   : List of driver dicts (from compute_drivers_for_site).
    site_data : Dict with site context (total_incidents_qtr, delta_qtr_pct,
                reporting_lag_p90, site, quarter, business_unit).
    rules     : Override the default RULES list (useful for testing).

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
