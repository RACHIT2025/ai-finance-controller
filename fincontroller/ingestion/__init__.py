"""
Ingestion modules for FinController.
"""

from fincontroller.ingestion.base import BaseIngestionAdapter
from fincontroller.ingestion.razorpay_adapter import RazorpayAdapter
from fincontroller.ingestion.bank_ledger_adapter import BankLedgerAdapter
from fincontroller.ingestion.generator import generate_benchmark_dataset
from fincontroller.ingestion.mapper import ColumnMapper, ColumnMappingConfig
from fincontroller.ingestion.generic_adapter import SchemaAgnosticAdapter

__all__ = [
    "BaseIngestionAdapter",
    "RazorpayAdapter",
    "BankLedgerAdapter",
    "generate_benchmark_dataset",
    "ColumnMapper",
    "ColumnMappingConfig",
    "SchemaAgnosticAdapter",
]
