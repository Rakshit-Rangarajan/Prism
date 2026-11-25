"""Deterministic, tenant-scoped training examples; no model or network calls."""
import json
import hashlib


def export_examples(rows, tenant_id):
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError('Tenant required')
    examples = {}
    for row in rows:
        if row.get('tenant_id') != tenant_id:
            raise PermissionError('Cross-tenant training input')
        if row.get('state') != 'approved':
            continue
        if not row.get('reviewer') or not row.get('reviewed_at'):
            raise ValueError('Approval provenance required')
        entry_id, version = row.get('id'), row.get('version')
        if type(entry_id) is not int or entry_id < 1 or type(version) is not int or version < 1:
            raise ValueError('Invalid entry identity')
        fields = {}
        for key, maximum in [('domain',80),('target_object',100),('title',200),('resolution',4000),('evidence',500)]:
            value = row.get(key)
            if not isinstance(value,str) or not value.strip() or len(value)>maximum:
                raise ValueError('Invalid training field: '+key)
            fields[key] = value
        example = {'entry_id':entry_id,'version':version,'input':{k:fields[k] for k in ('domain','target_object','title')},'output':{'recommendation':fields['resolution'],'evidence':fields['evidence']}}
        if entry_id in examples:
            raise ValueError('Duplicate approved entry')
        examples[entry_id] = example
    payload = ''.join(json.dumps(examples[k],sort_keys=True,ensure_ascii=False)+'\n' for k in sorted(examples))
    return {'jsonl':payload,'count':len(examples),'sha256':hashlib.sha256(payload.encode('utf-8')).hexdigest()}
