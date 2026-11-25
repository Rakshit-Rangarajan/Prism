"""Offline semantic retrieval orchestration; not a public API endpoint."""
from .local_embeddings import embed_local
from .pgvector_retrieval import retrieve_approved
from .tenant_context import VerifiedIdentity, tenant_transaction


def search_memory(connection, identity: VerifiedIdentity, *, domain: str,
                  target_object: str, query: str, limit: int = 10):
    if not isinstance(identity, VerifiedIdentity):
        raise PermissionError('Verified identity required')
    identity.validate()
    for value, maximum in ((domain, 80), (target_object, 100)):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError('Invalid memory scope')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid limit')
    vector = embed_local(query)
    with tenant_transaction(connection, identity) as scoped:
        return retrieve_approved(scoped, tenant_id=identity.tenant_id,
                                 domain=domain, target_object=target_object,
                                 embedding=vector, limit=limit)
