"""
FastAPI REST API Routes for FinController.
"""

from datetime import datetime
import json
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
    gateway_file: Optional[UploadFile] = File(None),
    bank_file: Optional[UploadFile] = File(None),
    razorpay_file: Optional[UploadFile] = File(None),
    gateway_mapping: Optional[str] = Form(None),
    bank_mapping: Optional[str] = Form(None),
):
    """
    Reconcile arbitrary user-supplied Gateway and Bank files with automatic column
    mapping and optional custom schema overrides.
    """
    global latest_report
    gw_upload = gateway_file or razorpay_file
    if not gw_upload or not bank_file:
        raise HTTPException(status_code=400, detail="Both gateway/razorpay file and bank file are required.")

    try:
        gw_bytes = await gw_upload.read()
        bank_bytes = await bank_file.read()

        gw_map = json.loads(gateway_mapping) if gateway_mapping and gateway_mapping.strip().startswith("{") else None
        bnk_map = json.loads(bank_mapping) if bank_mapping and bank_mapping.strip().startswith("{") else None

        from fincontroller.ingestion.generic_adapter import SchemaAgnosticAdapter
        from fincontroller.core.models import TransactionSource

        gw_adapter = SchemaAgnosticAdapter(source=TransactionSource.RAZORPAY, mapping=gw_map, source_prefix="gw")
        bank_adapter = SchemaAgnosticAdapter(source=TransactionSource.BANK_LEDGER, mapping=bnk_map, source_prefix="bnk")

        gw_txs = gw_adapter.parse(gw_bytes)
        bnk_txs = bank_adapter.parse(bank_bytes)

        engine = DeterministicMatchingEngine(session_id=f"upload_{int(datetime.now().timestamp())}")
        report = engine.reconcile(gw_txs, bnk_txs)

        audit_chain.record_reconciliation_report(report)
        qa_agent.set_report(report)
        latest_report = report

        telemetry.push(
            level="INFO",
            component="DYNAMIC_INGESTION",
            message=f"Live reconciliation complete: {len(gw_txs)} gateway txs vs {len(bnk_txs)} bank credits. Match Rate: {report.summary.match_rate:.1f}%.",
            metadata={"gw_count": len(gw_txs), "bnk_count": len(bnk_txs), "matches": len(report.matches)},
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


@router.post("/telemetry/clear")
@router.delete("/telemetry")
async def clear_telemetry_logs():
    """Clear all events from the real-time telemetry buffer."""
    telemetry.clear()
    return {"status": "cleared", "total_events": 0}


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


class ManualGatewayTx(BaseModel):
    id: str
    amount: float
    fee: Optional[float] = 0.0
    reference_id: Optional[str] = ""
    status: Optional[str] = "captured"
    timestamp: Optional[str] = None


class ManualBankTx(BaseModel):
    id: str
    amount: float
    reference_id: Optional[str] = ""
    description: Optional[str] = ""
    timestamp: Optional[str] = None


class ManualReconciliationRequest(BaseModel):
    gateway_transactions: List[ManualGatewayTx]
    bank_transactions: List[ManualBankTx]
    session_title: Optional[str] = "Customer Live Sandbox"


@router.get("/health")
async def health_check():
    """Production health check for cloud uptime monitoring and load balancers."""
    from fincontroller.core.config import settings
    return {
        "status": "healthy",
        "service": "Razorpay AI Finance Controller",
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "gemini_active": bool(settings.get_effective_gemini_key()),
        "openai_active": bool(settings.OPENAI_API_KEY),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/reconcile/manual-entry")
async def reconcile_manual_entry(payload: ManualReconciliationRequest):
    """
    Direct Interactive Customer Data Entry.
    Accepts row-by-row transaction lists entered directly on screen and reconciles them live.
    """
    global latest_report
    from fincontroller.core.models import TransactionSource, TransactionStatus

    if not payload.gateway_transactions or not payload.bank_transactions:
        raise HTTPException(status_code=400, detail="At least one gateway transaction and one bank credit are required.")

    gw_txs: List[NormalizedTransaction] = []
    for g in payload.gateway_transactions:
        ts = datetime.utcnow()
        if g.timestamp:
            try:
                ts = datetime.fromisoformat(g.timestamp.replace("Z", "+00:00"))
            except Exception:
                pass
        
        status_enum = TransactionStatus.CAPTURED
        if g.status and g.status.lower() in ("failed", "failure"):
            status_enum = TransactionStatus.FAILED
        elif g.status and g.status.lower() in ("refunded", "refund"):
            status_enum = TransactionStatus.REFUNDED

        gw_txs.append(
            NormalizedTransaction(
                id=g.id,
                source=TransactionSource.RAZORPAY,
                raw_id=g.id,
                amount=round(float(g.amount), 2),
                fee=round(float(g.fee or 0.0), 2),
                net_amount=round(float(g.amount) - float(g.fee or 0.0), 2),
                currency="INR",
                status=status_enum,
                timestamp=ts,
                reference_id=g.reference_id or g.id,
                metadata={"entry_type": "manual_interactive"},
            )
        )

    bnk_txs: List[NormalizedTransaction] = []
    for b in payload.bank_transactions:
        ts = datetime.utcnow()
        if b.timestamp:
            try:
                ts = datetime.fromisoformat(b.timestamp.replace("Z", "+00:00"))
            except Exception:
                pass

        bnk_txs.append(
            NormalizedTransaction(
                id=b.id,
                source=TransactionSource.BANK_LEDGER,
                raw_id=b.id,
                amount=round(float(b.amount), 2),
                fee=0.0,
                net_amount=round(float(b.amount), 2),
                currency="INR",
                status=TransactionStatus.CAPTURED,
                timestamp=ts,
                reference_id=b.reference_id or b.id,
                description=b.description or "Direct Customer Entry",
                metadata={"entry_type": "manual_interactive"},
            )
        )

    session_id = f"manual_{int(datetime.now().timestamp())}"
    engine = DeterministicMatchingEngine(session_id=session_id)
    report = engine.reconcile(gw_txs, bnk_txs)

    audit_chain.record_reconciliation_report(report)
    qa_agent.set_report(report)
    latest_report = report

    telemetry.push(
        level="INFO",
        component="MANUAL_STUDIO",
        message=f"Interactive sandbox reconciliation: {len(gw_txs)} gateway txs vs {len(bnk_txs)} bank entries. Match Rate: {report.summary.match_rate:.1f}%.",
        metadata={"session_id": session_id, "matches": len(report.matches), "review": len(report.human_reviews)},
    )

    return report


@router.get("/export/csv")
async def export_reconciliation_csv():
    """Export the active reconciliation report as a formatted CSV file."""
    from fastapi.responses import Response
    import io
    import csv

    if not latest_report:
        await reconcile_benchmark()

    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Header & Summary Info
    now_str = datetime.now().isoformat()
    writer.writerow(["# RAZORPAY AI FINANCE CONTROLLER - RECONCILIATION EXPORT"])
    writer.writerow(["# Session ID", latest_report.session_id])

    writer.writerow(["# Generated At", now_str])
    writer.writerow(["# Match Rate (%)", f"{latest_report.summary.match_rate:.2f}"])
    writer.writerow(["# Reconciled Volume", f"INR {latest_report.summary.reconciled_volume:.2f}"])
    writer.writerow([])

    # 2. Matches Table
    writer.writerow(["Record Type", "Match ID", "Category", "Reason Code", "Gateway TX IDs", "Bank TX IDs", "Fee Detected", "Discrepancy", "Confidence", "Explanation"])

    for m in latest_report.matches:
        writer.writerow([
            "AUTO_MATCHED",
            m.match_id,
            m.category.value,
            m.reason_code.value,
            "; ".join(m.gateway_tx_ids),
            "; ".join(m.bank_tx_ids),
            f"{m.fee_detected:.2f}",
            f"{m.amount_discrepancy:.2f}",
            f"{m.confidence:.2f}",
            m.explanation,
        ])

    for hr in latest_report.human_reviews:
        writer.writerow([
            "NEEDS_HUMAN_REVIEW",
            hr.match_id,
            hr.category.value,
            hr.reason_code.value,
            "; ".join(hr.gateway_tx_ids),
            "; ".join(hr.bank_tx_ids),
            f"{hr.fee_detected:.2f}",
            f"{hr.amount_discrepancy:.2f}",
            f"{hr.confidence:.2f}",
            hr.explanation,
        ])

    for ug in latest_report.unmatched_gateway:
        writer.writerow([
            "UNMATCHED_GATEWAY",
            ug.id,
            "UNMATCHED",
            ug.metadata.get("unmatched_reason", "UNSETTLED_PAYMENT"),
            ug.id,
            "",
            f"{ug.fee:.2f}",
            f"{ug.net_amount:.2f}",
            "0.00",
            f"Gross INR {ug.amount:.2f}, status '{ug.status.value}'. Pending bank settlement.",
        ])

    for ub in latest_report.unmatched_bank:
        writer.writerow([
            "UNMATCHED_BANK",
            ub.id,
            "UNMATCHED",
            ub.metadata.get("unmatched_reason", "ORPHANED_CREDIT"),
            "",
            ub.id,
            "0.00",
            f"{ub.net_amount:.2f}",
            "0.00",
            f"Narration: {ub.description or 'Direct deposit'}. Direct bank deposit without matching gateway settlement.",
        ])

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=fincontroller_recon_{latest_report.session_id}.csv"
        },
    )


@router.get("/export/audit-cert")
async def export_audit_certificate():
    """Export cryptographic SHA-256 tamper-evident reconciliation certificate."""
    if not latest_report:
        await reconcile_benchmark()

    is_valid, err_idx, msg = AuditVerifier.verify_chain(audit_chain.get_chain())
    
    cert = {
        "certificate_id": f"CERT-{latest_report.session_id.upper()}",
        "issuer": "Razorpay AI Finance Controller Audit Core",
        "issued_at_utc": datetime.now().isoformat(),
        "cryptographic_verification": {
            "status": "PASSED" if is_valid else "FAILED",
            "algorithm": "SHA-256 Merkle-Style Hash Chain",
            "chain_head_hash": audit_chain.get_head(),
            "total_blocks_sealed": len(audit_chain.get_chain()),
            "tamper_detected": not is_valid,
            "verification_message": msg,
        },
        "reconciliation_summary": {
            "session_id": latest_report.session_id,
            "match_rate_percentage": round(latest_report.summary.match_rate, 2),
            "total_gateway_volume_inr": latest_report.summary.total_gateway_volume,
            "reconciled_settlement_volume_inr": latest_report.summary.reconciled_volume,
            "gateway_fees_accounted_inr": latest_report.summary.total_fee_volume,
            "auto_matched_pairs": latest_report.summary.auto_matched_count,
            "needs_human_review_count": latest_report.summary.human_review_count,
            "unmatched_gateway_count": latest_report.summary.unmatched_gateway_count,
            "unmatched_bank_count": latest_report.summary.unmatched_bank_count,
        },
        "latest_audit_block": audit_chain.get_chain()[-1].model_dump() if audit_chain.get_chain() else None,
    }

    return cert


