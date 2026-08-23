"""
Integration tests for FastAPI routes, Web UI endpoints, and fault simulations.
"""

import io
import pytest
from fastapi.testclient import TestClient
from fincontroller.api.app import app
from fincontroller.ingestion.generator import generate_benchmark_dataset

client = TestClient(app)


def test_index_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "FinController" in response.text
    assert "Razorpay AI Track" in response.text


def test_reconcile_benchmark_endpoint():
    response = client.post("/api/reconcile/benchmark")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "matches" in data
    assert "human_reviews" in data
    assert data["summary"]["match_rate"] > 70.0
    assert data["summary"]["reconciled_volume"] > 0
    assert len(data["matches"]) > 0
    assert len(data["human_reviews"]) > 0


def test_reconcile_upload_endpoint():
    df_rzp, df_bank, _ = generate_benchmark_dataset(seed=42)
    rzp_csv = df_rzp.to_csv(index=False).encode("utf-8")
    bank_csv = df_bank.to_csv(index=False).encode("utf-8")

    response = client.post(
        "/api/reconcile/upload",
        files={
            "razorpay_file": ("razorpay.csv", io.BytesIO(rzp_csv), "text/csv"),
            "bank_file": ("bank.csv", io.BytesIO(bank_csv), "text/csv"),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["auto_matched_count"] > 0
    assert data["summary"]["reconciled_volume"] > 0


def test_query_rag_endpoint():
    # Trigger benchmark first
    client.post("/api/reconcile/benchmark")
    response = client.post("/api/query", json={"query": "Why did pay_AMBIG_DUP_00_A need human review?"})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "source" in data
    assert len(data["answer"]) > 20


def test_get_summary_endpoint():
    response = client.get("/api/summary")
    assert response.status_code == 200
    data = response.json()
    assert "summary_markdown" in data
    assert "metrics" in data
    assert "Executive Overview" in data["summary_markdown"]


def test_audit_chain_and_verify_endpoints():
    client.post("/api/reconcile/benchmark")
    chain_resp = client.get("/api/audit/chain")
    assert chain_resp.status_code == 200
    chain_data = chain_resp.json()
    assert chain_data["total_blocks"] >= 1
    assert len(chain_data["head"]) == 64

    verify_resp = client.get("/api/audit/verify")
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["verified"] is True
    assert verify_data["corrupted_block_index"] is None


def test_telemetry_endpoint():
    response = client.get("/api/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert isinstance(data["events"], list)


def test_simulate_failures_endpoints():
    # 1. Upstream timeout
    r1 = client.post("/api/simulate-failure", json={"scenario": "upstream_timeout"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "success"

    # 2. LLM outage
    r2 = client.post("/api/simulate-failure", json={"scenario": "llm_offline"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "success"

    # 3. Audit tamper
    client.post("/api/reconcile/benchmark")
    r3 = client.post("/api/simulate-failure", json={"scenario": "audit_tamper"})
    assert r3.status_code == 200
    assert r3.json()["status"] == "tamper_detected"
    assert r3.json()["detected"] is True
