"""
Razorpay settlement and payment data adapter.
Supports Razorpay Settlement CSV exports and simulated JSON API responses.
"""

from datetime import datetime
import io
import json
from typing import Any, Dict, List, Optional
import pandas as pd
from fincontroller.core.exceptions import IngestionError
from fincontroller.core.models import NormalizedTransaction, TransactionSource, TransactionStatus
from fincontroller.ingestion.base import BaseIngestionAdapter


from fincontroller.ingestion.mapper import ColumnMapper, ColumnMappingConfig


class RazorpayAdapter(BaseIngestionAdapter):
    """Parses Razorpay settlement reports and payment objects with schema auto-detection."""

    def __init__(self, mapping: Optional[ColumnMappingConfig | Dict[str, str]] = None):
        self.mapping = mapping

    def parse(
        self,
        data: bytes | str | pd.DataFrame | List[Dict[str, Any]],
        mapping_override: Optional[ColumnMappingConfig | Dict[str, str]] = None,
    ) -> List[NormalizedTransaction]:
        try:
            if isinstance(data, list):
                return self._parse_json_items(data, mapping_override)
            elif isinstance(data, str) and data.strip().startswith(("[", "{")):
                loaded = json.loads(data)
                items = loaded.get("items", loaded) if isinstance(loaded, dict) else loaded
                return self._parse_json_items(items, mapping_override)
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
            raise IngestionError(f"Failed to parse Razorpay data: {str(e)}") from e

    def _parse_dataframe(
        self,
        df: pd.DataFrame,
        mapping_override: Optional[ColumnMappingConfig | Dict[str, str]] = None,
    ) -> List[NormalizedTransaction]:
        normalized: List[NormalizedTransaction] = []
        active_map = mapping_override or self.mapping

        # If custom mapping or non-standard columns, use SchemaAgnosticAdapter
        standard_cols = {"entity_id", "payment_id", "amount", "settled_at", "utr"}
        clean_cols = {c.strip().lower().replace(" ", "_").replace("/", "_") for c in df.columns}
        if active_map or not any(sc in clean_cols for sc in standard_cols):
            from fincontroller.ingestion.generic_adapter import SchemaAgnosticAdapter
            adapter = SchemaAgnosticAdapter(source=TransactionSource.RAZORPAY, mapping=active_map, source_prefix="rzp")
            return adapter.parse(df)
        normalized: List[NormalizedTransaction] = []
        df.columns = [c.strip().lower().replace(" ", "_").replace("/", "_") for c in df.columns]

        for idx, row in df.iterrows():
            # ID resolution
            raw_id = (
                str(row.get("entity_id") or row.get("payment_id") or row.get("id") or f"rzp_row_{idx}")
            ).strip()

            # Amount parsing (Razorpay reports can be in paise or rupees)
            amount = float(row.get("amount", 0.0))
            fee = float(row.get("fee", 0.0))
            tax = float(row.get("tax", 0.0))
            
            # If amounts look like paise (integer > 10000 with no decimal), check flag or normalize
            if "is_paise" in row and bool(row["is_paise"]):
                amount /= 100.0
                fee /= 100.0
                tax /= 100.0

            net_amount = float(row.get("net_amount", amount - (fee + tax)))

            # Timestamp parsing
            timestamp_raw = row.get("settled_at") or row.get("created_at") or row.get("date") or datetime.now()
            if isinstance(timestamp_raw, (int, float)):
                ts = datetime.fromtimestamp(timestamp_raw)
            else:
                ts = pd.to_datetime(timestamp_raw).to_pydatetime()

            # Reference / UTR / ARN
            ref_raw = (
                str(row.get("utr") or row.get("arn") or row.get("reference_id") or raw_id)
            ).strip()
            reference_id = self.extract_reference_id(ref_raw) or raw_id

            # Status
            status_raw = str(row.get("status", "settled")).upper()
            status = TransactionStatus.SETTLED
            if "REFUND" in status_raw:
                status = TransactionStatus.REFUNDED
            elif "CHARGEBACK" in status_raw:
                status = TransactionStatus.CHARGEBACK
            elif "FAIL" in status_raw:
                status = TransactionStatus.FAILED
            elif "PEND" in status_raw:
                status = TransactionStatus.PENDING

            counterparty = str(row.get("merchant_name") or row.get("customer_email") or "Merchant").strip()
            description = str(row.get("description") or row.get("notes") or f"Razorpay Settlement {raw_id}")

            metadata = {k: v for k, v in row.to_dict().items() if not pd.isna(v)}

            tx = NormalizedTransaction(
                id=f"rzp_{raw_id}",
                source=TransactionSource.RAZORPAY,
                raw_id=raw_id,
                amount=round(amount, 2),
                fee=round(fee, 2),
                tax=round(tax, 2),
                net_amount=round(net_amount, 2),
                currency=str(row.get("currency", "INR")).upper(),
                timestamp=ts,
                reference_id=reference_id,
                counterparty=counterparty,
                description=description,
                status=status,
                metadata=metadata,
            )
            normalized.append(tx)

        return normalized

    def _parse_json_items(self, items: List[Dict[str, Any]]) -> List[NormalizedTransaction]:
        df = pd.DataFrame(items)
        return self._parse_dataframe(df)
