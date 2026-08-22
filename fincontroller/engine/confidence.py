"""
Confidence scoring and reason classification helpers.
"""

from fincontroller.core.config import settings
from fincontroller.core.models import MatchCategory, MatchReasonCode


class ConfidenceScorer:
    """Computes deterministic confidence metrics."""

    @staticmethod
    def classify_score(score: float, is_ambiguous: bool = False) -> MatchCategory:
        if is_ambiguous:
            return MatchCategory.NEEDS_HUMAN_REVIEW
        if score >= settings.AUTO_MATCH_THRESHOLD:
            return MatchCategory.AUTO_MATCHED
        elif score >= settings.HUMAN_REVIEW_THRESHOLD:
            return MatchCategory.NEEDS_HUMAN_REVIEW
        else:
            return MatchCategory.UNMATCHED

    @staticmethod
    def score_fuzzy_match(string_similarity: float, date_diff_hours: float, amount_diff: float) -> float:
        """
        Confidence formula:
        Base = string_similarity * 0.70 + (1.0 - min(amount_diff, 1.0)) * 0.20 + (1.0 - min(date_diff_hours/72.0, 1.0)) * 0.10
        """
        sim_component = max(0.0, min(1.0, string_similarity)) * 0.70
        amt_component = max(0.0, 1.0 - min(amount_diff, 1.0)) * 0.20
        date_component = max(0.0, 1.0 - min(date_diff_hours / 72.0, 1.0)) * 0.10
        return round(sim_component + amt_component + date_component, 3)
