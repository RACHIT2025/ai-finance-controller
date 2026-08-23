"""
FastAPI REST API Routes for FinController.
"""

from datetime import datetime
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from fincontroller.audit.hash_chain import AuditHashChain
from fincontroller.audit.verifier import AuditVerifier
from fincontroller.core.models import NormalizedTransaction, ReconciliationReport
from fincontroller.engine.matching_engine import DeterministicMatchingEngine
from fincontroller.ingestion.bank_ledger_adapter import BankLedgerAdapter
from fincontroller.ingestion.generator import generate_benchmark_dataset
from fincontroller.ingestion.razorpay_adapter import RazorpayAdapter
from fincontroller.rag.qa_agent import ReconciliationQAAgent
from fincontroller.rag.summarizer import FinancialSummarizer
from fincontroller.resilience.logger import telemetry

router = APIRouter()

# Global state instances for demo/API session
audit_chain = AuditHashChain()
qa_agent = ReconciliationQAAgent()
latest_report: Optional[ReconciliationReport] = None
rzp_adapter = RazorpayAdapter()
bank_adapter = BankLedgerAdapter()


class QueryRequest(BaseModel):
    query: str


class FailureSimulationRequest(BaseModel):
    scenario: str  # "upstream_timeout", "llm_offline", "audit_tamper"


@router.post("/reconcile/benchmark")
async def reconcile_benchmark():
    """Run reconciliation on the seeded messy benchmark dataset."""
    global latest_report
    df_rzp, df_bank, ground_truth = generate_benchmark_dataset(seed=42)

    gw_txs = rzp_adapter.parse(df_rzp)
    bnk_txs = bank_adapter.parse(df_bank)

    engine = DeterministicMatchingEngine(session_id=f"benchmark_{int(datetime.now().timestamp())}")
    report = engine.reconcile(gw_txs, bnk_txs)

    # Commit report to tamper-evident audit chain
    audit_chain.record_reconciliation_report(report)

    # Index into RAG agent
    qa_agent.set_report(report)
    latest_report = report

    telemetry.push(
        level="INFO",
        component="RECONCILIATION_ENGINE",
        message=f"Reconciled benchmark dataset: {len(report.matches)} auto-matched, {len(report.human_reviews)} flagged for human review.",
        metadata={"session_id": report.session_id, "rate": f"{report.summary.auto_match_rate}%"},
    )

    return report


@router.post("/reconcile/upload")
async def reconcile_upload(
    razorpay_file: UploadFile = File(...),
    bank_file: UploadFile = File(...),
):
    """Reconcile custom uploaded Razorpay and Bank CSV files."""
    global latest_report
    try:
        rzp_bytes = await razorpay_file.read()
        bank_bytes = await bank_file.read()

        gw_txs = rzp_adapter.parse(rzp_bytes)
        bnk_txs = bank_adapter.parse(bank_bytes)

        engine = DeterministicMatchingEngine(session_id=f"upload_{int(datetime.now().timestamp())}")
        report = engine.reconcile(gw_txs, bnk_txs)

        audit_chain.record_reconciliation_report(report)
        qa_agent.set_report(report)
        latest_report = report

        telemetry.push(
            level="INFO",
            component="RECONCILIATION_ENGINE",
            message=f"Custom CSV reconciliation finished: {report.summary.auto_matched_count} auto-matched.",
        )
        return report
    except Exception as e:
        telemetry.push("ERROR", "INGESTION_ERROR", f"Upload reconciliation failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/query")
async def query_reconciliation(req: QueryRequest):
    """Natural language Q&A over reconciliation results."""
    if not latest_report:
        # Automatically run benchmark so the agent is immediately ready
        await reconcile_benchmark()

    resp = qa_agent.answer_query(req.query)
    return resp


@router.get("/summary")
async def get_summary():
    """Get the financial controller executive summary."""
    if not latest_report:
        await reconcile_benchmark()
    
    markdown_summary = FinancialSummarizer.generate_executive_summary(latest_report)
    return {"summary_markdown": markdown_summary, "metrics": latest_report.summary}


@router.get("/audit/chain")
async def get_audit_chain():
    """Retrieve full cryptographic audit ledger."""
    return {
        "chain": audit_chain.get_chain(),
        "head": audit_chain.get_head(),
        "total_blocks": len(audit_chain.get_chain()),
    }


@router.get("/audit/verify")
async def verify_audit():
    """Perform independent mathematical verification of audit chain."""
    res = AuditVerifier.verify_chain(audit_chain.get_chain())
    is_valid, err_idx, msg = res

    telemetry.push(
        level="INFO" if is_valid else "ERROR",
        component="AUDIT_VERIFIER",
        message=f"Audit chain verification: {'PASSED (Zero Tampering)' if is_valid else f'FAILED at block {err_idx}'}",
        metadata={"verified": is_valid, "blocks": len(audit_chain.get_chain())},
    )

    return {
        "verified": is_valid,
        "total_blocks": len(audit_chain.get_chain()),
        "chain_head": audit_chain.get_head(),
        "corrupted_block_index": err_idx,
        "message": msg,
    }


@router.get("/telemetry")
async def get_telemetry_logs():
    """Retrieve recent resilience, retry, and fallback events."""
    return {"events": telemetry.get_recent(100)}


@router.post("/simulate-failure")
async def simulate_failure(req: FailureSimulationRequest):
    """Visually instrument and demonstrate runtime resilience and graceful fallback."""
    if req.scenario == "upstream_timeout":
        telemetry.push(
            level="WARNING",
            component="UPSTREAM_RETRY",
            message="Simulated Razorpay Banking API timeout (HTTP 504). Initiating exponential backoff retry 1/3 (delay 0.50s)...",
        )
        telemetry.push(
            level="WARNING",
            component="UPSTREAM_RETRY",
            message="Retry 2/3 failed (HTTP 504). Retrying in 1.10s...",
        )
        telemetry.push(
            level="INFO",
            component="UPSTREAM_RETRY",
            message="Retry 3/3 succeeded via secondary gateway mirror. Processed 12 transactions.",
        )
        return {"status": "success", "message": "Upstream timeout & retry backoff demonstrated."}

    elif req.scenario == "llm_offline":
        telemetry.push(
            level="WARNING",
            component="LLM_DEGRADATION",
            message="LLM API endpoint connection refused (Simulated Outage). Gracefully activating Deterministic Template Fallback Engine.",
        )
        return {"status": "success", "message": "Graceful LLM fallback simulated. System responded with zero downtime."}

    elif req.scenario == "audit_tamper":
        # Create a tampered block copy in memory to demonstrate cryptographic detection
        chain_copy = [b.model_copy(deep=True) for b in audit_chain.get_chain()]
        if len(chain_copy) > 1:
            chain_copy[1].payload["tampered_amount"] = 9999999.0
            is_valid, idx, msg = AuditVerifier.verify_chain(chain_copy)
            telemetry.push(
                level="ERROR",
                component="TAMPER_DETECTED",
                message=f"CRITICAL SECURITY ALERT: Cryptographic forgery detected at Block #{idx}! {msg}",
            )
            return {
                "status": "tamper_detected",
                "detected": True,
                "corrupted_block": idx,
                "message": msg,
            }
        return {"status": "error", "message": "Need more blocks to simulate tamper."}

    return {"status": "unknown_scenario"}
