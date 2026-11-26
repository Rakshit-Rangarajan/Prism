"""Convert approved export examples into constrained, context-local SLM targets."""
import json


def build_training_pair(example):
    entry, version = example['entry_id'], example['version']
    if any(type(x) is not int or x < 1 for x in (entry, version)):
        raise ValueError('Invalid versioned identity')
    # The model selects a retrieved candidate, never invents a database ID.
    candidate = 'candidate_1'
    source = example['output']
    for key in ('recommendation', 'evidence'):
        if not isinstance(source[key], str) or not source[key].strip():
            raise ValueError('Missing approved context')
    return {
        'input': {'query': example['input'], 'candidates': [
            {'id': candidate, 'resolution': source['recommendation']}]},
        'output': {'action': 'reuse_approved', 'evidence_id': candidate},
        'provenance': {'entry_id': entry, 'version': version},
    }


def resolve_selection(output, candidates):
    """Call only after validate_output; return provenance, not an operation."""
    if output['action'] != 'reuse_approved':
        return None
    return candidates[output['evidence_id']]
