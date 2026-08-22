"""
Resilient Deterministic Fallback Template Generator.
Provides guaranteed natural language responses when LLM APIs are offline,
unconfigured, or rate-limited.
"""

from typing import Any, Dict, List, Optional
from fincontroller.core.models import MatchCategory, MatchPair, NormalizedTransaction, ReconciliationReport
from fincontroller.resilience.logger import telemetry


class DeterministicFallbackEngine:
    """
    Generates rule-based natural language explanations and summaries
    with 100% deterministic reliability.
    """

    @classmethod
    def explain_transaction(
        cls,
        tx_id_or_ref: str,
        report: ReconciliationReport,
    ) -> str:
        """Explain why a specific transaction matched or failed to match."""
        import re
        telemetry.push(
            level="INFO",
            component="FALLBACK_LLM",
            message=f"Serving deterministic template explanation for query '{tx_id_or_ref}' (Offline / Fallback mode active).",
            metadata={"query": tx_id_or_ref, "engine": "DeterministicTemplateEngine"},
        )

        query = tx_id_or_ref.strip().lower()

        # Extract potential specific token identifiers from conversational sentences
        extracted_tokens = re.findall(r"(?:pay_|setl_|rfnd_|bnk_|rzp_|utr_)[a-zA-Z0-9_-]+", query, re.IGNORECASE)
        candidate_terms = [query] + [t.lower() for t in extracted_tokens]

        # Check in Auto Matches
        for m in report.matches:
            for term in candidate_terms:
                if (
                    any(term in gw_id.lower() for gw_id in m.gateway_tx_ids)
                    or any(term in bnk_id.lower() for bnk_id in m.bank_tx_ids)
                    or term in m.match_id.lower()
                    or term in m.explanation.lower()
                    or term in m.reason_code.value.lower()
                ):
                    return (
                        f"### ✅ Reconciled Successfully (Auto-Matched)\n\n"
                        f"- **Match ID**: `{m.match_id}`\n"
                        f"- **Classification**: **{m.category.value}** (Confidence: **{m.confidence * 100:.1f}%**)\n"
                        f"- **Reason Code**: `{m.reason_code.value}`\n"
                        f"- **Explanation**: {m.explanation}\n"
                        f"- **Gateway Transactions**: {', '.join(f'`{g}`' for g in m.gateway_tx_ids)}\n"
                        f"- **Bank Transactions**: {', '.join(f'`{b}`' for b in m.bank_tx_ids)}\n"
                        f"- **Fee Deducted**: ₹{m.fee_detected:,.2f}\n"
                        f"- **Discrepancy**: ₹{m.amount_discrepancy:,.2f}\n"
                        f"- **Settlement Drift**: {m.date_diff_hours:.1f} hours\n"
                    )

        # Check in Human Reviews
        for hr in report.human_reviews:
            for term in candidate_terms:
                if (
                    any(term in gw_id.lower() for gw_id in hr.gateway_tx_ids)
                    or any(term in bnk_id.lower() for bnk_id in hr.bank_tx_ids)
                    or term in hr.match_id.lower()
                    or term in hr.explanation.lower()
                    or term in hr.reason_code.value.lower()
                ):
                    return (
                        f"### ⚠️ Needs Human Review (Ambiguity Flagged)\n\n"
                        f"- **Review ID**: `{hr.match_id}`\n"
                        f"- **Classification**: **{hr.category.value}** (Confidence: **{hr.confidence * 100:.1f}%**)\n"
                        f"- **Reason Code**: `{hr.reason_code.value}`\n"
                        f"- **Investigation Note**: {hr.explanation}\n"
                        f"- **Action Required**: Verify bank credit attribution. Two or more candidate records share identical parameters.\n"
                    )

        # Check in Unmatched Gateway
        for gw in report.unmatched_gateway:
            for term in candidate_terms:
                if term in gw.id.lower() or term in gw.reference_id.lower() or term in gw.raw_id.lower():
                    return (
                        f"### ❌ Unmatched Gateway Transaction\n\n"
                        f"- **Transaction ID**: `{gw.id}` (Ref: `{gw.reference_id}`)\n"
                        f"- **Source**: Razorpay Gateway\n"
                        f"- **Gross Amount**: ₹{gw.amount:,.2f} | **Expected Net**: ₹{gw.net_amount:,.2f}\n"
                        f"- **Status**: `{gw.status.value}`\n"
                        f"- **Timestamp**: {gw.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"- **Diagnosis**: No corresponding deposit found in bank statement within the 3-day settlement window. "
                        f"Transaction may be in risk hold escrow, unsettled batch, or delayed bank NEFT clearing."
                    )

        # Check in Unmatched Bank
        for bnk in report.unmatched_bank:
            for term in candidate_terms:
                if term in bnk.id.lower() or term in bnk.reference_id.lower() or term in bnk.raw_id.lower():
                    return (
                        f"### ❌ Unmatched Bank Deposit (Orphaned Credit)\n\n"
                        f"- **Transaction ID**: `{bnk.id}` (Ref: `{bnk.reference_id}`)\n"
                        f"- **Source**: Bank Statement Feed\n"
                        f"- **Received Net Credit**: ₹{bnk.net_amount:,.2f}\n"
                        f"- **Narration**: `{bnk.description}`\n"
                        f"- **Value Date**: {bnk.timestamp.strftime('%Y-%m-%d')}\n"
                        f"- **Diagnosis**: Bank account received funds without a corresponding Razorpay settlement entry. "
                        f"Likely a direct client NEFT/RTGS transfer or non-gateway deposit."
                    )

        return (
            f"### 🔍 Search Query Not Found\n\n"
            f"No matching record found for query: `{tx_id_or_ref}`.\n\n"
            f"**Total Records Evaluated**:\n"
            f"- Auto-Matched: {len(report.matches)}\n"
            f"- Needs Human Review: {len(report.human_reviews)}\n"
            f"- Unmatched Gateway: {len(report.unmatched_gateway)}\n"
            f"- Unmatched Bank: {len(report.unmatched_bank)}"
        )

    @classmethod
    def generate_summary(cls, report: ReconciliationReport) -> str:
        """Generate structured executive summary for the financial controller."""
        s = report.summary
        return (
            f"# 📊 Financial Controller Daily Reconciliation Summary\n\n"
            f"**Session ID**: `{report.session_id}` | **Run Date**: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"## 1. Executive Overview\n"
            f"- **Total Gateway Volume Processed**: ₹{s.total_gateway_volume:,.2f} ({s.total_gateway_tx} txs)\n"
            f"- **Total Bank Volume Received**: ₹{s.total_bank_volume:,.2f} ({s.total_bank_tx} txs)\n"
            f"- **Successfully Reconciled Volume**: ₹{s.reconciled_volume:,.2f}\n"
            f"- **Auto-Match Accuracy Rate**: **{s.auto_match_rate:.1f}%**\n"
            f"- **Total Gateway Fees Accounted**: ₹{s.total_fee_volume:,.2f}\n"
            f"- **Reconciliation Execution Time**: {s.execution_time_ms:.1f} ms\n\n"
            f"## 2. Decision Bucketing & Classification\n"
            f"| Bucket | Transactions / Pairs | Volume (INR) | Operational Action |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"| **✅ Auto-Matched** | {s.auto_matched_count} pairs | ₹{s.reconciled_volume:,.2f} | Fully verified & signed into audit chain |\n"
            f"| **⚠️ Needs Human Review** | {s.human_review_count} cases | N/A | Ambiguous duplicate/conflict candidates |\n"
            f"| **❌ Unmatched Gateway** | {s.unmatched_gateway_count} txs | ₹{s.unmatched_gateway_volume:,.2f} | Outstanding receivable / escrow hold |\n"
            f"| **❌ Unmatched Bank** | {s.unmatched_bank_count} txs | ₹{s.unmatched_bank_volume:,.2f} | Unclaimed direct bank deposit |\n\n"
            f"## 3. Cryptographic Audit Trail\n"
            f"- **Chain Head**: `{report.audit_chain_head[:16]}...`\n"
            f"- **Total Immutable Blocks**: {report.audit_block_count}\n"
            f"- **Status**: Cryptographically sealed with SHA-256 hash-chaining."
        )
