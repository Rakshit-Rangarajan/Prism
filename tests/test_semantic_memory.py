import unittest
from unittest.mock import patch, MagicMock
from app.semantic_memory import search_memory
from app.tenant_context import VerifiedIdentity


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.identity = VerifiedIdentity('tenant-a', 'user-a', 'issuer', True)
        self.conn = MagicMock()
        self.args = dict(domain='erp', target_object='vendor', query='duplicate')

    @patch('app.semantic_memory.retrieve_approved')
    @patch('app.semantic_memory.embed_local', return_value=[1.0, 0.0])
    def test_scoped(self, embed, retrieve):
        retrieve.return_value = [{'id': 1}]
        self.assertEqual(search_memory(self.conn, self.identity, **self.args), [{'id': 1}])
        embed.assert_called_once_with('duplicate')
        retrieve.assert_called_once_with(self.conn, tenant_id='tenant-a', domain='erp', target_object='vendor', embedding=[1.0, 0.0], limit=10)
        self.conn.transaction.assert_called_once()
        self.assertEqual(self.conn.execute.call_count, 2)

    @patch('app.semantic_memory.embed_local')
    def test_unverified(self, embed):
        with self.assertRaises(PermissionError):
            search_memory(self.conn, VerifiedIdentity('tenant-a','user-a','issuer'), **self.args)
        embed.assert_not_called()
        self.conn.transaction.assert_not_called()

    @patch('app.semantic_memory.embed_local')
    def test_invalid_limit(self, embed):
        with self.assertRaises(ValueError):
            search_memory(self.conn, self.identity, limit=True, **self.args)
        embed.assert_not_called()

    @patch('app.semantic_memory.retrieve_approved')
    @patch('app.semantic_memory.embed_local', side_effect=RuntimeError('offline'))
    def test_no_fallback(self, embed, retrieve):
        with self.assertRaises(RuntimeError):
            search_memory(self.conn, self.identity, **self.args)
        retrieve.assert_not_called()
        self.conn.transaction.assert_not_called()
