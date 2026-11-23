"""Read-only security posture audit for an *existing* PRISM PostgreSQL schema.

Never grants permissions, changes schema, fetches enterprise rows or asserts
production readiness. Role and RLS checks must be run with the actual runtime
database role, not an administrator.
"""
import argparse
import json
import os
import re

TABLES = ("memory_entries", "memory_events", "memory_vectors")
REQUIRED_TENANT_COLUMN = "tenant_id"

def audit_connection(conn):
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        role = conn.execute(
            "SELECT rolname, rolsuper, rolbypassrls FROM pg_catalog.pg_roles "
            "WHERE rolname = current_user"
        ).fetchone()
        if not role:
            raise RuntimeError("Current PostgreSQL role not found")
        role_name, superuser, bypass_rls = role
        table_rows = conn.execute(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
            "pg_catalog.pg_get_userbyid(c.relowner) = current_user AS is_owner "
            "FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r','p') "
            "AND c.relname = ANY(%s)",
            (list(TABLES),)
        ).fetchall()
        column_rows = conn.execute(
            "SELECT table_name, column_name, is_nullable "
            "FROM information_schema.columns WHERE table_schema='public' "
            "AND table_name = ANY(%s) AND column_name='tenant_id'",
            (list(TABLES),)
        ).fetchall()
        policy_rows = conn.execute(
            "SELECT tablename, policyname, cmd, qual, with_check "
            "FROM pg_catalog.pg_policies WHERE schemaname='public' "
            "AND tablename = ANY(%s)",
            (list(TABLES),)
        ).fetchall()
        tables = {}
        relations = {name:(bool(enabled),bool(forced),bool(owner))
                     for name,enabled,forced,owner in table_rows}
        columns = {name:nullable for name,column,nullable in column_rows
                   if column == REQUIRED_TENANT_COLUMN}
        policies = {}
        for name,policy,cmd,qual,check in policy_rows:
            policies.setdefault(name,[]).append((policy,cmd,qual,check))
        for name in TABLES:
            exists = name in relations
            enabled,forced,owner = relations.get(name,(False,False,False))
            tenant_not_null = columns.get(name) == "NO"
            # Presence of a policy is not evidence that it correctly scopes access.
            has_policy = bool(policies.get(name))
            issues=[]
            # PostgreSQL OR-combines permissive policies: an unconditional
            # USING or WITH CHECK clause is a dangerous red flag.
            for policy_name, command, using_expr, check_expr in policies.get(name, []):
                for expression in (using_expr, check_expr):
                    if expression is not None and re.fullmatch(r"\s*\(*\s*true\s*\)*\s*", expression, re.I):
                        issues.append("unrestricted_policy_expression")
                        break
            if not exists:issues.append("table_missing")
            if exists and not enabled:issues.append("rls_disabled")
            if exists and not forced:issues.append("rls_not_forced")
            if exists and not tenant_not_null:issues.append("tenant_id_not_null_missing")
            if exists and not has_policy:issues.append("policy_missing")
            if exists and owner and not forced:issues.append("owner_can_bypass_rls")
            tables[name]={"exists":exists,"rls_enabled":enabled,"rls_forced":forced,
                          "tenant_not_null":tenant_not_null,"policy_count":len(policies.get(name,[])),
                          "issues":issues}
        role_safe = not superuser and not bypass_rls
        structural = role_safe and all(not v["issues"] for v in tables.values())
        return {"mode":"read_only","role":{"name":role_name,"superuser":bool(superuser),
                "bypass_rls":bool(bypass_rls),"safe_for_rls":role_safe},
                "tables":tables,"structural_prerequisites_pass":structural,
                "tenant_isolation_verified":False,
                "limitations":["Policy expressions, grants, tenant identity and transaction context are not verified.",
                               "Run actual cross-tenant positive/negative tests with the restricted runtime role.",
                               "A passing structural audit does not authorize enterprise data or production use."]}

def audit_postgres(dsn):
    if not dsn:raise ValueError("PRISM_POSTGRES_DSN must be set")
    try:import psycopg
    except ImportError as exc:raise RuntimeError("Optional psycopg v3 required") from exc
    with psycopg.connect(dsn,options="-c default_transaction_read_only=on",connect_timeout=5) as conn:
        return audit_connection(conn)

def main(argv=None):
    parser=argparse.ArgumentParser(description="Read-only PRISM PostgreSQL RLS structural audit")
    parser.parse_args(argv)
    try:result=audit_postgres(os.getenv("PRISM_POSTGRES_DSN"))
    except Exception as exc:
        print(json.dumps({"status":"blocked","reason":type(exc).__name__,
                          "message":"RLS audit could not complete; inspect connection securely."}))
        return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result["structural_prerequisites_pass"] else 1

if __name__=="__main__":raise SystemExit(main())
