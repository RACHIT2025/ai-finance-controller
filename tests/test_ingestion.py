"""
Unit tests for data ingestion adapters and reference extractors.
"""

import pandas as pd
import pytest
from fincontroller.core.models import TransactionSource, TransactionStatus
from fincontroller.ingestion.bank_ledger_adapter import BankLedgerAdapter
from fincontroller.ingestion.base import BaseIngestionAdapter
from fincontroller.ingestion.razorpay_adapter import RazorpayAdapter


def test_reference_id_extraction():
    # Test Razorpay payment ID
    assert BaseIngestionAdapter.extract_reference_id("CMS/RAZORPAY/pay_K1928374650/SETTL") == "pay_K1928374650"
    
    # Test Razorpay settlement ID
    assert BaseIngestionAdapter.extract_reference_id("Payout setl_998877665544 to merchant") == "setl_998877665544"

    # Test UTR string
    assert BaseIngestionAdapter.extract_reference_id("NEFT-HDFC-UTR998811223344") == "UTR998811223344"


def test_razorpay_csv_parser():
    adapter = RazorpayAdapter()
    csv_data = """entity_id,amount,fee,tax,net_amount,currency,settled_at,utr,status
pay_001,5000.0,100.0,18.0,4882.0,INR,2026-08-01 12:00:00,UTR001,settled
pay_002,2500.0,0.0,0.0,2500.0,INR,2026-08-01 13:00:00,UTR002,refunded
"""
    txs = adapter.parse(csv_data)
    assert len(txs) == 2
    assert txs[0].source == TransactionSource.RAZORPAY
    assert txs[0].amount == 5000.0
    assert txs[0].fee == 100.0
    assert txs[0].tax == 18.0
    assert txs[0].net_amount == 4882.0
    assert txs[0].reference_id == "UTR001"
    assert txs[1].status == TransactionStatus.REFUNDED


def test_bank_ledger_csv_parser():
    adapter = BankLedgerAdapter()
    csv_data = """transaction_date,value_date,narration,ref_no,credit,debit,currency
2026-08-01,2026-08-01,CMS/RZP/pay_001/CREDIT,UTR001,4882.0,0.0,INR
2026-08-02,2026-08-02,REFUND DEBIT,UTR002,0.0,2500.0,INR
"""
    txs = adapter.parse(csv_data)
    assert len(txs) == 2
    assert txs[0].source == TransactionSource.BANK_LEDGER
    assert txs[0].amount == 4882.0
    assert txs[0].net_amount == 4882.0
    assert txs[0].status == TransactionStatus.SETTLED
    assert txs[1].status == TransactionStatus.REFUNDED
