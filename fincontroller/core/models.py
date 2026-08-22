"""
Domain schemas and Pydantic models for the FinController reconciliation engine.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class TransactionSource(str, Enum):
    RAZORPAY = "RAZORPAY"
    BANK_LEDGER = "BANK_LEDGER"
    INTERNAL_ERP = "INTERNAL_ERP"


class TransactionStatus(str, Enum):
    SETTLED = "SETTLED"
    CAPTURED = "CAPTURED"
    PENDING = "PENDING"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    CHARGEBACK = "CHARGEBACK"


class MatchCategory(str, Enum):
    AUTO_MATCHED = "AUTO_MATCHED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    UNMATCHED = "UNMATCHED"


class MatchReasonCode(str, Enum):
    # High Confidence Match Reasons (AUTO_MATCHED)
    EXACT_MATCH_REF_AND_AMOUNT = "EXACT_MATCH_REF_AND_AMOUNT"
    FEE_ADJUSTED_MATCH = "FEE_ADJUSTED_MATCH"
    SPLIT_BATCH_MATCH = "SPLIT_BATCH_MATCH"
    FUZZY_REF_EXACT_AMOUNT_MATCH = "FUZZY_REF_EXACT_AMOUNT_MATCH"
    AMOUNT_TOLERANCE_MATCH = "AMOUNT_TOLERANCE_MATCH"

    # Ambiguous Match Reasons (NEEDS_HUMAN_REVIEW)
    AMBIGUOUS_DUPLICATE_CANDIDATES = "AMBIGUOUS_DUPLICATE_CANDIDATES"
    FEE_MISMATCH_EXCEEDS_TOLERANCE = "FEE_MISMATCH_EXCEEDS_TOLERANCE"
    DATE_OUTSIDE_WINDOW = "DATE_OUTSIDE_WINDOW"
    SUSPECTED_SPLIT_PARTIAL_MATCH = "SUSPECTED_SPLIT_PARTIAL_MATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    HIGH_FUZZY_LOW_CONFIDENCE = "HIGH_FUZZY_LOW_CONFIDENCE"
    MANUAL_REVIEW_FLAGGED = "MANUAL_REVIEW_FLAGGED"

    # Unmatched Reasons (UNMATCHED)
    NO_PLAUSIBLE_MATCH = "NO_PLAUSIBLE_MATCH"
    ORPHANED_BANK_CREDIT = "ORPHANED_BANK_CREDIT"
    UNSETTLED_GATEWAY_PAYMENT = "UNSETTLED_GATEWAY_PAYMENT"


class NormalizedTransaction(BaseModel):
    """Canonical normalized transaction representation across all data sources."""
    id: str = Field(description="Unique internal ID for this transaction")
    source: TransactionSource = Field(description="Source origin of the transaction")
    raw_id: str = Field(description="Original ID in the source system (e.g. pay_xxx, UTR)")
    amount: float = Field(description="Gross transaction amount in base currency")
    fee: float = Field(default=0.0, description="Deducted gateway fee")
    tax: float = Field(default=0.0, description="Deducted tax (GST/TDS)")
    net_amount: float = Field(description="Net expected/received settlement amount")
    currency: str = Field(default="INR", description="3-letter ISO currency code")
    timestamp: datetime = Field(description="Transaction event or value timestamp")
    reference_id: str = Field(description="Extracted clean reference identifier (UTR, payment_id, arn)")
    counterparty: Optional[str] = Field(default=None, description="Counterparty name or account details")
    description: Optional[str] = Field(default=None, description="Original transaction narration")
    status: TransactionStatus = Field(default=TransactionStatus.SETTLED, description="Current transaction status")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary raw metadata")

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("reference_id")
    @classmethod
    def clean_reference(cls, v: str) -> str:
        return v.strip()


class MatchPair(BaseModel):
    """Represents a reconciliation linkage between 1-to-1, 1-to-N, or N-to-1 transactions."""
    match_id: str = Field(description="Unique ID for this match pair/cluster")
    gateway_tx_ids: List[str] = Field(default_factory=list, description="IDs of matching Razorpay/gateway transactions")
    bank_tx_ids: List[str] = Field(default_factory=list, description="IDs of matching bank statement transactions")
    category: MatchCategory = Field(description="Classification bucket")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reason_code: MatchReasonCode = Field(description="Deterministic reason code")
    explanation: str = Field(description="Human and audit-readable explanation of the match decision")
    amount_discrepancy: float = Field(default=0.0, description="Gross/Net difference in base currency")
    date_diff_hours: float = Field(default=0.0, description="Time gap between source events in hours")
    fee_detected: float = Field(default=0.0, description="Total fee accounted for in this reconciliation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Auxiliary matching telemetry")


class ReconciliationSummary(BaseModel):
    """Aggregate statistics for a reconciliation run."""
    total_gateway_tx: int
    total_bank_tx: int
    auto_matched_count: int
    human_review_count: int
    unmatched_gateway_count: int
    unmatched_bank_count: int
    
    total_gateway_volume: float
    total_bank_volume: float
    reconciled_volume: float
    unmatched_gateway_volume: float
    unmatched_bank_volume: float
    total_fee_volume: float
    
    auto_match_rate: float
    execution_time_ms: float


class ReconciliationReport(BaseModel):
    """Full reconciliation output bundle."""
    session_id: str
    timestamp: datetime
    summary: ReconciliationSummary
    matches: List[MatchPair]
    human_reviews: List[MatchPair]
    unmatched_gateway: List[NormalizedTransaction]
    unmatched_bank: List[NormalizedTransaction]
    audit_chain_head: str
    audit_block_count: int


class AuditBlock(BaseModel):
    """Single immutable block in the cryptographic hash chain."""
    index: int
    timestamp: str
    previous_hash: str
    block_hash: str
    event_type: str
    payload_hash: str
    payload: Dict[str, Any]
    operator: str = "FIN_CONTROLLER_ENGINE_V1"
