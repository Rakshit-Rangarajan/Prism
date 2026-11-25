"""Deterministic reconciliation for the offline synthetic ERP demonstration.

Only local data. Read-only report generation; no updates or approvals.
"""
from collections import Counter


def reconcile(results, db):
    """Summarize a run without confusing preview validations with committed writes."""
    statuses = Counter(result["status"] for result in results)
    errors = Counter(
        signature for result in results for signature in result.get("errors", [])
    )
    reused = Counter(
        signature for result in results for signature in result.get("reused_lessons", [])
    )
    lessons = db.execute(
        "SELECT signature, suggestion, approved, occurrences FROM lessons ORDER BY signature"
    ).fetchall()
    target_count = db.execute("SELECT COUNT(*) FROM migrated").fetchone()[0]
    ids = [result["record"]["customer_id"] for result in results
           if result.get("status") == "migrated"]
    return {
        "scenario_count": len(results),
        "validated_only": statuses["validated"],
        "migrated_this_run": statuses["migrated"],
        "rejected_this_run": statuses["rejected"],
        "target_total_records": target_count,
        "unique_migrated_ids_this_run": len(set(ids)),
        "reconciliation_passed": (
            len(results) == sum(statuses.values())
            and statuses["migrated"] == len(ids) == len(set(ids))
        ),
        "error_signatures": dict(sorted(errors.items())),
        "approved_rule_reuse": dict(sorted(reused.items())),
        "lessons": [
            {"signature": signature, "suggestion": suggestion,
             "approved": bool(approved), "occurrences": occurrences}
            for signature, suggestion, approved, occurrences in lessons
        ],
        "warning": (
            "Synthetic SQLite demo only; these counts do not establish "
            "enterprise migration integrity or persistent cloud storage."
        ),
    }
