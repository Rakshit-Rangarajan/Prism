"""Deterministic synthetic migration readiness gates.

This is an exception triage aid, not SAP certification or migration approval.
Never infer production readiness from an empty sample.
"""
from collections import Counter

SEVERITIES = ("critical", "high", "medium", "low")
BLOCKING_STATES = frozenset(("open", "reopened", "rejected"))
RESOLVED_STATES = frozenset(("approved",))
KNOWN_STATES = BLOCKING_STATES | RESOLVED_STATES

def evaluate_readiness(exceptions, *, expected_domains=()):
    """Return explainable, fail-closed gates for a snapshot of synthetic exceptions."""
    records = [dict(row) for row in exceptions]
    domains = sorted(set(expected_domains) | {r["domain"] for r in records})
    output = []
    for domain in domains:
        rows = [r for r in records if r["domain"] == domain]
        active = [r for r in rows if r["state"] in BLOCKING_STATES]
        invalid = [r for r in rows if r["state"] not in KNOWN_STATES or r["severity"] not in SEVERITIES]
        critical = [r for r in active if r["severity"] == "critical"]
        high = [r for r in active if r["severity"] == "high"]
        unknown = not rows or bool(invalid)
        # Unresolved medium/low issues do not make the domain ready; they require review.
        if unknown:
            gate = "unknown"
            reasons = ["No validated sample or unrecognized exception states/severities"]
        elif critical:
            gate = "blocked"
            reasons = [f"{len(critical)} unresolved critical exception(s)"]
        elif high:
            gate = "blocked"
            reasons = [f"{len(high)} unresolved high exception(s)"]
        elif active:
            gate = "review_required"
            reasons = [f"{len(active)} unresolved medium/low exception(s)"]
        else:
            gate = "provisional"
            reasons = ["All sampled exceptions resolved; external controls unverified"]
        output.append({
            "domain": domain, "gate": gate, "sampled_exceptions": len(rows),
            "unresolved": len(active), "critical_blockers": len(critical),
            "high_blockers": len(high),
            "blocking_exception_ids": sorted(r["id"] for r in critical + high),
            "reasons": reasons,
        })
    summary = Counter(row["gate"] for row in output)
    # The whole assessment remains unknown without any validated samples.
    overall = ("unknown" if not output or summary["unknown"] else
               "blocked" if summary["blocked"] else
               "review_required" if summary["review_required"] else "provisional")
    return {
        "synthetic": True,
        "assessment": "exception-only-preliminary",
        "certified_sap_readiness": False,
        "overall_gate": overall,
        "domain_gates": output,
        "counts": {key: summary[key] for key in ("blocked", "review_required", "provisional", "unknown")},
        "missing_controls": [
            "Approved source-to-target mapping and business sign-off",
            "Target SAP connectivity, schema and configuration validation",
            "Record-count, financial and referential-integrity reconciliation",
            "Security, data privacy, cutover and rollback evidence",
        ],
    }
