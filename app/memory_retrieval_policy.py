"""Fail-closed, version-aware policy for PRISM Migration Memory retrieval.

Caller MUST fetch all scoped revisions with a database-enforced tenant predicate.
This is a reusable guard, not an authenticated PostgreSQL retrieval endpoint.
"""
from collections import defaultdict

class MemoryPolicyError(ValueError):
    pass

def select_current_approved(entries, *, tenant_id, domain, target_object):
    if not all(isinstance(x, str) and x.strip() for x in (tenant_id, domain, target_object)):
        raise MemoryPolicyError('Tenant, domain and target object are required')
    entries = list(entries)
    by_id = {}
    for row in entries:
        if row.get('tenant_id') != tenant_id or row.get('domain') != domain or row.get('target_object') != target_object:
            raise MemoryPolicyError('Scope mismatch in candidate set')
        identifier = row.get('id')
        if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0 or identifier in by_id:
            raise MemoryPolicyError('Invalid or duplicate memory identifier')
        if row.get('state') not in {'draft', 'approved', 'rejected', 'superseded'}:
            raise MemoryPolicyError('Unknown approval state')
        version = row.get('version')
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise MemoryPolicyError('Invalid version')
        by_id[identifier] = row
    children = defaultdict(list)
    for row in entries:
        parent_id = row.get('supersedes_id')
        if parent_id is None:
            if row['version'] != 1:
                raise MemoryPolicyError('Root must be version one')
            continue
        if parent_id not in by_id or parent_id == row['id']:
            raise MemoryPolicyError('Missing or self-referential predecessor')
        parent = by_id[parent_id]
        if row['version'] != parent['version'] + 1:
            raise MemoryPolicyError('Nonconsecutive revision')
        children[parent_id].append(row)
    for row in entries:
        seen = set()
        current = row
        while current.get('supersedes_id') is not None:
            if current['id'] in seen:
                raise MemoryPolicyError('Revision cycle')
            seen.add(current['id'])
            current = by_id[current['supersedes_id']]
    for parent_id, descendants in children.items():
        if sum(child['state'] == 'approved' for child in descendants) > 1:
            raise MemoryPolicyError('Conflicting approved successors')
        if any(child['state'] == 'approved' for child in descendants) and by_id[parent_id]['state'] != 'superseded':
            raise MemoryPolicyError('Approved successor has active predecessor')
    return sorted((row for row in entries if row['state'] == 'approved'), key=lambda r: r['id'])
