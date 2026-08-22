"""
Realistic Messy Seed Dataset Generator with Ground Truth Annotations.
Generates comprehensive edge cases for benchmark testing.
"""

from datetime import datetime, timedelta
import json
import random
from typing import Any, Dict, List, Tuple
import pandas as pd


def generate_benchmark_dataset(
    seed: int = 42,
    num_exact: int = 25,
    num_fee_adjusted: int = 20,
    num_split_batches: int = 6,  # Each split batch has 2-4 transactions
    num_delayed_date: int = 15,
    num_fuzzy_ref: int = 10,
    num_paise_rounding: int = 10,
    num_ambiguous_duplicate: int = 6,
    num_orphaned_bank: int = 8,
    num_unsettled_gateway: int = 8,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[Dict[str, Any]]]:
    """
    Generate synthetic Razorpay and Bank statements with intentional realistic anomalies
    and ground truth labels.
    """
    random.seed(seed)
    base_time = datetime(2026, 8, 1, 9, 0, 0)

    razorpay_records: List[Dict[str, Any]] = []
    bank_records: List[Dict[str, Any]] = []
    ground_truth: List[Dict[str, Any]] = []

    # 1. EXACT MATCHES (1:1)
    for i in range(num_exact):
        ref_id = f"pay_EXACT_{i:04d}_{random.randint(1000, 9999)}"
        amount = round(random.uniform(500.0, 25000.0), 2)
        tx_time = base_time + timedelta(hours=random.randint(1, 100))
        
        rzp_row = {
            "entity_id": ref_id,
            "amount": amount,
            "fee": 0.0,
            "tax": 0.0,
            "net_amount": amount,
            "currency": "INR",
            "settled_at": tx_time.strftime("%Y-%m-%d %H:%M:%S"),
            "utr": f"UTR_EX_{i:04d}",
            "merchant_name": f"Merchant_{random.randint(10, 99)}",
            "description": f"Standard checkout settlement {ref_id}",
            "status": "settled",
        }
        bank_row = {
            "transaction_date": tx_time.strftime("%Y-%m-%d"),
            "value_date": (tx_time + timedelta(hours=4)).strftime("%Y-%m-%d"),
            "narration": f"CMS/RAZORPAY/UTR_EX_{i:04d}/{ref_id}/SETTL",
            "ref_no": f"UTR_EX_{i:04d}",
            "credit": amount,
            "debit": 0.0,
            "currency": "INR",
        }
        razorpay_records.append(rzp_row)
        bank_records.append(bank_row)
        ground_truth.append({
            "expected_category": "AUTO_MATCHED",
            "expected_reason": "EXACT_MATCH_REF_AND_AMOUNT",
            "razorpay_refs": [ref_id],
            "bank_refs": [f"UTR_EX_{i:04d}"],
            "notes": "Clean exact 1:1 match",
        })

    # 2. FEE & TAX ADJUSTED MATCHES
    for i in range(num_fee_adjusted):
        ref_id = f"pay_FEE_{i:04d}_{random.randint(1000, 9999)}"
        gross_amount = round(random.uniform(1000.0, 50000.0), 2)
        mdr_fee = round(gross_amount * 0.02, 2)
        gst = round(mdr_fee * 0.18, 2)
        net_settled = round(gross_amount - (mdr_fee + gst), 2)
        tx_time = base_time + timedelta(hours=random.randint(20, 150))

        utr = f"UTR_FEE_{i:04d}"
        rzp_row = {
            "entity_id": ref_id,
            "amount": gross_amount,
            "fee": mdr_fee,
            "tax": gst,
            "net_amount": net_settled,
            "currency": "INR",
            "settled_at": tx_time.strftime("%Y-%m-%d %H:%M:%S"),
            "utr": utr,
            "merchant_name": "SaaS Platform Pvt Ltd",
            "description": f"Subscription plan payment {ref_id}",
            "status": "settled",
        }
        bank_row = {
            "transaction_date": tx_time.strftime("%Y-%m-%d"),
            "value_date": (tx_time + timedelta(hours=6)).strftime("%Y-%m-%d"),
            "narration": f"NEFT-RZP-PAYOUT-{utr}-{ref_id}",
            "ref_no": utr,
            "credit": net_settled,
            "debit": 0.0,
            "currency": "INR",
        }
        razorpay_records.append(rzp_row)
        bank_records.append(bank_row)
        ground_truth.append({
            "expected_category": "AUTO_MATCHED",
            "expected_reason": "FEE_ADJUSTED_MATCH",
            "razorpay_refs": [ref_id],
            "bank_refs": [utr],
            "notes": f"Reconciled via net amount after 2% MDR + 18% GST ({net_settled})",
        })

    # 3. SPLIT BATCH SETTLEMENTS (1 Bank Credit = Multiple Gateway Payouts)
    for b in range(num_split_batches):
        batch_utr = f"UTR_BATCH_{b:04d}"
        batch_time = base_time + timedelta(days=b + 2)
        num_items = random.randint(2, 4)
        sub_rzp_refs = []
        batch_net_sum = 0.0

        for s in range(num_items):
            sub_ref = f"pay_SPLIT_B{b}_S{s}_{random.randint(100, 999)}"
            amt = round(random.uniform(2000.0, 8000.0), 2)
            sub_rzp_refs.append(sub_ref)
            batch_net_sum += amt
            rzp_row = {
                "entity_id": sub_ref,
                "amount": amt,
                "fee": 0.0,
                "tax": 0.0,
                "net_amount": amt,
                "currency": "INR",
                "settled_at": (batch_time - timedelta(hours=random.randint(1, 12))).strftime("%Y-%m-%d %H:%M:%S"),
                "utr": batch_utr,
                "merchant_name": f"Batch Store {b}",
                "description": f"Batch item {s} for settlement {batch_utr}",
                "status": "settled",
            }
            razorpay_records.append(rzp_row)

        batch_net_sum = round(batch_net_sum, 2)
        bank_row = {
            "transaction_date": batch_time.strftime("%Y-%m-%d"),
            "value_date": batch_time.strftime("%Y-%m-%d"),
            "narration": f"BULK-RZP-SETTL-{batch_utr}-TOTAL-{batch_net_sum}",
            "ref_no": batch_utr,
            "credit": batch_net_sum,
            "debit": 0.0,
            "currency": "INR",
        }
        bank_records.append(bank_row)
        ground_truth.append({
            "expected_category": "AUTO_MATCHED",
            "expected_reason": "SPLIT_BATCH_MATCH",
            "razorpay_refs": sub_rzp_refs,
            "bank_refs": [batch_utr],
            "notes": f"1:N Split batch payout summing to {batch_net_sum}",
        })

    # 4. DELAYED SETTLEMENT DRIFT (T+2 / T+3 across weekend)
    for i in range(num_delayed_date):
        ref_id = f"pay_DELAY_{i:04d}_{random.randint(1000, 9999)}"
        amount = round(random.uniform(1500.0, 18000.0), 2)
        tx_time = base_time + timedelta(days=i * 2)
        settled_bank_time = tx_time + timedelta(days=2, hours=14)  # T+2.5 days

        utr = f"UTR_DELAY_{i:04d}"
        rzp_row = {
            "entity_id": ref_id,
            "amount": amount,
            "fee": 0.0,
            "tax": 0.0,
            "net_amount": amount,
            "currency": "INR",
            "settled_at": tx_time.strftime("%Y-%m-%d %H:%M:%S"),
            "utr": utr,
            "merchant_name": "Ecommerce Corp",
            "description": f"Friday payment settled Monday {ref_id}",
            "status": "settled",
        }
        bank_row = {
            "transaction_date": settled_bank_time.strftime("%Y-%m-%d"),
            "value_date": settled_bank_time.strftime("%Y-%m-%d"),
            "narration": f"ACH-CR-RZP-{utr}-{ref_id}",
            "ref_no": utr,
            "credit": amount,
            "debit": 0.0,
            "currency": "INR",
        }
        razorpay_records.append(rzp_row)
        bank_records.append(bank_row)
        ground_truth.append({
            "expected_category": "AUTO_MATCHED",
            "expected_reason": "AMOUNT_TOLERANCE_MATCH",
            "razorpay_refs": [ref_id],
            "bank_refs": [utr],
            "notes": "Settled with 2.5 day bank holiday drift",
        })

    # 5. FUZZY REFERENCE STRING TYPOS (e.g., OCR or manual ledger typo)
    for i in range(num_fuzzy_ref):
        clean_ref = f"pay_FUZZY_{i:03d}ABC"
        # Introduce a 1-character typo in bank narration (e.g. '0' vs 'O', '8' vs 'B')
        corrupted_ref = clean_ref.replace("ABC", "AB0")
        amount = round(random.uniform(3000.0, 15000.0), 2)
        tx_time = base_time + timedelta(hours=random.randint(10, 120))

        rzp_row = {
            "entity_id": clean_ref,
            "amount": amount,
            "fee": 0.0,
            "tax": 0.0,
            "net_amount": amount,
            "currency": "INR",
            "settled_at": tx_time.strftime("%Y-%m-%d %H:%M:%S"),
            "utr": clean_ref,
            "merchant_name": "Retail Store Online",
            "description": f"Order {clean_ref}",
            "status": "settled",
        }
        bank_row = {
            "transaction_date": tx_time.strftime("%Y-%m-%d"),
            "value_date": tx_time.strftime("%Y-%m-%d"),
            "narration": f"UPI/RZP/{corrupted_ref}/PAYMENT",
            "ref_no": corrupted_ref,
            "credit": amount,
            "debit": 0.0,
            "currency": "INR",
        }
        razorpay_records.append(rzp_row)
        bank_records.append(bank_row)
        ground_truth.append({
            "expected_category": "AUTO_MATCHED",
            "expected_reason": "FUZZY_REF_EXACT_AMOUNT_MATCH",
            "razorpay_refs": [clean_ref],
            "bank_refs": [corrupted_ref],
            "notes": f"Fuzzy match resolved string typo: {clean_ref} -> {corrupted_ref}",
        })

    # 6. PAISE ROUNDING DIFFERENCES (<= ₹1.00 discrepancy)
    for i in range(num_paise_rounding):
        ref_id = f"pay_ROUND_{i:04d}"
        rzp_amt = round(random.uniform(500.0, 10000.0) + 0.45, 2)
        bank_amt = round(rzp_amt - 0.45, 2)  # 45 paise rounding difference
        tx_time = base_time + timedelta(hours=random.randint(5, 80))

        utr = f"UTR_RND_{i:04d}"
        rzp_row = {
            "entity_id": ref_id,
            "amount": rzp_amt,
            "fee": 0.0,
            "tax": 0.0,
            "net_amount": rzp_amt,
            "currency": "INR",
            "settled_at": tx_time.strftime("%Y-%m-%d %H:%M:%S"),
            "utr": utr,
            "merchant_name": "Direct D2C",
            "description": f"Rounding case {ref_id}",
            "status": "settled",
        }
        bank_row = {
            "transaction_date": tx_time.strftime("%Y-%m-%d"),
            "value_date": tx_time.strftime("%Y-%m-%d"),
            "narration": f"IMPS/RAZORPAY/{utr}/{ref_id}",
            "ref_no": utr,
            "credit": bank_amt,
            "debit": 0.0,
            "currency": "INR",
        }
        razorpay_records.append(rzp_row)
        bank_records.append(bank_row)
        ground_truth.append({
            "expected_category": "AUTO_MATCHED",
            "expected_reason": "AMOUNT_TOLERANCE_MATCH",
            "razorpay_refs": [ref_id],
            "bank_refs": [utr],
            "notes": f"45 paise rounding mismatch accepted within tolerance",
        })

    # 7. AMBIGUOUS DUPLICATES (MUST BE FLAGGED FOR HUMAN REVIEW)
    for i in range(num_ambiguous_duplicate):
        dup_amt = 999.00
        ref_dup_rzp = f"pay_AMBIG_DUP_{i:02d}_A"
        ref_dup_rzp2 = f"pay_AMBIG_DUP_{i:02d}_B"
        utr_dup = f"UTR_AMBIG_{i:02d}"
        tx_time = base_time + timedelta(days=i)

        rzp_row_1 = {
            "entity_id": ref_dup_rzp,
            "amount": dup_amt,
            "fee": 0.0,
            "tax": 0.0,
            "net_amount": dup_amt,
            "currency": "INR",
            "settled_at": tx_time.strftime("%Y-%m-%d %H:%M:%S"),
            "utr": utr_dup,
            "merchant_name": "Ambiguous Merchant",
            "description": "Duplicate payment 1",
            "status": "settled",
        }
        rzp_row_2 = {
            "entity_id": ref_dup_rzp2,
            "amount": dup_amt,
            "fee": 0.0,
            "tax": 0.0,
            "net_amount": dup_amt,
            "currency": "INR",
            "settled_at": (tx_time + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
            "utr": utr_dup,
            "merchant_name": "Ambiguous Merchant",
            "description": "Duplicate payment 2",
            "status": "settled",
        }
        bank_row = {
            "transaction_date": tx_time.strftime("%Y-%m-%d"),
            "value_date": tx_time.strftime("%Y-%m-%d"),
            "narration": f"NEFT-RZP-{utr_dup}-CONFLICT",
            "ref_no": utr_dup,
            "credit": dup_amt,
            "debit": 0.0,
            "currency": "INR",
        }
        razorpay_records.extend([rzp_row_1, rzp_row_2])
        bank_records.append(bank_row)
        ground_truth.append({
            "expected_category": "NEEDS_HUMAN_REVIEW",
            "expected_reason": "AMBIGUOUS_DUPLICATE_CANDIDATES",
            "razorpay_refs": [ref_dup_rzp, ref_dup_rzp2],
            "bank_refs": [utr_dup],
            "notes": "Two identical Razorpay transactions matching single bank credit. Refuses auto-match.",
        })

    # 8. ORPHANED BANK CREDITS (No corresponding gateway transaction)
    for i in range(num_orphaned_bank):
        orphan_utr = f"DIRECT_BANK_NEFT_{i:04d}"
        amt = round(random.uniform(5000.0, 75000.0), 2)
        tx_time = base_time + timedelta(days=i + 5)
        bank_row = {
            "transaction_date": tx_time.strftime("%Y-%m-%d"),
            "value_date": tx_time.strftime("%Y-%m-%d"),
            "narration": f"DIRECT NEFT CLIENT TRANSFER {orphan_utr} FROM ACME CORP",
            "ref_no": orphan_utr,
            "credit": amt,
            "debit": 0.0,
            "currency": "INR",
        }
        bank_records.append(bank_row)
        ground_truth.append({
            "expected_category": "UNMATCHED",
            "expected_reason": "ORPHANED_BANK_CREDIT",
            "razorpay_refs": [],
            "bank_refs": [orphan_utr],
            "notes": "Direct bank credit outside Razorpay ecosystem",
        })

    # 9. UNSETTLED / ESCROW GATEWAY PAYMENTS (Captured in Razorpay, never deposited to bank)
    for i in range(num_unsettled_gateway):
        ref_id = f"pay_UNSETTLED_ESCROW_{i:04d}"
        amt = round(random.uniform(2000.0, 30000.0), 2)
        tx_time = base_time + timedelta(days=i + 3)
        rzp_row = {
            "entity_id": ref_id,
            "amount": amt,
            "fee": 0.0,
            "tax": 0.0,
            "net_amount": amt,
            "currency": "INR",
            "settled_at": tx_time.strftime("%Y-%m-%d %H:%M:%S"),
            "utr": "",
            "merchant_name": "High Risk Merchant",
            "description": "Payment held in fraud/risk escrow",
            "status": "pending",
        }
        razorpay_records.append(rzp_row)
        ground_truth.append({
            "expected_category": "UNMATCHED",
            "expected_reason": "UNSETTLED_GATEWAY_PAYMENT",
            "razorpay_refs": [ref_id],
            "bank_refs": [],
            "notes": "Unsettled gateway payment in risk escrow",
        })

    # Shuffle to make realistic
    random.shuffle(razorpay_records)
    random.shuffle(bank_records)

    df_rzp = pd.DataFrame(razorpay_records)
    df_bank = pd.DataFrame(bank_records)

    return df_rzp, df_bank, ground_truth
