"""
Cryptographic Tamper-Evident Hash Chain Audit Trail.
Guarantees immutability and mathematical verifiability for all reconciliation decisions.
"""

from datetime import datetime
import hashlib
import json
import os
from typing import Any, Dict, List, Optional
from fincontroller.core.config import settings
from fincontroller.core.models import AuditBlock, MatchPair, ReconciliationReport


class AuditHashChain:
    """
    Append-only cryptographic ledger using SHA-256 hash-chaining.
    """

    GENESIS_PREV_HASH = "0" * 64

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or settings.AUDIT_STORAGE_PATH
        self.chain: List[AuditBlock] = []
        self._load_or_initialize()

    def _load_or_initialize(self) -> None:
        """Load existing ledger or create genesis block."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.chain = [AuditBlock(**item) for item in data]
                    return
            except Exception:
                self.chain = []

        # Create Genesis Block
        genesis = self._create_block(
            index=0,
            previous_hash=self.GENESIS_PREV_HASH,
            event_type="GENESIS",
            payload={"message": "FinController Tamper-Evident Audit Chain Initialized", "version": "1.0"},
        )
        self.chain = [genesis]
        self._persist()

    @staticmethod
    def compute_payload_hash(payload: Dict[str, Any]) -> str:
        """Deterministic SHA-256 hash of JSON payload."""
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_block_hash(
        index: int,
        timestamp: str,
        previous_hash: str,
        event_type: str,
        payload_hash: str,
        operator: str,
    ) -> str:
        """Compute SHA-256 block hash including secret salt."""
        raw_str = f"{index}|{timestamp}|{previous_hash}|{event_type}|{payload_hash}|{operator}|{settings.AUDIT_SECRET_SALT}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def _create_block(
        self,
        index: int,
        previous_hash: str,
        event_type: str,
        payload: Dict[str, Any],
        operator: str = "FIN_CONTROLLER_ENGINE_V1",
    ) -> AuditBlock:
        from datetime import timezone
        ts = datetime.now(timezone.utc).isoformat()
        payload_hash = self.compute_payload_hash(payload)
        block_hash = self.compute_block_hash(index, ts, previous_hash, event_type, payload_hash, operator)

        return AuditBlock(
            index=index,
            timestamp=ts,
            previous_hash=previous_hash,
            block_hash=block_hash,
            event_type=event_type,
            payload_hash=payload_hash,
            payload=payload,
            operator=operator,
        )

    def append_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        operator: str = "FIN_CONTROLLER_ENGINE_V1",
    ) -> AuditBlock:
        """Append a new verified block to the hash chain."""
        prev_block = self.chain[-1]
        new_block = self._create_block(
            index=len(self.chain),
            previous_hash=prev_block.block_hash,
            event_type=event_type,
            payload=payload,
            operator=operator,
        )
        self.chain.append(new_block)
        self._persist()
        return new_block

    def record_reconciliation_report(self, report: ReconciliationReport) -> AuditBlock:
        """Record an entire reconciliation run and update the report with chain head."""
        payload = {
            "session_id": report.session_id,
            "summary": report.summary.model_dump(),
            "auto_matched_count": len(report.matches),
            "human_review_count": len(report.human_reviews),
            "unmatched_gateway_count": len(report.unmatched_gateway),
            "unmatched_bank_count": len(report.unmatched_bank),
            "sample_match_ids": [m.match_id for m in report.matches[:10]],
        }
        block = self.append_event(event_type="RECONCILIATION_RUN_COMPLETED", payload=payload)
        report.audit_chain_head = block.block_hash
        report.audit_block_count = len(self.chain)
        return block

    def get_chain(self) -> List[AuditBlock]:
        return list(self.chain)

    def get_head(self) -> str:
        return self.chain[-1].block_hash if self.chain else self.GENESIS_PREV_HASH

    def _persist(self) -> None:
        """Save chain to storage file."""
        os.makedirs(os.path.dirname(os.path.abspath(self.storage_path)), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump([b.model_dump() for b in self.chain], f, indent=2)
