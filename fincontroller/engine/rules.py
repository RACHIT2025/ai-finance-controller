"""
Deterministic matching rules and comparison heuristics.
Zero LLM involvement — purely deterministic, mathematical and explainable.
"""

from datetime import datetime
import difflib
from typing import Optional, Tuple
from fincontroller.core.config import settings
from fincontroller.core.models import NormalizedTransaction


class MatchingRules:
    """Rule checkers for deterministic reconciliation."""

    @staticmethod
    def calculate_string_similarity(str1: str, str2: str) -> float:
        """
        Compute similarity ratio between two reference strings.
        Uses SequenceMatcher (Ratcliff-Obershelp).
        """
        if not str1 or not str2:
            return 0.0
        s1 = str1.strip().upper()
        s2 = str2.strip().upper()
        if s1 == s2:
            return 1.0
        
        # Check substring inclusion
        if len(s1) >= 6 and (s1 in s2 or s2 in s1):
            return 0.95

        return difflib.SequenceMatcher(None, s1, s2).ratio()

    @staticmethod
    def is_exact_ref_match(tx1: NormalizedTransaction, tx2: NormalizedTransaction) -> bool:
        """Check if transactions share a non-empty identical reference ID or UTR."""
        if not tx1.reference_id or not tx2.reference_id:
            return False
        
        ref1 = tx1.reference_id.strip().upper()
        ref2 = tx2.reference_id.strip().upper()
        
        if ref1 == ref2:
            return True
            
        # Cross-reference check with raw IDs or description UTR
        raw1 = tx1.raw_id.strip().upper()
        raw2 = tx2.raw_id.strip().upper()
        if raw1 == ref2 or raw2 == ref1 or raw1 == raw2:
            return True

        desc1 = (tx1.description or "").strip().upper()
        desc2 = (tx2.description or "").strip().upper()

        if len(ref1) >= 6 and (ref1 in desc2 or ref1 in raw2):
            return True
        if len(ref2) >= 6 and (ref2 in desc1 or ref2 in raw1):
            return True
        if len(raw1) >= 6 and (raw1 in desc2 or raw1 in ref2):
            return True
        if len(raw2) >= 6 and (raw2 in desc1 or raw2 in ref1):
            return True

        return False

    @staticmethod
    def is_amount_exact_match(
        amount1: float, amount2: float, tolerance: float = settings.AMOUNT_ABSOLUTE_TOLERANCE
    ) -> bool:
        """Check if amounts match within absolute tolerance."""
        return abs(round(amount1, 2) - round(amount2, 2)) <= tolerance

    @staticmethod
    def is_fee_adjusted_match(
        gateway_tx: NormalizedTransaction, bank_tx: NormalizedTransaction
    ) -> Tuple[bool, float]:
        """
        Check if bank amount matches gateway net amount after fees and taxes across
        dynamic payment method tiers (Credit Cards, Debit Cards, International, IMPS/NEFT).
        Returns (is_match, detected_fee).
        """
        # Case 1: Gateway already has explicit fee and tax calculated
        if gateway_tx.fee > 0 or gateway_tx.tax > 0:
            if MatchingRules.is_amount_exact_match(gateway_tx.net_amount, bank_tx.net_amount):
                return True, round(gateway_tx.fee + gateway_tx.tax, 2)

        gross = gateway_tx.amount
        if gross <= 0:
            return False, 0.0

        # Tiered MDR profiles (MDR % + 18% GST on MDR)
        mdr_tiers = [
            0.02,     # Standard CC / Gateway Default (2.00% + 18% GST = 2.36%)
            0.0199,   # Standard Merchant Tier (1.99% + 18% GST = 2.3482%)
            0.0090,   # Domestic Debit Card (0.90% + 18% GST = 1.062%)
            0.0299,   # International / Amex (2.99% + 18% GST = 3.5282%)
            0.0150,   # SME Discounted Tier (1.50% + 18% GST = 1.77%)
        ]

        for mdr in mdr_tiers:
            expected_mdr = round(gross * mdr, 2)
            expected_gst = round(expected_mdr * settings.DEFAULT_GST_ON_FEE_PERCENT, 2)
            calculated_net = round(gross - (expected_mdr + expected_gst), 2)
            if MatchingRules.is_amount_exact_match(calculated_net, bank_tx.net_amount, tolerance=1.50):
                return True, round(expected_mdr + expected_gst, 2)

        # Flat IMPS / NEFT settlement fee deductions (₹5, ₹10, ₹15, ₹20)
        for flat_fee in [5.0, 10.0, 15.0, 20.0]:
            if MatchingRules.is_amount_exact_match(gross - flat_fee, bank_tx.net_amount, tolerance=0.50):
                return True, flat_fee

        return False, 0.0


    @staticmethod
    def get_date_delta_hours(dt1: datetime, dt2: datetime) -> float:
        """Calculate absolute difference between timestamps in hours."""
        return abs((dt1 - dt2).total_seconds()) / 3600.0

    @staticmethod
    def is_within_date_window(
        dt1: datetime, dt2: datetime, max_days: int = settings.DATE_WINDOW_DAYS
    ) -> bool:
        """Check if timestamps are within allowable settlement drift window."""
        delta_days = abs((dt1 - dt2).total_seconds()) / 86400.0
        return delta_days <= max_days
