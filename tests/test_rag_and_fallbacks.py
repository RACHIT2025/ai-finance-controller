"""
Unit tests for RAG indexing, Q&A agent, and deterministic offline fallbacks.
"""

from datetime import datetime
import pytest
from fincontroller.core.models import NormalizedTransaction, TransactionSource, TransactionStatus
from fincontroller.engine.matching_engine import DeterministicMatchingEngine
from fincontroller.rag.fallback_templates import DeterministicFallbackEngine
from fincontroller.rag.qa_agent import ReconciliationQAAgent
from fincontroller.rag.summarizer import FinancialSummarizer
from fincontroller.rag.vector_store import ReconciliationDocStore


def test_rag_agent_query_and_offline_fallback():
    gw = NormalizedTransaction(
        id="rzp_qa_1",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_QUESTION_01",
        amount=2500.0,
        net_amount=2500.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        reference_id="pay_QUESTION_01",
    )
    bnk = NormalizedTransaction(
        id="bnk_qa_1",
        source=TransactionSource.BANK_LEDGER,
        raw_id="UTR_QA_01",
        amount=2500.0,
        net_amount=2500.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 12, 0, 0),
        reference_id="pay_QUESTION_01",
    )
    engine = DeterministicMatchingEngine()
    report = engine.reconcile([gw], [bnk])

    doc_store = ReconciliationDocStore()
    qa_agent = ReconciliationQAAgent(doc_store=doc_store)
    qa_agent.set_report(report)

    # Test Q&A Query
    resp = qa_agent.answer_query("pay_QUESTION_01")
    assert resp is not None
    assert "Reconciled Successfully" in resp["answer"]
    assert "pay_QUESTION_01" in resp["answer"]


def test_executive_summary_generation():
    gw = NormalizedTransaction(
        id="rzp_sum_1",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_SUM_1",
        amount=10000.0,
        net_amount=10000.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        reference_id="pay_SUM_1",
    )
    bnk = NormalizedTransaction(
        id="bnk_sum_1",
        source=TransactionSource.BANK_LEDGER,
        raw_id="pay_SUM_1",
        amount=10000.0,
        net_amount=10000.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 10, 30, 0),
        reference_id="pay_SUM_1",
    )
    report = DeterministicMatchingEngine().reconcile([gw], [bnk])
    summary_md = FinancialSummarizer.generate_executive_summary(report)
    assert "Financial Controller Daily Reconciliation Summary" in summary_md
    assert "10,000.00" in summary_md
