"""
Deterministic Multi-Pass Matching Engine for Settlement Reconciliation.
Core rule-based layer — 100% explainable, deterministic, zero hallucinated math.
"""

from datetime import datetime
import time
from typing import Dict, List, Set, Tuple
from fincontroller.core.config import settings
from fincontroller.core.models import (
    MatchCategory,
    MatchPair,
    MatchReasonCode,
    NormalizedTransaction,
    ReconciliationReport,
    ReconciliationSummary,
)
from fincontroller.engine.confidence import ConfidenceScorer
from fincontroller.engine.rules import MatchingRules
from fincontroller.engine.split_resolver import SplitSettlementResolver


class DeterministicMatchingEngine:
    """
    Orchestrates multi-pass settlement reconciliation.
    """

    def __init__(self, session_id: str = "default_session"):
        self.session_id = session_id

    def reconcile(
        self,
        gateway_txs: List[NormalizedTransaction],
        bank_txs: List[NormalizedTransaction],
    ) -> ReconciliationReport:
        start_time = time.perf_counter()
        
        matches: List[MatchPair] = []
        human_reviews: List[MatchPair] = []

        unmatched_gateway: List[NormalizedTransaction] = list(gateway_txs)
        unmatched_bank: List[NormalizedTransaction] = list(bank_txs)

        matched_gw_ids: Set[str] = set()
        matched_bnk_ids: Set[str] = set()

        # =========================================================================
        # PASS 0: CONFLICT & AMBIGUOUS DUPLICATE DETECTION (PRE-PASS)
        # Prevents greedy auto-matching when multiple candidates compete for a counter-entry
        # =========================================================================
        # Group gateway items by reference_id
        gw_by_ref: Dict[str, List[NormalizedTransaction]] = {}
        for gw in unmatched_gateway:
            if gw.reference_id:
                gw_by_ref.setdefault(gw.reference_id.strip().upper(), []).append(gw)

        # Check for ambiguous duplicates where multiple gateway items share a ref with identical amounts
        # and there is only 1 bank item with that ref (not a split settlement)
        for ref_key, gw_list in gw_by_ref.items():
            if len(gw_list) >= 2:
                matching_banks = [
                    b for b in unmatched_bank 
                    if b.reference_id and b.reference_id.strip().upper() == ref_key
                ]
                # If there's 1 bank transaction whose net_amount equals individual gw item (not their sum)
                if len(matching_banks) == 1:
                    bnk = matching_banks[0]
                    # If sum does NOT match bnk, but individual amounts do -> ambiguous duplicate conflict!
                    gw_sum = sum(g.net_amount for g in gw_list)
                    if not MatchingRules.is_amount_exact_match(gw_sum, bnk.net_amount, tolerance=1.0):
                        if any(MatchingRules.is_amount_exact_match(g.net_amount, bnk.net_amount, tolerance=1.0) for g in gw_list):
                            gw_ids = [g.id for g in gw_list]
                            pair = MatchPair(
                                match_id=f"review_ambig_{bnk.id}",
                                gateway_tx_ids=gw_ids,
                                bank_tx_ids=[bnk.id],
                                category=MatchCategory.NEEDS_HUMAN_REVIEW,
                                confidence=0.50,
                                reason_code=MatchReasonCode.AMBIGUOUS_DUPLICATE_CANDIDATES,
                                explanation=(
                                    f"Ambiguous duplicate candidates detected on reference '{ref_key}'. "
                                    f"Bank credit of ₹{bnk.net_amount:,.2f} has {len(gw_list)} conflicting "
                                    f"Gateway payments ({', '.join(gw_ids)}). Refused auto-matching to prevent false linkage."
                                ),
                                amount_discrepancy=0.0,
                                date_diff_hours=0.0,
                                fee_detected=0.0,
                                metadata={"pass": 0, "contending_gw_ids": gw_ids},
                            )
                            human_reviews.append(pair)
                            matched_bnk_ids.add(bnk.id)
                            matched_gw_ids.update(gw_ids)

        unmatched_gateway = [g for g in unmatched_gateway if g.id not in matched_gw_ids]
        unmatched_bank = [b for b in unmatched_bank if b.id not in matched_bnk_ids]

        # =========================================================================
        # PASS 1: EXACT MATCH (Ref ID + Amount when zero fees)
        # =========================================================================
        remaining_gw: List[NormalizedTransaction] = []
        for gw in unmatched_gateway:
            matched_bnk = None
            if gw.fee == 0.0 and gw.tax == 0.0:
                for bnk in unmatched_bank:
                    if bnk.id in matched_bnk_ids:
                        continue
                    if gw.currency == bnk.currency and MatchingRules.is_exact_ref_match(gw, bnk):
                        if MatchingRules.is_amount_exact_match(gw.net_amount, bnk.net_amount, tolerance=0.01):
                            matched_bnk = bnk
                            break
            
            if matched_bnk:
                date_diff = MatchingRules.get_date_delta_hours(gw.timestamp, matched_bnk.timestamp)
                pair = MatchPair(
                    match_id=f"match_exact_{gw.id}_{matched_bnk.id}",
                    gateway_tx_ids=[gw.id],
                    bank_tx_ids=[matched_bnk.id],
                    category=MatchCategory.AUTO_MATCHED,
                    confidence=1.0,
                    reason_code=MatchReasonCode.EXACT_MATCH_REF_AND_AMOUNT,
                    explanation=(
                        f"Exact 1:1 match on reference '{gw.reference_id}' and net amount "
                        f"₹{gw.net_amount:,.2f} ({gw.currency}). Settled within {date_diff:.1f} hours."
                    ),
                    amount_discrepancy=0.0,
                    date_diff_hours=round(date_diff, 1),
                    fee_detected=0.0,
                    metadata={"pass": 1, "strategy": "EXACT_1_TO_1"},
                )
                matches.append(pair)
                matched_gw_ids.add(gw.id)
                matched_bnk_ids.add(matched_bnk.id)
            else:
                remaining_gw.append(gw)

        unmatched_gateway = remaining_gw
        unmatched_bank = [b for b in unmatched_bank if b.id not in matched_bnk_ids]

        # =========================================================================
        # PASS 2: FEE & TAX ADJUSTED MATCH (Ref ID + Net Settlement after MDR/GST)
        # =========================================================================
        remaining_gw = []
        for gw in unmatched_gateway:
            matched_bnk = None
            detected_fee = 0.0

            for bnk in unmatched_bank:
                if bnk.id in matched_bnk_ids:
                    continue
                if gw.currency == bnk.currency and MatchingRules.is_exact_ref_match(gw, bnk):
                    is_match, fee_calc = MatchingRules.is_fee_adjusted_match(gw, bnk)
                    if is_match:
                        matched_bnk = bnk
                        detected_fee = fee_calc
                        break

            if matched_bnk:
                date_diff = MatchingRules.get_date_delta_hours(gw.timestamp, matched_bnk.timestamp)
                pair = MatchPair(
                    match_id=f"match_fee_{gw.id}_{matched_bnk.id}",
                    gateway_tx_ids=[gw.id],
                    bank_tx_ids=[matched_bnk.id],
                    category=MatchCategory.AUTO_MATCHED,
                    confidence=0.98,
                    reason_code=MatchReasonCode.FEE_ADJUSTED_MATCH,
                    explanation=(
                        f"Fee-adjusted match on reference '{gw.reference_id}'. Gateway gross ₹{gw.amount:,.2f} "
                        f"reconciles to bank net ₹{matched_bnk.net_amount:,.2f} after detected fee/tax ₹{detected_fee:,.2f}."
                    ),
                    amount_discrepancy=round(abs(gw.amount - (matched_bnk.net_amount + detected_fee)), 2),
                    date_diff_hours=round(date_diff, 1),
                    fee_detected=detected_fee,
                    metadata={"pass": 2, "strategy": "FEE_ADJUSTED"},
                )
                matches.append(pair)
                matched_gw_ids.add(gw.id)
                matched_bnk_ids.add(matched_bnk.id)
            else:
                remaining_gw.append(gw)

        unmatched_gateway = remaining_gw
        unmatched_bank = [b for b in unmatched_bank if b.id not in matched_bnk_ids]

        # =========================================================================
        # PASS 3: SPLIT & BATCH SETTLEMENTS (1-to-N Grouping & Subset Sum)
        # =========================================================================
        # 3a. Reference-grouped batch
        split_ref_matches, unmatched_gateway, unmatched_bank = (
            SplitSettlementResolver.resolve_by_reference_group(unmatched_gateway, unmatched_bank)
        )
        matches.extend(split_ref_matches)
        for sm in split_ref_matches:
            matched_gw_ids.update(sm.gateway_tx_ids)
            matched_bnk_ids.update(sm.bank_tx_ids)

        # 3b. Subset-sum batch
        split_sum_matches, unmatched_gateway, unmatched_bank = (
            SplitSettlementResolver.resolve_by_subset_sum(unmatched_gateway, unmatched_bank)
        )
        matches.extend(split_sum_matches)
        for sm in split_sum_matches:
            matched_gw_ids.update(sm.gateway_tx_ids)
            matched_bnk_ids.update(sm.bank_tx_ids)

        # =========================================================================
        # PASS 4: FUZZY REFERENCE + EXACT AMOUNT MATCH (OCR/Typo Heuristic)
        # =========================================================================
        remaining_gw = []
        for gw in unmatched_gateway:
            best_bnk = None
            best_sim = 0.0

            for bnk in unmatched_bank:
                if bnk.id in matched_bnk_ids:
                    continue
                if gw.currency != bnk.currency:
                    continue
                if not MatchingRules.is_within_date_window(gw.timestamp, bnk.timestamp, max_days=3):
                    continue

                if MatchingRules.is_amount_exact_match(gw.net_amount, bnk.net_amount, tolerance=0.10):
                    sim = MatchingRules.calculate_string_similarity(gw.reference_id, bnk.reference_id)
                    # Also check narration similarity
                    narration_sim = MatchingRules.calculate_string_similarity(gw.reference_id, bnk.description)
                    sim = max(sim, narration_sim)
                    
                    if sim >= settings.FUZZY_STRING_SIMILARITY_THRESHOLD and sim > best_sim:
                        best_sim = sim
                        best_bnk = bnk

            if best_bnk and best_sim >= settings.FUZZY_STRING_SIMILARITY_THRESHOLD:
                date_diff = MatchingRules.get_date_delta_hours(gw.timestamp, best_bnk.timestamp)
                conf = ConfidenceScorer.score_fuzzy_match(best_sim, date_diff, 0.0)
                pair = MatchPair(
                    match_id=f"match_fuzzy_{gw.id}_{best_bnk.id}",
                    gateway_tx_ids=[gw.id],
                    bank_tx_ids=[best_bnk.id],
                    category=MatchCategory.AUTO_MATCHED if conf >= 0.85 else MatchCategory.NEEDS_HUMAN_REVIEW,
                    confidence=conf,
                    reason_code=MatchReasonCode.FUZZY_REF_EXACT_AMOUNT_MATCH,
                    explanation=(
                        f"Fuzzy reference match with {best_sim*100:.1f}% string similarity "
                        f"('{gw.reference_id}' ≈ '{best_bnk.reference_id}') and identical net amount ₹{gw.net_amount:,.2f}."
                    ),
                    amount_discrepancy=0.0,
                    date_diff_hours=round(date_diff, 1),
                    fee_detected=round(gw.fee + gw.tax, 2),
                    metadata={"pass": 4, "similarity": round(best_sim, 3)},
                )
                if pair.category == MatchCategory.AUTO_MATCHED:
                    matches.append(pair)
                else:
                    human_reviews.append(pair)
                matched_gw_ids.add(gw.id)
                matched_bnk_ids.add(best_bnk.id)
            else:
                remaining_gw.append(gw)

        unmatched_gateway = remaining_gw
        unmatched_bank = [b for b in unmatched_bank if b.id not in matched_bnk_ids]

        # =========================================================================
        # PASS 5: AMOUNT & DATE TOLERANCE MATCH (Paise Rounding & Delayed Drift)
        # =========================================================================
        remaining_gw = []
        for gw in unmatched_gateway:
            matched_bnk = None
            amt_diff = 0.0

            for bnk in unmatched_bank:
                if bnk.id in matched_bnk_ids:
                    continue
                if gw.currency == bnk.currency and MatchingRules.is_exact_ref_match(gw, bnk):
                    diff = abs(gw.net_amount - bnk.net_amount)
                    if diff <= settings.AMOUNT_ABSOLUTE_TOLERANCE and MatchingRules.is_within_date_window(
                        gw.timestamp, bnk.timestamp, max_days=settings.DATE_WINDOW_DAYS
                    ):
                        matched_bnk = bnk
                        amt_diff = diff
                        break

            if matched_bnk:
                date_diff = MatchingRules.get_date_delta_hours(gw.timestamp, matched_bnk.timestamp)
                pair = MatchPair(
                    match_id=f"match_tolerance_{gw.id}_{matched_bnk.id}",
                    gateway_tx_ids=[gw.id],
                    bank_tx_ids=[matched_bnk.id],
                    category=MatchCategory.AUTO_MATCHED,
                    confidence=0.88,
                    reason_code=MatchReasonCode.AMOUNT_TOLERANCE_MATCH,
                    explanation=(
                        f"Reconciled within tolerance. Reference '{gw.reference_id}' matched with "
                        f"₹{amt_diff:.2f} rounding discrepancy over {date_diff:.1f} hours drift."
                    ),
                    amount_discrepancy=round(amt_diff, 2),
                    date_diff_hours=round(date_diff, 1),
                    fee_detected=round(gw.fee + gw.tax, 2),
                    metadata={"pass": 5, "strategy": "ROUNDING_TOLERANCE"},
                )
                matches.append(pair)
                matched_gw_ids.add(gw.id)
                matched_bnk_ids.add(matched_bnk.id)
            else:
                remaining_gw.append(gw)

        unmatched_gateway = remaining_gw
        unmatched_bank = [b for b in unmatched_bank if b.id not in matched_bnk_ids]

        # =========================================================================
        # PASS 6: AMBIGUOUS & CONFLICT DETECTION (MUST ROUTE TO HUMAN REVIEW)
        # =========================================================================
        # Detect multiple gateway transactions with same reference/amount contending for 1 bank credit
        remaining_gw = []
        for gw in unmatched_gateway:
            competing_bnk = [
                b for b in unmatched_bank
                if MatchingRules.is_exact_ref_match(gw, b) or (
                    MatchingRules.is_amount_exact_match(gw.net_amount, b.net_amount, 0.05)
                    and MatchingRules.is_within_date_window(gw.timestamp, b.timestamp, 2)
                )
            ]
            if len(competing_bnk) >= 1:
                # Find all other gateway txs matching this bank tx
                bnk = competing_bnk[0]
                other_gw = [
                    g for g in unmatched_gateway
                    if MatchingRules.is_exact_ref_match(g, bnk) or (
                        MatchingRules.is_amount_exact_match(g.net_amount, bnk.net_amount, 0.05)
                        and MatchingRules.is_within_date_window(g.timestamp, bnk.timestamp, 2)
                    )
                ]
                if len(other_gw) >= 2:
                    gw_ids = [g.id for g in other_gw]
                    pair = MatchPair(
                        match_id=f"review_ambig_{bnk.id}",
                        gateway_tx_ids=gw_ids,
                        bank_tx_ids=[bnk.id],
                        category=MatchCategory.NEEDS_HUMAN_REVIEW,
                        confidence=0.50,
                        reason_code=MatchReasonCode.AMBIGUOUS_DUPLICATE_CANDIDATES,
                        explanation=(
                            f"Ambiguous candidates detected. Bank credit of ₹{bnk.net_amount:,.2f} "
                            f"matches {len(other_gw)} conflicting Gateway payments ({', '.join(gw_ids)}). "
                            f"Engine refuses auto-match to prevent false linkage."
                        ),
                        amount_discrepancy=0.0,
                        date_diff_hours=0.0,
                        fee_detected=0.0,
                        metadata={"pass": 6, "contending_gw_ids": gw_ids},
                    )
                    human_reviews.append(pair)
                    matched_bnk_ids.add(bnk.id)
                    for g in other_gw:
                        matched_gw_ids.add(g.id)

        unmatched_gateway = [g for g in unmatched_gateway if g.id not in matched_gw_ids]
        unmatched_bank = [b for b in unmatched_bank if b.id not in matched_bnk_ids]

        # =========================================================================
        # PASS 7: RESIDUAL UNMATCHED (Honest Classification)
        # =========================================================================
        for bnk in unmatched_bank:
            bnk.metadata["unmatched_reason"] = MatchReasonCode.ORPHANED_BANK_CREDIT.value
        for gw in unmatched_gateway:
            gw.metadata["unmatched_reason"] = MatchReasonCode.UNSETTLED_GATEWAY_PAYMENT.value

        end_time = time.perf_counter()
        execution_time_ms = round((end_time - start_time) * 1000.0, 2)

        # Calculate Summary Metrics
        total_gw_vol = sum(g.net_amount for g in gateway_txs)
        total_bnk_vol = sum(b.net_amount for b in bank_txs)
        reconciled_vol = sum(
            sum(g.net_amount for g in gateway_txs if g.id in m.gateway_tx_ids)
            for m in matches
        )
        unmatched_gw_vol = sum(g.net_amount for g in unmatched_gateway)
        unmatched_bnk_vol = sum(b.net_amount for b in unmatched_bank)
        total_fee_vol = sum(m.fee_detected for m in matches)

        total_tx = len(gateway_txs)
        auto_rate = round((len(matched_gw_ids) / total_tx) * 100.0, 2) if total_tx > 0 else 0.0

        summary = ReconciliationSummary(
            total_gateway_tx=len(gateway_txs),
            total_bank_tx=len(bank_txs),
            auto_matched_count=len(matches),
            human_review_count=len(human_reviews),
            unmatched_gateway_count=len(unmatched_gateway),
            unmatched_bank_count=len(unmatched_bank),
            total_gateway_volume=round(total_gw_vol, 2),
            total_bank_volume=round(total_bnk_vol, 2),
            reconciled_volume=round(reconciled_vol, 2),
            unmatched_gateway_volume=round(unmatched_gw_vol, 2),
            unmatched_bank_volume=round(unmatched_bnk_vol, 2),
            total_fee_volume=round(total_fee_vol, 2),
            auto_match_rate=auto_rate,
            execution_time_ms=execution_time_ms,
        )

        return ReconciliationReport(
            session_id=self.session_id,
            timestamp=datetime.now(),
            summary=summary,
            matches=matches,
            human_reviews=human_reviews,
            unmatched_gateway=unmatched_gateway,
            unmatched_bank=unmatched_bank,
            audit_chain_head="",  # Populated after audit recording
            audit_block_count=0,
        )
