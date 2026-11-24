"""Self-contained, offline synthetic ERP migration demo. No production writes."""
import json
import sqlite3
from pathlib import Path

FIELDS = ("customer_id", "name", "email", "amount")
SCENARIOS = (
    "clean", "blank_name", "bad_amount", "negative_amount", "missing_id",
    "duplicate_id", "email_whitespace", "uppercase_email", "amount_whitespace",
    "currency_symbol", "comma_amount", "null_email", "invalid_email",
    "zero_amount", "name_whitespace", "id_whitespace", "bad_id_type",
    "missing_amount", "extra_field", "repeated_known_error",
)


def sample(case, index):
    row = {"customer_id": f"C{index:03d}", "name": "Acme Ltd",
           "email": "SALES@EXAMPLE.COM ", "amount": "120.50"}
    changes = {
        "blank_name": {"name": ""}, "bad_amount": {"amount": "abc"},
        "negative_amount": {"amount": "-5"}, "missing_id": {"customer_id": ""},
        "duplicate_id": {"customer_id": "C001"},
        "email_whitespace": {"email": " sales@example.com "},
        "uppercase_email": {"email": "SALES@EXAMPLE.COM"},
        "amount_whitespace": {"amount": " 120.50 "},
        "currency_symbol": {"amount": "$120.50"},
        "comma_amount": {"amount": "1,200.50"},
        "null_email": {"email": None}, "invalid_email": {"email": "not-an-email"},
        "zero_amount": {"amount": "0"}, "name_whitespace": {"name": " Acme Ltd "},
        "id_whitespace": {"customer_id": " C016 "},
        "bad_id_type": {"customer_id": 42}, "missing_amount": {"amount": None},
        "extra_field": {"legacy_code": "L1"},
        "repeated_known_error": {"amount": "$120.50"},
    }
    row.update(changes.get(case, {}))
    return row


class Demo:
    def __init__(self, db_path):
        self.db = sqlite3.connect(str(db_path))
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS lessons (
                signature TEXT PRIMARY KEY, suggestion TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0, occurrences INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS migrated (
                customer_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                email TEXT NOT NULL, amount REAL NOT NULL
            );
        """)
        self.db.commit()

    def approve(self, signature):
        with self.db:
            result = self.db.execute(
                "UPDATE lessons SET approved=1 WHERE signature=?", (signature,))
        return result.rowcount == 1

    def lesson(self, signature, suggestion):
        with self.db:
            self.db.execute("""
                INSERT INTO lessons(signature,suggestion,occurrences) VALUES(?,?,1)
                ON CONFLICT(signature) DO UPDATE SET occurrences=occurrences+1
            """, (signature, suggestion))
        return bool(self.db.execute(
            "SELECT approved FROM lessons WHERE signature=?", (signature,)
        ).fetchone()[0])

    def migrate(self, case, index, apply=False):
        raw = sample(case, index)
        row = dict(raw)
        errors, reused = [], []
        for key in ("customer_id", "name", "email"):
            if not isinstance(row.get(key), str):
                errors.append(f"{key}:invalid_type")
            else:
                row[key] = row[key].strip()
        if isinstance(row.get("email"), str):
            row["email"] = row["email"].lower()
        if not row.get("customer_id"):
            errors.append("customer_id:required")
        if not row.get("name"):
            errors.append("name:required")
        if not isinstance(row.get("email"), str) or "@" not in row["email"]:
            errors.append("email:invalid")
        amount = row.get("amount")
        if isinstance(amount, str):
            amount = amount.strip()
            if amount.startswith("$") or "," in amount:
                sig = "amount:legacy_format"
                approved = self.lesson(sig, "Strip USD symbol and thousands separators")
                if approved:
                    amount = amount.replace("$", "").replace(",", "")
                    reused.append(sig)
                else:
                    errors.append(sig)
        try:
            amount = float(amount)
            if amount < 0:
                errors.append("amount:negative")
        except (ValueError, TypeError):
            errors.append("amount:invalid")
        row["amount"] = amount if isinstance(amount, float) else None
        if errors:
            for signature in set(errors):
                if signature != "amount:legacy_format":
                    self.lesson(signature, "Review source and correct invalid field")
            return {"scenario": case, "status": "rejected", "errors": errors,
                    "reused_lessons": reused}
        if self.db.execute("SELECT 1 FROM migrated WHERE customer_id=?",
                           (row["customer_id"],)).fetchone():
            self.lesson("customer_id:duplicate", "Deduplicate source identifiers")
            return {"scenario": case, "status": "rejected",
                    "errors": ["customer_id:duplicate"], "reused_lessons": reused}
        if apply:
            with self.db:
                self.db.execute("INSERT INTO migrated VALUES(?,?,?,?)",
                                tuple(row[k] for k in FIELDS))
        return {"scenario": case, "status": "migrated" if apply else "validated",
                "record": {k: row[k] for k in FIELDS}, "reused_lessons": reused}

    def run(self, apply=False):
        return [self.migrate(case, i + 1, apply=apply)
                for i, case in enumerate(SCENARIOS)]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="prism_erp_demo.sqlite")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve-legacy-format", action="store_true")
    args = parser.parse_args()
    demo = Demo(Path(args.db))
    if args.approve_legacy_format:
        demo.lesson("amount:legacy_format", "Strip USD symbol and thousands separators")
        demo.approve("amount:legacy_format")
    results = demo.run(apply=args.apply)
    print(json.dumps({"results": results,
                      "migrated": sum(r["status"] == "migrated" for r in results),
                      "rejected": sum(r["status"] == "rejected" for r in results)},
                     indent=2))
