"""
Unit and integration tests for the Deterministic Matching Engine.
"""

from datetime import datetime, timedelta
import pytest
from fincontroller.core.models import MatchCategory, MatchReasonCode, NormalizedTransaction, TransactionSource, TransactionStatus
from fincontroller.engine.matching_engine import DeterministicMatchingEngine
from fincontroller.engine.rules import MatchingRules


def test_exact_1_to_1_match(matching_engine, sample_gateway_tx, sample_bank_tx):
    report = matching_engine.reconcile([sample_gateway_tx], [sample_bank_tx])
    assert len(report.matches) == 1
    match = report.matches[0]
    assert match.category == MatchCategory.AUTO_MATCHED
    assert match.reason_code == MatchReasonCode.EXACT_MATCH_REF_AND_AMOUNT
    assert match.confidence == 1.0
    assert match.amount_discrepancy == 0.0
    assert len(report.human_reviews) == 0
    assert len(report.unmatched_gateway) == 0
    assert len(report.unmatched_bank) == 0


def test_fee_adjusted_match(matching_engine):
    gw = NormalizedTransaction(
        id="rzp_fee_1",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_FEE_1",
        amount=10000.0,
        fee=200.0,
        tax=36.0,
        net_amount=9764.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        reference_id="UTR_FEE_01",
    )
    bnk = NormalizedTransaction(
        id="bnk_fee_1",
        source=TransactionSource.BANK_LEDGER,
        raw_id="UTR_FEE_01",
        amount=9764.0,
        net_amount=9764.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 16, 0, 0),
        reference_id="UTR_FEE_01",
    )
    report = matching_engine.reconcile([gw], [bnk])
    assert len(report.matches) == 1
    assert report.matches[0].category == MatchCategory.AUTO_MATCHED
    assert report.matches[0].reason_code == MatchReasonCode.FEE_ADJUSTED_MATCH
    assert report.matches[0].fee_detected == 236.0


def test_split_batch_settlement_resolution(matching_engine):
    base_ts = datetime(2026, 8, 2, 10, 0, 0)
    gw1 = NormalizedTransaction(
        id="rzp_split_1",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_SP_1",
        amount=3000.0,
        net_amount=3000.0,
        currency="INR",
        timestamp=base_ts,
        reference_id="UTR_BULK_99",
    )
    gw2 = NormalizedTransaction(
        id="rzp_split_2",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_SP_2",
        amount=4500.0,
        net_amount=4500.0,
        currency="INR",
        timestamp=base_ts + timedelta(hours=1),
        reference_id="UTR_BULK_99",
    )
    bnk_bulk = NormalizedTransaction(
        id="bnk_bulk_1",
        source=TransactionSource.BANK_LEDGER,
        raw_id="UTR_BULK_99",
        amount=7500.0,
        net_amount=7500.0,
        currency="INR",
        timestamp=base_ts + timedelta(hours=4),
        reference_id="UTR_BULK_99",
    )
    report = matching_engine.reconcile([gw1, gw2], [bnk_bulk])
    assert len(report.matches) == 1
    match = report.matches[0]
    assert match.category == MatchCategory.AUTO_MATCHED
    assert match.reason_code == MatchReasonCode.SPLIT_BATCH_MATCH
    assert set(match.gateway_tx_ids) == {"rzp_split_1", "rzp_split_2"}
    assert match.bank_tx_ids == ["bnk_bulk_1"]


def test_fuzzy_ref_match(matching_engine):
    gw = NormalizedTransaction(
        id="rzp_fuzz_1",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_FUZZY_TEST_ABC",
        amount=5500.0,
        net_amount=5500.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        reference_id="pay_FUZZY_TEST_ABC",
    )
    bnk = NormalizedTransaction(
        id="bnk_fuzz_1",
        source=TransactionSource.BANK_LEDGER,
        raw_id="pay_FUZZY_TEST_AB0",  # Single char OCR typo
        amount=5500.0,
        net_amount=5500.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 12, 0, 0),
        reference_id="pay_FUZZY_TEST_AB0",
    )
    report = matching_engine.reconcile([gw], [bnk])
    assert len(report.matches) == 1
    assert report.matches[0].category == MatchCategory.AUTO_MATCHED
    assert report.matches[0].reason_code == MatchReasonCode.FUZZY_REF_EXACT_AMOUNT_MATCH


def test_ambiguous_duplicate_routes_to_human_review(matching_engine):
    base_ts = datetime(2026, 8, 1, 10, 0, 0)
    gw1 = NormalizedTransaction(
        id="rzp_dup_1",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_DUP_1",
        amount=999.0,
        net_amount=999.0,
        currency="INR",
        timestamp=base_ts,
        reference_id="UTR_CONFLICT",
    )
    gw2 = NormalizedTransaction(
        id="rzp_dup_2",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_DUP_2",
        amount=999.0,
        net_amount=999.0,
        currency="INR",
        timestamp=base_ts + timedelta(minutes=2),
        reference_id="UTR_CONFLICT",
    )
    bnk = NormalizedTransaction(
        id="bnk_dup_1",
        source=TransactionSource.BANK_LEDGER,
        raw_id="UTR_CONFLICT",
        amount=999.0,
        net_amount=999.0,
        currency="INR",
        timestamp=base_ts + timedelta(hours=1),
        reference_id="UTR_CONFLICT",
    )
    report = matching_engine.reconcile([gw1, gw2], [bnk])
    # Must refuse auto-matching and route to human review
    assert len(report.matches) == 0
    assert len(report.human_reviews) == 1
    hr = report.human_reviews[0]
    assert hr.category == MatchCategory.NEEDS_HUMAN_REVIEW
    assert hr.reason_code == MatchReasonCode.AMBIGUOUS_DUPLICATE_CANDIDATES
