"""
Tests for Customer Data Studio Interactive Sandbox, CSV & Audit Cert Exports, Health Status, and Multi-Model LLM logic.
"""

import pytest
from fastapi.testclient import TestClient
from fincontroller.api.app import app
from fincontroller.core.config import settings

client = TestClient(app)


def test_cloud_health_check_endpoint():
    """Verify the /api/health endpoint returns healthy 200 with system capabilities."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["version"] == "2.0.0"
    assert "environment" in data
    assert "llm_provider" in data


def test_manual_interactive_reconciliation_exact_and_fee():
    """Test customer interactive row entry submission and reconciliation."""
    payload = {
        "gateway_transactions": [
            {
                "id": "pay_manual_01",
                "amount": 5000.0,
                "fee": 118.0,
                "reference_id": "ORDER_1001",
                "status": "captured",
            },
            {
                "id": "pay_manual_02",
                "amount": 2500.0,
                "fee": 59.0,
                "reference_id": "ORDER_1002",
                "status": "captured",
            },
            {
                "id": "pay_manual_unsettled",
                "amount": 1200.0,
                "fee": 0.0,
                "reference_id": "ORDER_UNSETTLED",
                "status": "captured",
            },
        ],
        "bank_transactions": [
            {
                "id": "UTR_BNK_001",
                "amount": 4882.0,  # 5000 - 118
                "reference_id": "ORDER_1001",
                "description": "Settlement ORDER_1001",
            },
            {
                "id": "UTR_BNK_002",
                "amount": 2441.0,  # 2500 - 59
                "reference_id": "ORDER_1002",
                "description": "Settlement ORDER_1002",
            },
            {
                "id": "UTR_BNK_ORPHAN",
                "amount": 333.0,
                "reference_id": "OFFLINE_DEPOSIT",
                "description": "Direct counter credit",
            },
        ],
        "session_title": "Interactive Test Session",
    }

    resp = client.post("/api/reconcile/manual-entry", json=payload)
    assert resp.status_code == 200
    report = resp.json()

    # Matches should contain the 2 fee-adjusted matched pairs
    assert len(report["matches"]) == 2
    assert len(report["unmatched_gateway"]) == 1
    assert len(report["unmatched_bank"]) == 1
    assert report["summary"]["match_rate"] > 0


def test_export_reconciliation_csv_endpoint():
    """Verify CSV export endpoint returns valid CSV text and headers."""
    # Ensure benchmark report exists
    client.post("/api/reconcile/benchmark")

    resp = client.get("/api/export/csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in resp.headers.get("content-disposition", "")
    assert "Record Type,Match ID,Category" in resp.text


def test_export_audit_certificate_endpoint():
    """Verify cryptographic audit certificate endpoint returns valid signed JSON."""
    client.post("/api/reconcile/benchmark")

    resp = client.get("/api/export/audit-cert")
    assert resp.status_code == 200
    cert = resp.json()
    assert "certificate_id" in cert
    assert cert["issuer"] == "Razorpay AI Finance Controller Audit Core"
    assert cert["cryptographic_verification"]["status"] == "PASSED"
    assert "chain_head_hash" in cert["cryptographic_verification"]
    assert "reconciliation_summary" in cert


def test_tiered_mdr_matching():
    """Verify tiered MDR rates (e.g. Debit Card 0.9% + GST, Flat IMPS) match correctly."""
    from fincontroller.engine.rules import MatchingRules
    from fincontroller.core.models import NormalizedTransaction, TransactionSource, TransactionStatus
    from datetime import datetime

    gw = NormalizedTransaction(
        id="pay_debit_01",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_debit_01",
        amount=10000.0,
        fee=0.0,
        net_amount=10000.0,
        currency="INR",
        status=TransactionStatus.CAPTURED,
        timestamp=datetime.now(),
        reference_id="REF_DEBIT_101",
    )

    # 0.9% MDR + 18% GST = ₹106.20 fee -> Net = ₹9,893.80
    bnk = NormalizedTransaction(
        id="UTR_DEBIT_101",
        source=TransactionSource.BANK_LEDGER,
        raw_id="UTR_DEBIT_101",
        amount=9893.80,
        fee=0.0,
        net_amount=9893.80,
        currency="INR",
        status=TransactionStatus.CAPTURED,
        timestamp=datetime.now(),
        reference_id="REF_DEBIT_101",
    )

    is_match, detected_fee = MatchingRules.is_fee_adjusted_match(gw, bnk)
    assert is_match is True
    assert round(detected_fee, 2) == 106.20


def test_dispute_chargeback_reconciliation():
    """Test 3-way chargeback & refund dispute reconciliation."""
    payload = {
        "gateway_transactions": [
            {
                "id": "pay_DISPUTE_01",
                "amount": 8000.0,
                "fee": 188.8,
                "reference_id": "ORD_DISPUTE_201",
                "status": "captured",
            },
            {
                "id": "pay_DISPUTE_refund",
                "amount": 8000.0,
                "fee": 0.0,
                "reference_id": "ORD_DISPUTE_201_CBK",
                "status": "refunded",
            },
        ],
        "bank_transactions": [
            {
                "id": "UTR_DISPUTE_SETTL",
                "amount": 7811.2,
                "reference_id": "ORD_DISPUTE_201",
                "description": "Settlement ORD_DISPUTE_201",
            }
        ],
        "session_title": "Dispute Test Session",
    }

    resp = client.post("/api/reconcile/manual-entry", json=payload)
    assert resp.status_code == 200
    report = resp.json()
    assert len(report["matches"]) == 1
    assert report["matches"][0]["fee_detected"] > 0

