"""
Base Ingestion Adapter and string reference extractors.
"""

from abc import ABC, abstractmethod
import re
from typing import List, Optional
from datetime import datetime
import pandas as pd
from fincontroller.core.models import NormalizedTransaction, TransactionSource, TransactionStatus


class BaseIngestionAdapter(ABC):
    """Abstract base class for financial source adapters."""

    @abstractmethod
    def parse(self, data: bytes | str | pd.DataFrame) -> List[NormalizedTransaction]:
        """Parse source data into normalized transaction models."""
        pass

    @staticmethod
    def extract_reference_id(text: Optional[str]) -> str:
        """
        Extract clean transaction identifiers (UTR, payment IDs, ARN, settlement IDs)
        from free-form narrations or reference fields.
        """
        if not text or pd.isna(text):
            return ""

        text = str(text).strip()

        # Specific prefix tokens (Razorpay, Stripe, PayPal, UTR, etc.)
        for pattern in [
            r"\b(pay_[a-zA-Z0-9_-]{3,35})\b",
            r"\b(setl_[a-zA-Z0-9_-]{3,35})\b",
            r"\b(rfnd_[a-zA-Z0-9_-]{3,35})\b",
            r"\b(ch_[a-zA-Z0-9_-]{10,35})\b",
            r"\b(pi_[a-zA-Z0-9_-]{10,35})\b",
            r"(?:^|[\s/-])(UTR_?[a-zA-Z0-9]{6,30})(?:$|[\s/-])",
            r"\b(PP_TXN_[a-zA-Z0-9_-]{3,30})\b",
            r"\b(txn_[a-zA-Z0-9_-]{3,35})\b",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        # Standard Indian Banking UTR / RRN (12-22 alphanumeric without special chars)
        match = re.search(r"\b([A-Z0-9]{12,22})\b", text)
        if match and sum(1 for c in match.group(1) if c.isdigit()) >= 3:
            return match.group(1)

        # Alphanumeric tokens with mixed letters & digits (e.g. UTR_EX_0001, CMS348291048291)
        for token in re.split(r"[\s/]+", text):
            token = token.strip(" -:,.")
            digit_count = sum(1 for c in token if c.isdigit())
            if digit_count >= 3 and 8 <= len(token) <= 30:
                return token

        return text
