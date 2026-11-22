"""Read-only governance preflight for synthetic Migration Memory.

This is an integrity report, NOT proof of tenant authorization or PostgreSQL
readiness. The caller must already be authenticated by the API router.
"""
from collections import Counter, defaultdict


def evaluate_memory_integrity(entries, events):
    entries = [dict(row) for row in entries]
    events = [dict(row) for row in events]
    by_id = {row["id"]: row for row in entries}
    findings = []
    def issue(code, entry_id=None):
        findings.append({"code": code, "entry_id": entry_id})
    if len(by_id) != len(entries):
        issue("duplicate_entry_id")
    drafts = Counter()
    successors = defaultdict(list)
    for entry in entries:
        identifier = entry["id"]
        state = entry["state"]
        parent_id = entry.get("supersedes_id")
        if state not in ("draft", "approved", "rejected", "superseded"):
            issue("invalid_state", identifier)
        if int(entry["version"]) < 1:
            issue("invalid_version", identifier)
        if state in ("approved", "rejected", "superseded") and (not entry.get("reviewer") or not entry.get("reviewed_at")):
            # Superseded entries must retain their original approval reviewer.
            issue("missing_review_metadata", identifier)
        if parent_id is not None:
            parent = by_id.get(parent_id)
            if parent is None:
                issue("orphan_predecessor", identifier)
            else:
                if parent_id == identifier:
                    issue("self_reference", identifier)
                if parent["domain"] != entry["domain"] or parent["target_object"] != entry["target_object"]:
                    issue("cross_scope_revision", identifier)
                if entry["version"] != parent["version"] + 1:
                    issue("version_gap", identifier)
            successors[parent_id].append(entry)
            if state == "draft":
                drafts[parent_id] += 1
    for parent_id, count in drafts.items():
        if count > 1:
            issue("parallel_draft_successors", parent_id)
    for parent_id, children in successors.items():
        if sum(child["state"] in ("approved", "superseded") for child in children) > 1:
            issue("competing_accepted_successors", parent_id)
    for entry in entries:
        seen = set()
        cursor = entry
        while cursor and cursor.get("supersedes_id") is not None:
            if cursor["id"] in seen:
                issue("revision_cycle", entry["id"])
                break
            seen.add(cursor["id"])
            cursor = by_id.get(cursor["supersedes_id"])
    for event in events:
        if event["entry_id"] not in by_id:
            issue("orphan_event", event["entry_id"])
    # A current approved version cannot have an accepted successor.
    for entry in entries:
        if entry["state"] == "approved" and any(
            child["state"] == "approved" for child in successors[entry["id"]]
        ):
            issue("unretired_predecessor", entry["id"])
    counts = dict(sorted(Counter(row["state"] for row in entries).items()))
    return {
        "mode": "synthetic-demo",
        "ready_for_migration": len(findings) == 0,
        "entry_count": len(entries),
        "event_count": len(events),
        "state_counts": counts,
        "findings": sorted(findings, key=lambda x: (x["code"], x["entry_id"] if x["entry_id"] is not None else -1)),
        "scope": "SQLite governance consistency only; not tenant authorization, backup verification or PostgreSQL acceptance",
    }
