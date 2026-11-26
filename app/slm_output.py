"""Validate a small model's recommendation; never execute it."""
import json


def validate_output(raw, allowed_evidence):
    if not isinstance(raw, str) or len(raw) > 8192:
        raise ValueError('Invalid model response size')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    data = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(data, dict) or set(data) != {'action', 'evidence_id'}:
        raise ValueError('Unexpected response schema')
    action, evidence = data['action'], data['evidence_id']
    if not isinstance(action, str) or action not in ('review', 'reuse_approved', 'abstain'):
        raise ValueError('Unsupported action')
    if action == 'reuse_approved':
        if not isinstance(evidence, str) or not evidence or evidence not in allowed_evidence:
            raise ValueError('Unknown evidence')
    elif evidence is not None:
        raise ValueError('Unexpected evidence')
    return data
