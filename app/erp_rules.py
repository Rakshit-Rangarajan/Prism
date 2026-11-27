"""Finite transformation language. Model text is never executable Python or SQL."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .database_demo import inspect_db, ident


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    table: str = Field(min_length=1, max_length=100)
    column: str = Field(min_length=1, max_length=100)
    operation: Literal['trim', 'blank_to_null', 'uppercase', 'email_lower', 'decimal_us', 'map_values']
    mapping: dict[str, str] = Field(default_factory=dict, max_length=30)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode='after')
    def validate_mapping(self):
        if (self.operation == 'map_values') != bool(self.mapping):
            raise ValueError('Only map_values accepts a nonempty mapping')
        if any(not k or len(k) > 80 or len(v) > 80 for k, v in self.mapping.items()):
            raise ValueError('Mapping entries must be bounded strings')
        return self


class Classification(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    table: str = Field(min_length=1, max_length=100)
    domain: Literal['vendor', 'material', 'finance', 'customer', 'other']
    rationale: str = Field(min_length=3, max_length=300)


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_table: str = Field(min_length=1, max_length=100)
    source_column: str = Field(min_length=1, max_length=100)
    target_object: str = Field(min_length=1, max_length=100)
    target_field: str = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=3, max_length=300)


class Advice(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    summary: str = Field(min_length=3, max_length=1000)
    rules: list[Rule] = Field(max_length=40)
    risks: list[str] = Field(max_length=20)
    classifications: list[Classification] = Field(default_factory=list, max_length=20)
    field_mappings: list[FieldMapping] = Field(default_factory=list, max_length=20)


def candidate_rules(db, report):
    """Offer only useful finite operations and the explicit synthetic UOM crosswalk."""
    candidates = []
    for issue in report['issues']:
        if issue['protected']:
            continue
        table, column = issue['table'], issue['column']
        operations = []
        if issue['counts'].get('whitespace'):
            operations.append(('trim', {}, 'Trim surrounding whitespace; preserve empty strings'))
        if column in ('country_code', 'currency_code', 'uom', 'unit_code'):
            operations.append(('uppercase', {}, 'Normalize the case of code values; retain unknown codes'))
        if column in ('amount', 'price', 'unit_price'):
            operations.append(('decimal_us', {}, 'Parse explicit US decimal amounts; preserve invalid and negative amounts'))
        if column in ('uom', 'unit_code'):
            operations.append(('map_values', {'pieces': 'EA', 'kilograms': 'KG', 'meters': 'M'}, 'Apply the synthetic ERP unit crosswalk'))
        values = [r[0] for r in db.execute(f'SELECT DISTINCT {ident(column)} FROM {ident(table)}')]
        for operation, mapping, reason in operations:
            rule = Rule(table=table, column=column, operation=operation, mapping=mapping, reason=reason)
            if any(transform(v, rule) != v for v in values):
                candidates.append(rule)
    return candidates[:40]


US_AMOUNT = re.compile(r'^\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?$')
COUNTRIES = {'IN', 'US', 'DE', 'GB', 'FR', 'SG', 'AU', 'CA'}
CURRENCIES = {'INR', 'USD', 'EUR', 'GBP', 'SGD', 'AUD', 'CAD'}
UNITS = {'EA', 'KG', 'M', 'L', 'BOX'}


def transform(value, rule):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if rule.operation == 'trim':
        return text if text else value
    if rule.operation == 'blank_to_null':
        return None if not text else value
    if rule.operation == 'uppercase':
        return text.upper()
    if rule.operation == 'email_lower':
        # Preserve local-part case; only domain names are case insensitive.
        local, sep, domain = text.partition('@')
        return local + sep + domain.lower() if sep else value
    if rule.operation == 'decimal_us':
        return str(Decimal(text.replace('$', '').replace(',', ''))) if US_AMOUNT.fullmatch(text) else value
    if rule.operation == 'map_values':
        return rule.mapping.get(text, value)
    raise ValueError('Unknown operation')


def validate_rules(db, rules):
    catalog = {t['table']: {c['column']: c for c in t['columns']} for t in inspect_db(db)}
    seen = set()
    for r in rules:
        col = catalog.get(r.table, {}).get(r.column)
        if not col or not col['trim_eligible']:
            raise ValueError(f'Protected or unknown field: {r.table}.{r.column}')
        if r.operation == 'blank_to_null' and not col['blank_to_null_eligible']:
            raise ValueError('Required fields cannot become NULL')
        field = r.column.casefold()
        allowed = {
            'uppercase': field in ('country_code', 'currency_code', 'uom', 'unit_code'),
            'decimal_us': field in ('amount', 'price', 'unit_price'),
            'email_lower': field == 'email',
            'map_values': field in ('country_code', 'currency_code', 'uom', 'unit_code', 'cost_center', 'reconciliation_account'),
        }
        if r.operation in allowed and not allowed[r.operation]:
            raise ValueError('Operation does not match field semantics')
        if r.operation == 'map_values':
            vocabulary = {'country_code': COUNTRIES, 'currency_code': CURRENCIES, 'uom': UNITS, 'unit_code': UNITS}.get(field)
            if vocabulary and not set(r.mapping.values()) <= vocabulary:
                raise ValueError('Mapping target outside ERP vocabulary')
        key = (r.table, r.column, r.operation)
        if key in seen:
            raise ValueError('Duplicate transformation')
        seen.add(key)


def execute(db, rules):
    validate_rules(db, rules)
    audit = []
    # Crosswalks consume source spellings before code uppercasing. Canonical
    # stages make model, edited and retrieved plans behave identically.
    stages = {'trim': 0, 'blank_to_null': 1, 'map_values': 2, 'uppercase': 3, 'decimal_us': 4, 'email_lower': 5}
    for r in sorted(rules, key=lambda rule: stages[rule.operation]):
        table, column = ident(r.table), ident(r.column)
        values = db.execute(f'SELECT DISTINCT {column} FROM {table}').fetchall()
        changed = 0
        # CASE avoids cascading a mapping A->B then B->C within one operation.
        pairs = [(transform(v, r), v) for (v,) in values if transform(v, r) != v]
        if pairs:
            cases = ' '.join('WHEN ? THEN ?' for _ in pairs)
            params = [x for new, old in pairs for x in (old, new)]
            changed = sum(db.execute(f'SELECT count(*) FROM {table} WHERE {column} IS ?', (old,)).fetchone()[0] for _, old in pairs)
            db.execute(f'UPDATE {table} SET {column}=CASE {column} {cases} ELSE {column} END', params)
        audit.append({**r.model_dump(), 'changed_cells': changed})
    if db.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('Foreign key validation failed')
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Database integrity check failed')
    return audit


def quality(db):
    tables = inspect_db(db)
    issues, cells = [], 0
    for t in tables:
        table = t['table']
        for col in t['columns']:
            field = col['column']
            values = db.execute(f'SELECT {ident(field)} FROM {ident(table)}').fetchall()
            counts = {}
            samples = []
            for (v,) in values:
                cells += 1
                errors = []
                if v is None or (isinstance(v, str) and not v.strip()):
                    errors.append('missing')
                if isinstance(v, str) and v != v.strip():
                    errors.append('whitespace')
                text = str(v).strip() if v is not None else ''
                vocabulary = {'country_code': COUNTRIES, 'currency_code': CURRENCIES, 'uom': UNITS}.get(field)
                if vocabulary and text and text not in vocabulary:
                    errors.append('invalid_code')
                if field in ('amount', 'price') and text:
                    try:
                        number = Decimal(text)
                        if not number.is_finite() or number < 0:
                            errors.append('invalid_amount')
                    except InvalidOperation:
                        errors.append('invalid_amount')
                if field == 'posting_date' and text:
                    try:
                        date.fromisoformat(text)
                    except ValueError:
                        errors.append('invalid_date')
                if field == 'email' and text and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', text):
                    errors.append('invalid_email')
                if field == 'cost_center' and text and text not in ('CC100', 'CC200'):
                    errors.append('unknown_cost_center')
                for error in errors:
                    counts[error] = counts.get(error, 0) + 1
                if errors and len(samples) < 5 and isinstance(v, (str, int, float, type(None))):
                    samples.append(v)
            if counts:
                issues.append({'table': table, 'column': field, 'counts': counts, 'examples': samples,
                               'protected': not col['trim_eligible']})
    names = {t['table'] for t in tables}
    orphans = 0
    if {'invoices', 'vendors'} <= names:
        invoice_cols = {c['column'] for t in tables if t['table'] == 'invoices' for c in t['columns']}
        vendor_cols = {c['column'] for t in tables if t['table'] == 'vendors' for c in t['columns']}
        if 'vendor_id' in invoice_cols and 'id' in vendor_cols:
            orphans = db.execute('SELECT count(*) FROM invoices i WHERE NOT EXISTS (SELECT 1 FROM vendors v WHERE v.id=i.vendor_id)').fetchone()[0]
    findings = sum(sum(i['counts'].values()) for i in issues)
    return {'tables': tables, 'issues': issues, 'issue_count': findings, 'cells': cells,
            'quality_score': round(100 * max(0, 1 - findings / max(cells, 1)), 2),
            'duplicate_candidates': sum(t['duplicate_nonkey_rows'] for t in tables),
            'orphan_invoices': orphans,
            'validation_scope': 'Demo ERP vocabularies; findings can overlap. Duplicates, orphan references, invalid dates and unknown financial mappings require review.'}
