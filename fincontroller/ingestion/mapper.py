"""
Schema-Agnostic Column Mapping, Auto-Detection, and Type Coercion Engine.
Handles arbitrary financial formats (Stripe, PayPal, HDFC, ICICI, Quickbooks, custom ERPs).
"""

from datetime import datetime
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd
from pydantic import BaseModel, Field

from fincontroller.core.exceptions import IngestionError


class ColumnAliases:
    """Standard aliases for common financial fields across global gateways and banks."""

    AMOUNT: List[str] = [
        "amount", "amt", "net_amount", "gross_amount", "gross", "paid_amount", "payment_amount",
        "txn_amount", "transaction_amount", "credit", "credit_amount", "deposit", "deposit_amt",
        "deposit_amount", "value", "total", "volume", "net_value", "total_amount", "bill_amount",
        "settled_amount", "trans_amount"
    ]

    DEBIT: List[str] = [
        "debit", "withdrawal", "withdrawal_amt", "debit_amount", "withdrawal_amount", "dr",
        "payout_amount", "refund_amount"
    ]

    FEE: List[str] = [
        "fee", "fees", "mdr", "gateway_fee", "service_fee", "platform_fee", "commission",
        "processing_fee", "charge", "charges", "paypal_fee", "stripe_fee"
    ]

    TAX: List[str] = [
        "tax", "gst", "vat", "tds", "service_tax", "cgst", "sgst", "igst", "tax_amount"
    ]

    NET_AMOUNT: List[str] = [
        "net_amount", "net_settled", "net", "settlement_amount", "net_credit", "net_payout",
        "net_value", "net_total", "amount_settled"
    ]

    REFERENCE_ID: List[str] = [
        "reference_id", "ref_id", "ref_no", "ref", "reference", "utr", "rrn", "arn",
        "transaction_id", "txn_id", "tx_id", "payment_id", "entity_id", "order_id",
        "cheque_no", "chq_no", "chq_ref_number", "ext_ref", "external_id", "bank_ref",
        "payout_utr", "settlement_utr", "batch_id", "custom_ref", "client_reference"
    ]

    RAW_ID: List[str] = [
        "id", "raw_id", "entity_id", "payment_id", "tx_id", "txn_id", "entry_id",
        "record_id", "identifier", "internal_id", "doc_number"
    ]

    TIMESTAMP: List[str] = [
        "timestamp", "date", "txn_date", "transaction_date", "value_date", "settled_at",
        "created_at", "created", "created_utc", "time", "datetime", "booking_date",
        "trans_date", "posted_date", "post_date", "settlement_date", "event_time", "timestamp_epoch"
    ]

    DESCRIPTION: List[str] = [
        "description", "narration", "particulars", "remarks", "notes", "memo",
        "details", "transaction_remarks", "concept", "message", "narrative", "line_description"
    ]

    CURRENCY: List[str] = [
        "currency", "curr", "ccy", "iso_currency", "currency_code", "currency_iso", "val_ccy"
    ]

    COUNTERPARTY: List[str] = [
        "counterparty", "merchant_name", "merchant", "customer_email", "beneficiary",
        "payee", "payer", "account_name", "sender", "receiver", "customer", "vendor"
    ]

    STATUS: List[str] = [
        "status", "state", "txn_status", "transaction_status", "payment_status", "settlement_status"
    ]


class ColumnMappingConfig(BaseModel):
    """Explicit or auto-detected column mapping definition."""
    amount: Optional[str] = None
    debit: Optional[str] = None
    fee: Optional[str] = None
    tax: Optional[str] = None
    net_amount: Optional[str] = None
    reference_id: Optional[str] = None
    raw_id: Optional[str] = None
    timestamp: Optional[str] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    counterparty: Optional[str] = None
    status: Optional[str] = None


class ColumnMapper:
    """
    Intelligent Schema Auto-Detector and Field Mapper for arbitrary financial datasets.
    """

    @classmethod
    def clean_column_name(cls, col: str) -> str:
        """Normalize column name for comparison."""
        return re.sub(r"[^a-z0-9]", "_", str(col).strip().lower()).strip("_")

    @classmethod
    def auto_detect_mapping(
        cls,
        df_columns: List[str],
        user_override: Optional[Dict[str, str] | ColumnMappingConfig] = None,
    ) -> ColumnMappingConfig:
        """
        Auto-detect column mappings with fuzzy alias matching, respecting user overrides.
        """
        if isinstance(user_override, ColumnMappingConfig):
            override_dict = user_override.model_dump(exclude_none=True)
        elif isinstance(user_override, dict):
            override_dict = {k: v for k, v in user_override.items() if v}
        else:
            override_dict = {}

        cleaned_to_orig = {cls.clean_column_name(c): c for c in df_columns}
        cleaned_cols = list(cleaned_to_orig.keys())

        result: Dict[str, str] = {}

        # 1. Apply explicit user overrides first
        for canonical_field, user_col in override_dict.items():
            if user_col in df_columns:
                result[canonical_field] = user_col
            elif cls.clean_column_name(user_col) in cleaned_to_orig:
                result[canonical_field] = cleaned_to_orig[cls.clean_column_name(user_col)]

        # 2. Auto-detect remaining fields
        fields_to_detect = {
            "amount": ColumnAliases.AMOUNT,
            "debit": ColumnAliases.DEBIT,
            "fee": ColumnAliases.FEE,
            "tax": ColumnAliases.TAX,
            "net_amount": ColumnAliases.NET_AMOUNT,
            "reference_id": ColumnAliases.REFERENCE_ID,
            "raw_id": ColumnAliases.RAW_ID,
            "timestamp": ColumnAliases.TIMESTAMP,
            "description": ColumnAliases.DESCRIPTION,
            "currency": ColumnAliases.CURRENCY,
            "counterparty": ColumnAliases.COUNTERPARTY,
            "status": ColumnAliases.STATUS,
        }

        for field_name, aliases in fields_to_detect.items():
            if field_name in result:
                continue

            for alias in aliases:
                clean_alias = cls.clean_column_name(alias)
                # Exact match against cleaned column
                if clean_alias in cleaned_to_orig:
                    result[field_name] = cleaned_to_orig[clean_alias]
                    break
                # Partial match check (e.g., 'created_utc' -> 'created')
                for c_col in cleaned_cols:
                    if clean_alias == c_col or (len(clean_alias) > 3 and clean_alias in c_col.split("_")):
                        result[field_name] = cleaned_to_orig[c_col]
                        break
                if field_name in result:
                    break

        return ColumnMappingConfig(**result)

    @classmethod
    def parse_numeric(cls, val: Any, default: float = 0.0) -> float:
        """Parse dirty currency/numeric strings into clean float."""
        if val is None or pd.isna(val):
            return default
        if isinstance(val, (int, float)):
            return float(val)

        val_str = str(val).strip()
        # Remove currency symbols (₹, $, €, £, INR, USD, etc.) and commas/spaces
        cleaned = re.sub(r"[^\d.-]", "", val_str.replace(",", ""))
        if not cleaned or cleaned == "-":
            return default
        try:
            return float(cleaned)
        except ValueError:
            return default

    @classmethod
    def parse_datetime(cls, val: Any) -> datetime:
        """Robust date parser handling ISO, Indian, US, and epoch timestamps."""
        if val is None or pd.isna(val):
            return datetime.now()
        if isinstance(val, datetime):
            return val

        if isinstance(val, (int, float)):
            # Epoch in seconds or milliseconds
            if val > 1e11:  # Milliseconds
                val /= 1000.0
            try:
                return datetime.fromtimestamp(val)
            except Exception:
                return datetime.now()

        val_str = str(val).strip()
        if not val_str:
            return datetime.now()

        try:
            if re.match(r"^\d{4}-\d{2}-\d{2}", val_str):
                return pd.to_datetime(val_str, dayfirst=False).to_pydatetime()
            if "/" in val_str:
                return pd.to_datetime(val_str, dayfirst=True).to_pydatetime()
            return pd.to_datetime(val_str).to_pydatetime()
        except Exception:
            try:
                return pd.to_datetime(val_str, dayfirst=False).to_pydatetime()
            except Exception:
                return datetime.now()
