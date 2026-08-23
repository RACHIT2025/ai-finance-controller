"""
Tests for Schema-Agnostic Dynamic Ingestion, Column Auto-Detection, and Cross-Platform Matching.
"""

from datetime import datetime
import os
import pytest

from fincontroller.core.exceptions import IngestionError
from fincontroller.core.models import TransactionSource, TransactionStatus
from fincontroller.engine.matching_engine import DeterministicMatchingEngine
from fincontroller.ingestion.generic_adapter import SchemaAgnosticAdapter
from fincontroller.ingestion.mapper import ColumnMapper, ColumnMappingConfig


def test_column_mapper_alias_detection():
    # Test Stripe-like headers
    stripe_cols = ["id", "Amount", "Fee", "Converted Amount", "Created (UTC)", "Description", "Customer Email", "Status"]
    cfg = ColumnMapper.auto_detect_mapping(stripe_cols)
    assert cfg.amount == "Amount"
    assert cfg.fee == "Fee"
    assert cfg.timestamp == "Created (UTC)"
    assert cfg.description == "Description"
    assert cfg.counterparty == "Customer Email"

    # Test HDFC-like headers
    hdfc_cols = ["Date", "Narration", "Chq/Ref Number", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
    cfg_hdfc = ColumnMapper.auto_detect_mapping(hdfc_cols)
    assert cfg_hdfc.timestamp == "Date"
    assert cfg_hdfc.description == "Narration"
    assert cfg_hdfc.reference_id == "Chq/Ref Number"
    assert cfg_hdfc.amount == "Deposit Amt."
    assert cfg_hdfc.debit == "Withdrawal Amt."


def test_column_mapper_numeric_and_datetime_parsing():
    # Numeric parsing
    assert ColumnMapper.parse_numeric("₹1,250.50") == 1250.50
    assert ColumnMapper.parse_numeric("$50,000.00") == 50000.00
    assert ColumnMapper.parse_numeric(" 4,500 ") == 4500.00
    assert ColumnMapper.parse_numeric("-") == 0.0
    assert ColumnMapper.parse_numeric(None) == 0.0

    # Datetime parsing
    dt1 = ColumnMapper.parse_datetime("2026-08-01 10:15:00")
    assert dt1.year == 2026 and dt1.month == 8 and dt1.day == 1

    dt2 = ColumnMapper.parse_datetime("01/08/2026")
    assert dt2.year == 2026 and dt2.month == 8 and dt2.day == 1

    dt3 = ColumnMapper.parse_datetime(1785600000)
    assert isinstance(dt3, datetime)


def test_schema_agnostic_adapter_stripe_and_hdfc(tmp_path):
    stripe_file = os.path.join("data", "sample_stripe_export.csv")
    hdfc_file = os.path.join("data", "sample_hdfc_bank_statement.csv")

    assert os.path.exists(stripe_file)
    assert os.path.exists(hdfc_file)

    gw_adapter = SchemaAgnosticAdapter(source=TransactionSource.RAZORPAY, source_prefix="stripe")
    bank_adapter = SchemaAgnosticAdapter(source=TransactionSource.BANK_LEDGER, source_prefix="hdfc")

    gw_txs = gw_adapter.parse(stripe_file)
    bnk_txs = bank_adapter.parse(hdfc_file)

    assert len(gw_txs) == 5
    assert len(bnk_txs) == 6

    # Test values in normalized transactions
    assert gw_txs[0].amount == 4500.00
    assert gw_txs[0].net_amount == 4410.00
    assert "pay_STRIPE_001" in gw_txs[0].reference_id

    # Execute matching engine over dynamic datasets
    engine = DeterministicMatchingEngine(session_id="test_dynamic_01")
    report = engine.reconcile(gw_txs, bnk_txs)

    assert report.summary.auto_matched_count == 5
    assert report.summary.unmatched_bank_count == 1
    assert report.summary.match_rate == 100.0


def test_custom_user_mapping_override():
    custom_csv = (
        "custom_tx_id,my_paid_val,my_commission,booking_time,order_code\n"
        "TXN_991,5000.00,100.00,2026-08-01,ORD_991\n"
    )
    user_mapping = {
        "raw_id": "custom_tx_id",
        "amount": "my_paid_val",
        "fee": "my_commission",
        "timestamp": "booking_time",
        "reference_id": "order_code",
    }
    adapter = SchemaAgnosticAdapter(mapping=user_mapping)
    txs = adapter.parse(custom_csv)

    assert len(txs) == 1
    assert txs[0].amount == 5000.00
    assert txs[0].fee == 100.00
    assert txs[0].net_amount == 4900.00
    assert txs[0].reference_id == "ORD_991"


def test_missing_required_amount_column_fails_gracefully():
    broken_csv = (
        "user_name,comment,date\n"
        "John Doe,Payment confirmed,2026-08-01\n"
    )
    adapter = SchemaAgnosticAdapter()
    with pytest.raises(IngestionError) as exc_info:
        adapter.parse(broken_csv)

    assert "Missing required amount column" in str(exc_info.value)
