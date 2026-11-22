import contextlib
import unittest
from unittest.mock import patch
from scripts.postgres_preflight import inspect_connection, inspect_postgres, main

class FakeConnection:
    def __init__(self, version='160002', vector=True, tables=None, counts=None):
        self.version=version
        self.vector=vector
        self.tables=tables or {}
        self.counts=counts or {}
        self.statements=[]
    @contextlib.contextmanager
    def transaction(self):
        yield self
    def execute(self,sql,params=None):
        self.statements.append((sql,params))
        if sql=='SET TRANSACTION READ ONLY':return FakeCursor([])
        if sql=='SHOW server_version_num':return FakeCursor([(self.version,)])
        if 'pg_catalog.pg_extension' in sql:return FakeCursor([('vector',)] if self.vector else [])
        if sql.startswith('SELECT to_regclass'):
            name=params[0].split('.')[-1]
            return FakeCursor([(name if self.tables.get(name) else None,)])
        if sql.startswith('SELECT COUNT(*) FROM public.'):
            name=sql.split('.')[-1]
            return FakeCursor([(self.counts[name],)])
        raise AssertionError('Unexpected SQL: '+sql)
class FakeCursor:
    def __init__(self,rows):self.rows=rows
    def fetchone(self):return self.rows[0]
    def fetchall(self):return self.rows

class PreflightTests(unittest.TestCase):
    def test_empty_database_readiness(self):
        c=FakeConnection()
        r=inspect_connection(c)
        self.assertTrue(r['ready_for_offline_migration'])
        self.assertFalse(r['ready_for_semantic_retrieval'])
        self.assertTrue(r['pgvector_installed'])
        self.assertEqual(c.statements[0][0],'SET TRANSACTION READ ONLY')
        self.assertTrue(all(not q.upper().startswith(('INSERT','UPDATE','DELETE','CREATE','DROP','ALTER')) for q,_ in c.statements))
    def test_populated_target_fails_closed(self):
        c=FakeConnection(tables={'memory_entries':True,'memory_events':True},counts={'memory_entries':1,'memory_events':0})
        r=inspect_connection(c)
        self.assertFalse(r['empty_migration_target'])
        self.assertFalse(r['ready_for_offline_migration'])
    def test_older_postgres_not_ready(self):
        self.assertFalse(inspect_connection(FakeConnection(version='120001'))['postgres_supported'])
    def test_missing_vector_extension_reported(self):
        self.assertFalse(inspect_connection(FakeConnection(vector=False))['pgvector_installed'])
    def test_missing_dsn_fails_before_driver_import(self):
        with self.assertRaisesRegex(ValueError,'PRISM_POSTGRES_DSN'):
            inspect_postgres('')
    def test_cli_redacts_connection_failure(self):
        with patch('scripts.postgres_preflight.inspect_postgres',side_effect=RuntimeError('password=SECRET host=private')):
            from io import StringIO
            with patch('sys.stdout',new_callable=StringIO) as out:
                self.assertEqual(main([]),2)
            self.assertNotIn('SECRET',out.getvalue())
            self.assertNotIn('private',out.getvalue())

if __name__=='__main__':unittest.main()
