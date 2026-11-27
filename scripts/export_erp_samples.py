"""Export identical deliberately messy ERP records for SQLite, MySQL and SSMS."""
import argparse
import hashlib
import json
from pathlib import Path
from app.database_demo import sqlite_connection
from app.erp_samples import SCHEMA, generate, records

DATABASE = 'prism_erp_sample'


def literal(value, dialect):
    if value is None:
        return 'NULL'
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if dialect == 'mysql':
        text = text.replace('\\', '\\\\')
    return ('N' if dialect == 'sqlserver' else '') + "'" + text.replace("'", "''") + "'"


def export_samples(output, batch=1):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    names = ('prism-erp-source.sqlite', 'prism-erp-sqlite.sql', 'prism-erp-mysql.sql', 'prism-erp-sqlserver.sql', 'sample-manifest.json', 'README.txt')
    if any((output / name).exists() for name in names):
        raise FileExistsError('Sample files already exist; choose a new output directory')
    path = generate(output / names[0], batch)
    with sqlite_connection(path) as db:
        (output / names[1]).write_text('\n'.join(db.iterdump()) + '\n', encoding='utf-8')
    data = records(batch)
    mysql = [
        '-- PRISM synthetic ERP source. Import using phpMyAdmin or the mysql client.',
        '-- Dedicated schema only. Existing tables cause an error; nothing is dropped.',
        '-- Amounts and dates intentionally remain text to preserve migration defects.',
        'SET NAMES utf8mb4;',
        f'CREATE DATABASE IF NOT EXISTS `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;',
        f'USE `{DATABASE}`;',
    ]
    sqlserver = [
        '-- PRISM synthetic ERP source. Run in SQL Server Management Studio.',
        '-- Existing tables cause a deliberate error; nothing is dropped.',
        '-- Dates and amounts remain NVARCHAR because this is messy staging data.',
        f"IF DB_ID(N'{DATABASE}') IS NULL EXEC(N'CREATE DATABASE [{DATABASE}]');", 'GO',
        f'USE [{DATABASE}];', 'GO', 'SET XACT_ABORT ON;', 'BEGIN TRANSACTION;',
        "IF OBJECT_ID(N'dbo.vendors', N'U') IS NOT NULL OR OBJECT_ID(N'dbo.materials', N'U') IS NOT NULL OR OBJECT_ID(N'dbo.invoices', N'U') IS NOT NULL",
        "    THROW 50001, 'PRISM requires an empty dedicated demo database. Existing data was not changed.', 1;",
    ]
    for table, ddl in SCHEMA.items():
        mysql.append(f'CREATE TABLE `{table}` ({ddl}) ENGINE=InnoDB;')
        definitions = ddl.replace('INTEGER', 'INT').replace('TEXT', 'NVARCHAR(255)')
        sqlserver.append(f'CREATE TABLE [dbo].[{table}] ({definitions});')
    mysql.append('START TRANSACTION;')
    for table, values in data.items():
        mysql.append(f'INSERT INTO `{table}` VALUES\n' + ',\n'.join('(' + ', '.join(literal(v, 'mysql') for v in row) + ')' for row in values) + ';')
        sqlserver.append(f'INSERT INTO [dbo].[{table}] VALUES\n' + ',\n'.join('(' + ', '.join(literal(v, 'sqlserver') for v in row) + ')' for row in values) + ';')
    mysql.extend(['COMMIT;', '-- Review queries', 'SELECT COUNT(*) AS vendor_rows FROM vendors;', 'SELECT COUNT(*) AS material_rows FROM materials;', 'SELECT COUNT(*) AS invoice_rows FROM invoices;'])
    sqlserver.extend(['COMMIT TRANSACTION;', 'GO', 'SELECT COUNT(*) AS vendor_rows FROM dbo.vendors;', 'SELECT COUNT(*) AS material_rows FROM dbo.materials;', 'SELECT COUNT(*) AS invoice_rows FROM dbo.invoices;', 'GO'])
    (output / names[2]).write_text('\n\n'.join(mysql) + '\n', encoding='utf-8')
    (output / names[3]).write_text('\n\n'.join(sqlserver) + '\n', encoding='utf-8')
    manifest = {'synthetic': True, 'batch': batch, 'database': DATABASE,
                'row_counts': {table: len(values) for table, values in data.items()},
                'issues': ['Surrounding spaces', 'Mixed-case codes', 'Missing tax IDs and reconciliation accounts',
                           'Duplicate vendor business records', 'Legacy unit names', 'Unknown codes',
                           'Dollar signs and thousands separators', 'Invalid or negative amounts',
                           'Impossible dates', 'Missing or unknown cost centres', 'Orphan invoice vendor references'],
                'foreign_keys': 'Intentionally unenforced in source staging so orphan records can be demonstrated.',
                'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in names[:4]}}
    (output / names[4]).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / names[5]).write_text('''PRISM synthetic ERP source database

Contents: 81 vendors, 80 materials, 80 invoices. These records deliberately
contain migration problems. Amounts and dates are text so import does not
silently discard invalid source values. No script drops existing data.

SQLite (quickest):
  Open prism-erp-source.sqlite in DB Browser for SQLite, or upload it in
  PRISM > Local AI & Learning / Migration Studio.
  Alternatively import prism-erp-sqlite.sql into a NEW empty SQLite database.
  CLI: sqlite3 my-prism-source.sqlite ".read prism-erp-sqlite.sql"

MySQL / phpMyAdmin:
  Log in to your LOCAL MySQL server with permission to create a database.
  Choose Import, select prism-erp-mysql.sql and execute it.
  The script creates and selects prism_erp_sample.
  If your hosting account cannot create databases, select a NEW empty database
  and omit the CREATE DATABASE and USE statements before importing.
  PRISM's direct connector uses server-side PRISM_MYSQL_HOST, PORT, DATABASE,
  USER and PASSWORD settings. Create/grant a read-only SELECT user for that
  schema; do not configure PRISM with the admin account.
  phpMyAdmin is an import UI, not a separate database engine.

SQL Server / SSMS:
  Connect SSMS to your SQL Server instance, open prism-erp-sqlserver.sql,
  and click Execute. A login with CREATE DATABASE permission is required.
  The script creates prism_erp_sample and uses GO batch separators.
  PRISM does not yet have a direct SQL Server connector. For the complete
  working PRISM demonstration, use the identical SQLite or MySQL sample.

For repeat imports, choose another NEW empty database or a fresh sample folder.
Do not clean these files before the demo. PRISM generates a separate target.
''', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch', type=int, choices=range(1, 21), default=1)
    args = parser.parse_args()
    result = export_samples(args.output, args.batch)
    print(json.dumps({'directory': str(args.output.resolve()), 'row_counts': result['row_counts']}))
