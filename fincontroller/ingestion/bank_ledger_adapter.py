"""
Bank Ledger and Bank Statement CSV/Data Adapter.
Supports multi-bank statement formats with credit/debit columns and narration UTR extraction.
"""

from datetime import datetime
import io
from typing import Any, Dict, List, Optional
import pandas as pd
from fincontroller.core.exceptions import IngestionError
from fincontroller.core.models import NormalizedTransaction, TransactionSource, TransactionStatus
from fincontroller.ingestion.base import BaseIngestionAdapter


from fincontroller.ingestion.mapper import ColumnMapper, ColumnMappingConfig


class BankLedgerAdapter(BaseIngestionAdapter):
    """Parses Bank statement exports and ledger transaction feeds with schema auto-detection."""

    def __init__(self, mapping: Optional[ColumnMappingConfig | Dict[str, str]] = None):
        self.mapping = mapping

    def parse(
        self,
        data: bytes | str | pd.DataFrame | List[Dict[str, Any]],
        mapping_override: Optional[ColumnMappingConfig | Dict[str, str]] = None,
    ) -> List[NormalizedTransaction]:
        try:
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, pd.DataFrame):
                df = data
            elif isinstance(data, bytes):
                df = pd.read_csv(io.BytesIO(data))
            else:
                df = pd.read_csv(io.StringIO(str(data)))

            return self._parse_dataframe(df, mapping_override)
        except IngestionError:
            raise
        except Exception as e:
            raise IngestionError(f"Failed to parse Bank Ledger data: {str(e)}") from e

    def _parse_dataframe(
        self,
        df: pd.DataFrame,
        mapping_override: Optional[ColumnMappingConfig | Dict[str, str]] = None,
    ) -> List[NormalizedTransaction]:
        active_map = mapping_override or self.mapping

        # If custom mapping or non-standard columns, use SchemaAgnosticAdapter
        standard_cols = {"narration", "ref_no", "credit", "debit", "transaction_date", "value_date"}
        clean_cols = {c.strip().lower().replace(" ", "_").replace("/", "_").replace(".", "") for c in df.columns}
        if active_map or not any(sc in clean_cols for sc in standard_cols):
            from fincontroller.ingestion.generic_adapter import SchemaAgnosticAdapter
            adapter = SchemaAgnosticAdapter(source=TransactionSource.BANK_LEDGER, mapping=active_map, source_prefix="bnk")
            return adapter.parse(df)

        normalized: List[NormalizedTransaction] = []
        df.columns = [c.strip().lower().replace(" ", "_").replace("/", "_").replace(".", "") for c in df.columns]

        for idx, row in df.iterrows():
            # Find Credit / Deposit or Net Amount
            credit = row.get("credit") or row.get("deposit") or row.get("credit_amount") or 0.0
            debit = row.get("debit") or row.get("withdrawal") or row.get("debit_amount") or 0.0
            
            try:
                credit_val = float(str(credit).replace(",", "")) if credit and not pd.isna(credit) else 0.0
            except ValueError:
                credit_val = 0.0

            try:
                debit_val = float(str(debit).replace(",", "")) if debit and not pd.isna(debit) else 0.0
            except ValueError:
                debit_val = 0.0

            if credit_val > 0:
                amount = credit_val
                status = TransactionStatus.SETTLED
            elif debit_val > 0:
                amount = -debit_val
                status = TransactionStatus.REFUNDED
            else:
                raw_amt = row.get("amount", 0.0)
                try:
                    amount = float(str(raw_amt).replace(",", "")) if not pd.isna(raw_amt) else 0.0
                except ValueError:
                    amount = 0.0
                status = TransactionStatus.SETTLED

            # Narration / Description
            narration = str(
                row.get("narration")
                or row.get("description")
                or row.get("transaction_remarks")
                or row.get("particulars")
                or ""
            ).strip()

            # Reference / UTR
            ref_raw = str(
                row.get("ref_no")
                or row.get("cheque_no")
                or row.get("utr")
                or row.get("reference_id")
                or ""
            ).strip()

            reference_id = self.extract_reference_id(ref_raw) or self.extract_reference_id(narration)
            raw_id = ref_raw if ref_raw and ref_raw != "nan" else (
                reference_id if reference_id else f"bank_tx_{idx}"
            )

            # Date parsing
            date_raw = (
                row.get("value_date")
                or row.get("transaction_date")
                or row.get("date")
                or datetime.now()
            )
            ts = pd.to_datetime(date_raw).to_pydatetime()

            counterparty = str(row.get("counterparty") or row.get("beneficiary") or "Bank Account").strip()
            currency = str(row.get("currency", "INR")).upper()

            metadata = {k: v for k, v in row.to_dict().items() if not pd.isna(v)}

            tx = NormalizedTransaction(
                id=f"bnk_{raw_id}_{idx}",
                source=TransactionSource.BANK_LEDGER,
                raw_id=raw_id,
                amount=round(amount, 2),
                fee=0.0,
                tax=0.0,
                net_amount=round(amount, 2),
                currency=currency,
                timestamp=ts,
                reference_id=reference_id,
                counterparty=counterparty,
                description=narration,
                status=status,
                metadata=metadata,
            )
            normalized.append(tx)

        return normalized
