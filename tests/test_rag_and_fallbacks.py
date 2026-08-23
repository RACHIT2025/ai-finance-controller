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


def test_deterministic_fallback_unmatched_and_missing():
    gw_unmatched = NormalizedTransaction(
        id="rzp_unmatched_99",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_UNSETTLED_99",
        amount=15000.0,
        net_amount=15000.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        reference_id="pay_UNSETTLED_99",
    )
    bnk_orphaned = NormalizedTransaction(
        id="bnk_orphaned_99",
        source=TransactionSource.BANK_LEDGER,
        raw_id="DIRECT_BANK_99",
        amount=25000.0,
        net_amount=25000.0,
        currency="INR",
        timestamp=datetime(2026, 8, 5, 10, 0, 0),
        reference_id="DIRECT_BANK_99",
        description="Direct client NEFT deposit",
    )
    report = DeterministicMatchingEngine().reconcile([gw_unmatched], [bnk_orphaned])

    qa_agent = ReconciliationQAAgent()
    qa_agent.set_report(report)

    # 1. Unmatched Gateway
    res_gw = qa_agent.answer_query("pay_UNSETTLED_99")
    assert "Unmatched Gateway Transaction" in res_gw["answer"]
    assert "15,000.00" in res_gw["answer"]

    # 2. Unmatched Bank
    res_bnk = qa_agent.answer_query("DIRECT_BANK_99")
    assert "Unmatched Bank Deposit" in res_bnk["answer"]
    assert "25,000.00" in res_bnk["answer"]

    # 3. Not found
    res_missing = qa_agent.answer_query("nonexistent_id_999")
    assert "Search Query Not Found" in res_missing["answer"]
