"""
Test fixtures and configuration.
"""

from datetime import datetime
import pytest
from fincontroller.core.models import NormalizedTransaction, TransactionSource, TransactionStatus
from fincontroller.engine.matching_engine import DeterministicMatchingEngine


@pytest.fixture
def sample_gateway_tx() -> NormalizedTransaction:
    return NormalizedTransaction(
        id="rzp_test_101",
        source=TransactionSource.RAZORPAY,
        raw_id="pay_SAMPLE_101",
        amount=1000.0,
        fee=0.0,
        tax=0.0,
        net_amount=1000.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        reference_id="pay_SAMPLE_101",
        counterparty="Test Merchant",
        status=TransactionStatus.SETTLED,
    )


@pytest.fixture
def sample_bank_tx() -> NormalizedTransaction:
    return NormalizedTransaction(
        id="bnk_test_101",
        source=TransactionSource.BANK_LEDGER,
        raw_id="UTR_SAMPLE_101",
        amount=1000.0,
        fee=0.0,
        tax=0.0,
        net_amount=1000.0,
        currency="INR",
        timestamp=datetime(2026, 8, 1, 14, 0, 0),
        reference_id="pay_SAMPLE_101",
        counterparty="HDFC Bank",
        description="CMS/RAZORPAY/pay_SAMPLE_101",
        status=TransactionStatus.SETTLED,
    )


@pytest.fixture
def matching_engine() -> DeterministicMatchingEngine:
    return DeterministicMatchingEngine(session_id="test_session")
