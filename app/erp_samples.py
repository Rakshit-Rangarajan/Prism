"""Reproducible synthetic ERP sources shared by SQLite and real MySQL demos."""
import random
import sqlite3
from pathlib import Path
from .database_demo import sqlite_connection

SCHEMA = {
    "vendors": "id INTEGER PRIMARY KEY, name TEXT, email TEXT, country_code TEXT, tax_id TEXT, reconciliation_account TEXT",
    "materials": "id INTEGER PRIMARY KEY, description TEXT, uom TEXT, price TEXT, currency_code TEXT",
    "invoices": "id INTEGER PRIMARY KEY, vendor_id INTEGER, amount TEXT, currency_code TEXT, posting_date TEXT, cost_center TEXT",
}


def records(batch=1, rows=80):
    rng = random.Random(7300 + batch)
    vendors, materials, invoices = [], [], []
    for i in range(1, rows + 1):
        vendors.append((i, f"  {rng.choice(['Orion', 'Atlas', 'Meridian', 'Nova'])} Components {i}  ",
                        f" SALES{i}@VENDOR.EXAMPLE.TEST ", rng.choice([' in ', ' us ', 'DE', 'ZZ']),
                        '' if i % 9 == 0 else f"SYNTH-TAX-{i:05d}", '' if i % 11 == 0 else '160000'))
        materials.append((i, f" Precision part {i} ", rng.choice(['pieces', 'kilograms', 'meters', 'EA', '???']),
                          f"{rng.randint(1, 90):d}.50", rng.choice([' usd ', ' eur ', 'INR', 'XXX'])))
        # Recurrent US-locale amounts plus randomized values; invalids remain visible.
        amount = f"${rng.randint(1, 9)},{rng.randint(100, 999)}.50" if i % 3 else rng.choice(['invalid', '-40', '0'])
        invoices.append((i, rows + 10 if i % 13 == 0 else i, amount, ' usd ',
                         '2026-02-30' if i % 10 == 0 else f"2026-11-{1 + i % 27:02d}",
                         '' if i % 7 == 0 else rng.choice(['CC100', 'CC200', 'UNKNOWN'])))
    # Duplicate business records with different surrogate IDs; never auto-merge.
    vendors.append((rows + 1, *vendors[0][1:]))
    return dict(vendors=vendors, materials=materials, invoices=invoices)


def generate(path, batch=1, rows=80):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    with sqlite_connection(path) as db:
        for table, ddl in SCHEMA.items():
            db.execute(f'CREATE TABLE "{table}" ({ddl})')
        for table, values in records(batch, rows).items():
            db.executemany(f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in values[0])})', values)
    return path
