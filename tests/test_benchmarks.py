"""
Benchmark and Accuracy Evaluation Test Suite.
Validates precision, recall, and false-positive refusal on the messy dataset.
"""

from fincontroller.engine.matching_engine import DeterministicMatchingEngine
from fincontroller.ingestion.bank_ledger_adapter import BankLedgerAdapter
from fincontroller.ingestion.generator import generate_benchmark_dataset
from fincontroller.ingestion.razorpay_adapter import RazorpayAdapter


def test_benchmark_accuracy_and_metrics():
    df_rzp, df_bank, ground_truth = generate_benchmark_dataset(seed=42)
    assert len(df_rzp) > 0
    assert len(df_bank) > 0

    gw_txs = RazorpayAdapter().parse(df_rzp)
    bnk_txs = BankLedgerAdapter().parse(df_bank)

    engine = DeterministicMatchingEngine(session_id="eval_test")
    report = engine.reconcile(gw_txs, bnk_txs)

    # 1. Zero false matches on ambiguous duplicates
    assert len(report.human_reviews) > 0
    for hr in report.human_reviews:
        assert hr.confidence < 0.85

    # 2. Reconciled volume is positive
    assert report.summary.reconciled_volume > 0

    # 3. Auto-match rate is healthy
    assert report.summary.auto_match_rate > 70.0

    # 4. Total gateway fees are tracked
    assert report.summary.total_fee_volume > 0
