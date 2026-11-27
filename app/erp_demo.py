"""Authenticated synthetic ERP learning demo API.

Isolated SQLite storage; deliberately not a real ERP connector.
"""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from demo.erp_learning_pipeline import Demo, SCENARIOS

router = APIRouter(prefix="/api/demo/erp", tags=["Synthetic ERP demo"])


def _open():
    # Fixed server configuration, never a request-provided filesystem path.
    path = Path(os.getenv("PRISM_ERP_DEMO_DB", "/tmp/prism_erp_learning.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return Demo(path)


class RunRequest(BaseModel):
    # Strict typing prevents strings such as "yes" from silently triggering a
    # target write when a preview was intended.
    apply: bool = Field(default=False, strict=True)
    batch: int = Field(default=1, ge=1, le=20, strict=True)


class ApprovalRequest(BaseModel):
    signature: str
    confirmation: str


@router.get("/scenarios")
def scenarios(batch: int = Query(default=1, ge=1, le=20)):
    return {"synthetic": True, "count": len(SCENARIOS), "batch": batch,
            "scenarios": [
                {"index": i + 1, "name": scenario, "source": Demo.batch_sample(scenario, i + 1, batch)}
                for i, scenario in enumerate(SCENARIOS)
            ]}


@router.post("/run")
def run_demo(request: RunRequest):
    engine = _open()
    try:
        results = engine.run(apply=request.apply, batch=request.batch)
        return {"synthetic": True, "mode": "apply" if request.apply else "preview",
                "batch": request.batch, "results": results, "reconciliation": engine.report(results)}
    finally:
        engine.db.close()


@router.get("/lessons")
def lessons():
    engine = _open()
    try:
        return {"synthetic": True, "lessons": engine.report([])["lessons"]}
    finally:
        engine.db.close()


@router.post("/lessons/approve")
def approve_lesson(request: ApprovalRequest):
    # Exact allow-list: never let a client authorize arbitrary corrections.
    if request.signature != "amount:legacy_format":
        raise HTTPException(422, "This demo permits only the legacy amount format rule")
    if request.confirmation != "APPROVE SYNTHETIC RULE":
        raise HTTPException(422, "Explicit synthetic-rule confirmation required")
    engine = _open()
    try:
        if not engine.approve(request.signature):
            raise HTTPException(404, "Review a run to discover the rule before approval")
        return {"synthetic": True, "signature": request.signature, "approved": True}
    finally:
        engine.db.close()


class ResetRequest(BaseModel):
    confirmation: str


@router.post("/reset")
def reset_demo(request: ResetRequest):
    """Reset only the two dedicated synthetic-demo tables for repeatable presentations."""
    if request.confirmation != "RESET SYNTHETIC DEMO":
        raise HTTPException(422, "Explicit synthetic-demo reset confirmation required")
    engine = _open()
    try:
        with engine.db:
            engine.db.execute("DELETE FROM migrated")
            engine.db.execute("DELETE FROM lessons")
        return {"synthetic": True, "reset": True,
                "message": "Synthetic ERP demo records and lessons cleared."}
    finally:
        engine.db.close()


class ExplainRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/explain")
def explain(request: ExplainRequest):
    """Use a configured local OpenAI-compatible small language model; no fallback fiction."""
    import json
    from urllib.request import Request, urlopen
    endpoint = os.getenv("PRISM_SLM_URL", "").rstrip("/")
    model = os.getenv("PRISM_SLM_MODEL", "")
    if not endpoint or not model:
        raise HTTPException(503, "Local SLM is not configured. Set PRISM_SLM_URL and PRISM_SLM_MODEL.")
    engine = _open()
    try:
        approved = [x for x in engine.report([])["lessons"] if x["approved"]]
    finally:
        engine.db.close()
    prompt = "Explain synthetic ERP migration errors using approved evidence only. Do not claim live SAP or Qlik access, invent approvals, or execute changes. If evidence is insufficient, say so. Approved lessons: " + json.dumps(approved)
    payload = json.dumps({"model": model, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": request.question}], "max_tokens": 180, "temperature": 0.2}).encode()
    try:
        req = Request(endpoint + "/chat/completions", data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=40) as response:
            answer = json.load(response)["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Empty inference")
    except Exception:
        raise HTTPException(503, "Configured SLM unavailable or returned an invalid response.")
    return {"synthetic": True, "model": model, "answer": answer, "approved_evidence": approved}
