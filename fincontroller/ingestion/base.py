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

        # Razorpay Payment IDs: pay_XXXXXXXXXXXXXX
        match = re.search(r"\b(pay_[a-zA-Z0-9]{10,20})\b", text)
        if match:
            return match.group(1)

        # Razorpay Settlement IDs: setl_XXXXXXXXXXXXXX
        match = re.search(r"\b(setl_[a-zA-Z0-9]{10,20})\b", text)
        if match:
            return match.group(1)

        # Razorpay Refund IDs: rfnd_XXXXXXXXXXXXXX
        match = re.search(r"\b(rfnd_[a-zA-Z0-9]{10,20})\b", text)
        if match:
            return match.group(1)

        # Standard Indian Banking UTR / RRN (12-22 alphanumeric)
        # e.g., CMS/348291048291/RZP, NEFT-HDFC000123-348291048291
        match = re.search(r"\b([A-Z0-9]{12,22})\b", text)
        if match:
            return match.group(1)

        # Order or general alphanumeric tokens
        match = re.search(r"\b([A-Za-z0-9_-]{6,30})\b", text)
        if match:
            return match.group(1)

        return text
