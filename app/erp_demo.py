"""Authenticated synthetic ERP learning demo API.

Isolated SQLite storage; deliberately not a real ERP connector.
"""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from demo.erp_learning_pipeline import Demo, SCENARIOS, sample

router = APIRouter(prefix="/api/demo/erp", tags=["Synthetic ERP demo"])


def _open():
    # Fixed server configuration, never a request-provided filesystem path.
    path = Path(os.getenv("PRISM_ERP_DEMO_DB", "/tmp/prism_erp_learning.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return Demo(path)


class RunRequest(BaseModel):
    apply: bool = False


class ApprovalRequest(BaseModel):
    signature: str
    confirmation: str


@router.get("/scenarios")
def scenarios():
    return {"synthetic": True, "count": len(SCENARIOS),
            "scenarios": [
                {"index": i + 1, "name": scenario, "source": sample(scenario, i + 1)}
                for i, scenario in enumerate(SCENARIOS)
            ]}


@router.post("/run")
def run_demo(request: RunRequest):
    engine = _open()
    try:
        results = engine.run(apply=request.apply)
        return {"synthetic": True, "mode": "apply" if request.apply else "preview",
                "results": results, "reconciliation": engine.report(results)}
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
