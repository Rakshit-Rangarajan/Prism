import unittest
from app.memory_retrieval_policy import MemoryPolicyError, select_current_approved

SCOPE={'tenant_id':'synthetic-company-a','domain':'Vendor','target_object':'SUPPLIER'}
def row(i,state='approved',version=1,parent=None,**kw):
    return dict(SCOPE,id=i,state=state,version=version,supersedes_id=parent,**kw)
def select(rows,**scope):
    return select_current_approved(rows,**(scope or SCOPE))
class TestPolicy(unittest.TestCase):
    def test_approved_only(self):
        self.assertEqual([x['id'] for x in select([row(1),row(2,'draft'),row(3,'rejected')])],[1])
    def test_supersession(self):
        self.assertEqual([x['id'] for x in select([row(1,'superseded'),row(2,version=2,parent=1)])],[2])
    def test_reject_cross_tenant(self):
        with self.assertRaises(MemoryPolicyError): select([dict(row(1),tenant_id='other')])
    def test_reject_cross_object(self):
        with self.assertRaises(MemoryPolicyError): select([dict(row(1),target_object='GL_ACCOUNT')])
    def test_reject_missing_predecessor(self):
        with self.assertRaises(MemoryPolicyError): select([row(2,version=2,parent=1)])
    def test_reject_nonconsecutive_version(self):
        with self.assertRaises(MemoryPolicyError): select([row(1,'superseded'),row(2,version=3,parent=1)])
    def test_reject_conflicting_approvals(self):
        with self.assertRaises(MemoryPolicyError): select([row(1,'superseded'),row(2,version=2,parent=1),row(3,version=2,parent=1)])
    def test_reject_active_predecessor(self):
        with self.assertRaises(MemoryPolicyError): select([row(1),row(2,version=2,parent=1)])
    def test_reject_duplicate_ids(self):
        with self.assertRaises(MemoryPolicyError): select([row(1),row(1)])
    def test_require_scope(self):
        with self.assertRaises(MemoryPolicyError): select([row(1)],tenant_id='',domain='Vendor',target_object='SUPPLIER')
    def test_reject_self_cycle(self):
        with self.assertRaises(MemoryPolicyError): select([row(1,version=2,parent=1)])
    def test_draft_successor_preserves_approved(self):
        self.assertEqual([x['id'] for x in select([row(1),row(2,'draft',2,1)])],[1])
