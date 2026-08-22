"""
Financial Controller Executive Summary Generator.
"""

from fincontroller.core.models import ReconciliationReport
from fincontroller.rag.fallback_templates import DeterministicFallbackEngine


class FinancialSummarizer:
    """Generates comprehensive daily exception & reconciliation summaries."""

    @staticmethod
    def generate_executive_summary(report: ReconciliationReport) -> str:
        return DeterministicFallbackEngine.generate_summary(report)
