"""
Universal Schema-Agnostic Financial Transaction Ingestion Adapter.
Parses arbitrary user-supplied CSV/JSON files into canonical NormalizedTransaction models.
"""

from datetime import datetime
import io
import json
import os
from typing import Any, Dict, List, Optional
import pandas as pd

from fincontroller.core.exceptions import IngestionError
from fincontroller.core.models import NormalizedTransaction, TransactionSource, TransactionStatus
from fincontroller.ingestion.base import BaseIngestionAdapter
from fincontroller.ingestion.mapper import ColumnMapper, ColumnMappingConfig


class SchemaAgnosticAdapter(BaseIngestionAdapter):
    """
    Generic adapter that ingests and normalizes any user-supplied transaction dataset
    with dynamic column auto-detection and optional explicit schema mapping.
    """

    def __init__(
        self,
        source: TransactionSource = TransactionSource.INTERNAL_ERP,
        mapping: Optional[ColumnMappingConfig | Dict[str, str]] = None,
        source_prefix: str = "tx",
    ):
        self.source = source
        self.mapping = mapping
        self.source_prefix = source_prefix

    def parse(
        self,
        data: bytes | str | pd.DataFrame | List[Dict[str, Any]],
        mapping_override: Optional[ColumnMappingConfig | Dict[str, str]] = None,
    ) -> List[NormalizedTransaction]:
        """
        Parse raw input (bytes, filepath, string, DataFrame, or JSON) into NormalizedTransaction list.
        """
        try:
            df = self._load_to_dataframe(data)
            if df.empty:
                return []

            active_mapping = mapping_override or self.mapping
            resolved_map = ColumnMapper.auto_detect_mapping(list(df.columns), active_mapping)

            return self._normalize_dataframe(df, resolved_map)
        except IngestionError:
            raise
        except Exception as e:
            raise IngestionError(f"Dynamic ingestion failed: {str(e)}") from e

    def _load_to_dataframe(self, data: bytes | str | pd.DataFrame | List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert various input formats into a pandas DataFrame."""
        if isinstance(data, pd.DataFrame):
            return data.copy()

        if isinstance(data, list):
            return pd.DataFrame(data)

        if isinstance(data, bytes):
            # Try multiple encodings for robustness (utf-8-sig, utf-8, latin1, cp1252)
            for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
                try:
                    return pd.read_csv(io.BytesIO(data), encoding=enc)
                except Exception:
                    continue
            raise IngestionError("Could not decode CSV bytes with standard encodings (UTF-8, Latin-1, CP1252).")

        if isinstance(data, str):
            # Check if it's a file path
            if os.path.exists(data):
                for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
                    try:
                        return pd.read_csv(data, encoding=enc)
                    except Exception:
                        continue
                raise IngestionError(f"Could not decode file '{data}'.")

            # Check if it's a JSON string
            trimmed = data.strip()
            if trimmed.startswith(("[", "{")):
                try:
                    loaded = json.loads(trimmed)
                    items = loaded.get("items", loaded.get("data", loaded)) if isinstance(loaded, dict) else loaded
                    return pd.DataFrame(items)
                except json.JSONDecodeError:
                    pass

            # Otherwise treat as raw CSV text
            return pd.read_csv(io.StringIO(data))

        raise IngestionError(f"Unsupported data type for ingestion: {type(data)}")

    def _normalize_dataframe(self, df: pd.DataFrame, mapping: ColumnMappingConfig) -> List[NormalizedTransaction]:
        """Convert DataFrame rows to canonical NormalizedTransaction objects."""
        # Validation: Verify that an amount or credit column exists
        has_amount = bool(mapping.amount and mapping.amount in df.columns)
        has_debit = bool(mapping.debit and mapping.debit in df.columns)
        has_net = bool(mapping.net_amount and mapping.net_amount in df.columns)

        if not (has_amount or has_debit or has_net):
            available_cols = ", ".join(f"'{c}'" for c in df.columns)
            raise IngestionError(
                f"Missing required amount column in source data. Available columns: [{available_cols}]. "
                f"Please provide an explicit mapping for 'amount' or 'credit'."
            )

        normalized: List[NormalizedTransaction] = []

        for idx, row in df.iterrows():
            # 1. Amount & Fee Extraction
            gross_val = ColumnMapper.parse_numeric(row[mapping.amount]) if mapping.amount and mapping.amount in row else 0.0
            debit_val = ColumnMapper.parse_numeric(row[mapping.debit]) if mapping.debit and mapping.debit in row else 0.0
            fee_val = ColumnMapper.parse_numeric(row[mapping.fee]) if mapping.fee and mapping.fee in row else 0.0
            tax_val = ColumnMapper.parse_numeric(row[mapping.tax]) if mapping.tax and mapping.tax in row else 0.0

            # Determine net amount
            if mapping.net_amount and mapping.net_amount in row:
                net_val = ColumnMapper.parse_numeric(row[mapping.net_amount])
            elif gross_val > 0:
                net_val = gross_val - (fee_val + tax_val)
            elif debit_val > 0:
                net_val = -debit_val
            else:
                net_val = gross_val

            effective_amount = gross_val if gross_val != 0.0 else (net_val if net_val != 0.0 else -debit_val)

            # 2. Reference & ID Extraction
            ref_col_val = str(row[mapping.reference_id]).strip() if mapping.reference_id and mapping.reference_id in row and not pd.isna(row[mapping.reference_id]) else ""
            desc_val = str(row[mapping.description]).strip() if mapping.description and mapping.description in row and not pd.isna(row[mapping.description]) else ""
            raw_id_val = str(row[mapping.raw_id]).strip() if mapping.raw_id and mapping.raw_id in row and not pd.isna(row[mapping.raw_id]) else ""

            # Extract clean reference ID using regex patterns
            extracted_ref = (
                self.extract_reference_id(ref_col_val)
                or self.extract_reference_id(desc_val)
                or ref_col_val
                or raw_id_val
                or f"ref_{idx}"
            )

            canonical_raw_id = raw_id_val or extracted_ref or f"{self.source_prefix}_{idx}"

            # 3. Timestamp Parsing
            date_col_val = row[mapping.timestamp] if mapping.timestamp and mapping.timestamp in row else None
            ts = ColumnMapper.parse_datetime(date_col_val)

            # 4. Status Coercion
            status_col_val = str(row[mapping.status]).upper() if mapping.status and mapping.status in row and not pd.isna(row[mapping.status]) else "SETTLED"
            status = self._coerce_status(status_col_val, net_val)

            # 5. Currency & Counterparty
            currency = str(row[mapping.currency]).strip().upper() if mapping.currency and mapping.currency in row and not pd.isna(row[mapping.currency]) else "INR"
            counterparty = str(row[mapping.counterparty]).strip() if mapping.counterparty and mapping.counterparty in row and not pd.isna(row[mapping.counterparty]) else None

            # Clean metadata dictionary
            metadata = {
                str(k): v for k, v in row.to_dict().items() 
                if not pd.isna(v)
            }
            metadata["_detected_mapping"] = mapping.model_dump(exclude_none=True)

            tx = NormalizedTransaction(
                id=f"{self.source_prefix}_{canonical_raw_id}_{idx}",
                source=self.source,
                raw_id=canonical_raw_id,
                amount=round(abs(effective_amount), 2),
                fee=round(fee_val, 2),
                tax=round(tax_val, 2),
                net_amount=round(abs(net_val), 2),
                currency=currency,
                timestamp=ts,
                reference_id=extracted_ref,
                counterparty=counterparty,
                description=desc_val or None,
                status=status,
                metadata=metadata,
            )
            normalized.append(tx)

        return normalized

    @staticmethod
    def _coerce_status(status_str: str, net_amount: float) -> TransactionStatus:
        """Coerce arbitrary string status into canonical TransactionStatus enum."""
        s = status_str.upper()
        if any(w in s for w in ["REFUND", "REVERSAL", "VOID", "RETURN"]):
            return TransactionStatus.REFUNDED
        if any(w in s for w in ["CHARGEBACK", "DISPUTE"]):
            return TransactionStatus.CHARGEBACK
        if any(w in s for w in ["FAIL", "DECLINED", "ERROR", "REJECT"]):
            return TransactionStatus.FAILED
        if any(w in s for w in ["PEND", "HOLD", "ESCROW", "AUTH", "PROCESSING", "IN_TRANSIT"]):
            return TransactionStatus.PENDING
        if any(w in s for w in ["CAPTURED", "AUTHORIZED"]):
            return TransactionStatus.CAPTURED
        return TransactionStatus.SETTLED
