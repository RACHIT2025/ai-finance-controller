"""
Split and Batch Settlement Resolver.
Detects and resolves 1-to-N settlement relationships deterministically.
"""

from itertools import combinations
from typing import List, Optional, Tuple
from fincontroller.core.config import settings
from fincontroller.core.models import (
    MatchCategory,
    MatchPair,
    MatchReasonCode,
    NormalizedTransaction,
)
from fincontroller.engine.rules import MatchingRules


class SplitSettlementResolver:
    """Resolves bulk bank settlements composed of multiple gateway payouts."""

    @staticmethod
    def resolve_by_reference_group(
        unmatched_gateway: List[NormalizedTransaction],
        unmatched_bank: List[NormalizedTransaction],
    ) -> Tuple[List[MatchPair], List[NormalizedTransaction], List[NormalizedTransaction]]:
        """
        Group gateway transactions by reference_id / UTR and match against single bank transactions.
        """
        matches: List[MatchPair] = []
        matched_gw_ids = set()
        matched_bnk_ids = set()

        # Build reference lookup for gateway items
        gw_by_ref = {}
        for gw in unmatched_gateway:
            if gw.reference_id:
                gw_by_ref.setdefault(gw.reference_id.upper(), []).append(gw)

        for bnk in unmatched_bank:
            if bnk.id in matched_bnk_ids:
                continue

            bnk_ref = bnk.reference_id.upper() if bnk.reference_id else ""
            candidate_gw_list = gw_by_ref.get(bnk_ref, [])

            if len(candidate_gw_list) >= 2:
                # Check if sum matches
                total_gw_net = sum(g.net_amount for g in candidate_gw_list)
                total_gw_gross = sum(g.amount for g in candidate_gw_list)
                total_fee = sum(g.fee + g.tax for g in candidate_gw_list)

                if MatchingRules.is_amount_exact_match(total_gw_net, bnk.net_amount, tolerance=2.0):
                    gw_ids = [g.id for g in candidate_gw_list]
                    max_date_diff = max(
                        MatchingRules.get_date_delta_hours(g.timestamp, bnk.timestamp)
                        for g in candidate_gw_list
                    )
                    
                    pair = MatchPair(
                        match_id=f"match_split_ref_{bnk.id}",
                        gateway_tx_ids=gw_ids,
                        bank_tx_ids=[bnk.id],
                        category=MatchCategory.AUTO_MATCHED,
                        confidence=0.96,
                        reason_code=MatchReasonCode.SPLIT_BATCH_MATCH,
                        explanation=(
                            f"Bulk batch settlement matched by UTR '{bnk_ref}'. "
                            f"1 Bank credit of ₹{bnk.net_amount:,.2f} corresponds to {len(candidate_gw_list)} "
                            f"Razorpay payouts (Sum: ₹{total_gw_net:,.2f}, Total Fee: ₹{total_fee:,.2f})."
                        ),
                        amount_discrepancy=round(abs(total_gw_net - bnk.net_amount), 2),
                        date_diff_hours=round(max_date_diff, 1),
                        fee_detected=round(total_fee, 2),
                        metadata={"type": "1_to_N_ref_group", "count": len(candidate_gw_list)},
                    )
                    matches.append(pair)
                    matched_bnk_ids.add(bnk.id)
                    matched_gw_ids.update(gw_ids)

        remaining_gw = [g for g in unmatched_gateway if g.id not in matched_gw_ids]
        remaining_bnk = [b for b in unmatched_bank if b.id not in matched_bnk_ids]
        return matches, remaining_gw, remaining_bnk

    @staticmethod
    def resolve_by_subset_sum(
        unmatched_gateway: List[NormalizedTransaction],
        unmatched_bank: List[NormalizedTransaction],
        max_subset_size: int = settings.SPLIT_MAX_ITEMS,
    ) -> Tuple[List[MatchPair], List[NormalizedTransaction], List[NormalizedTransaction]]:
        """
        Combinatorial subset-sum solver for 1-to-N batch matches within date proximity window.
        """
        matches: List[MatchPair] = []
        matched_gw_ids = set()
        matched_bnk_ids = set()

        for bnk in unmatched_bank:
            if bnk.id in matched_bnk_ids:
                continue

            # Filter candidates within time window
            candidates = [
                g for g in unmatched_gateway
                if g.id not in matched_gw_ids
                and MatchingRules.is_within_date_window(g.timestamp, bnk.timestamp, max_days=3)
                and g.net_amount <= bnk.net_amount + 5.0
            ]

            if len(candidates) < 2:
                continue

            found_subset = None
            for k in range(2, min(max_subset_size + 1, len(candidates) + 1)):
                for subset in combinations(candidates, k):
                    sub_sum = sum(item.net_amount for item in subset)
                    if MatchingRules.is_amount_exact_match(sub_sum, bnk.net_amount, tolerance=1.0):
                        found_subset = subset
                        break
                if found_subset:
                    break

            if found_subset:
                gw_ids = [g.id for g in found_subset]
                total_sum = sum(g.net_amount for g in found_subset)
                total_fee = sum(g.fee + g.tax for g in found_subset)
                max_date_diff = max(
                    MatchingRules.get_date_delta_hours(g.timestamp, bnk.timestamp)
                    for g in found_subset
                )

                pair = MatchPair(
                    match_id=f"match_split_subset_{bnk.id}",
                    gateway_tx_ids=gw_ids,
                    bank_tx_ids=[bnk.id],
                    category=MatchCategory.AUTO_MATCHED,
                    confidence=0.92,
                    reason_code=MatchReasonCode.SPLIT_BATCH_MATCH,
                    explanation=(
                        f"Subset batch match discovered. 1 Bank credit of ₹{bnk.net_amount:,.2f} "
                        f"matches {len(found_subset)} gateway payouts totaling ₹{total_sum:,.2f}."
                    ),
                    amount_discrepancy=round(abs(total_sum - bnk.net_amount), 2),
                    date_diff_hours=round(max_date_diff, 1),
                    fee_detected=round(total_fee, 2),
                    metadata={"type": "1_to_N_subset_sum", "count": len(found_subset)},
                )
                matches.append(pair)
                matched_bnk_ids.add(bnk.id)
                matched_gw_ids.update(gw_ids)

        remaining_gw = [g for g in unmatched_gateway if g.id not in matched_gw_ids]
        remaining_bnk = [b for b in unmatched_bank if b.id not in matched_bnk_ids]
        return matches, remaining_gw, remaining_bnk
