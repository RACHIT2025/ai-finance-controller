"""
Independent Audit Chain Integrity Verifier.
Validates SHA-256 hash linkages and proves zero tampering.
"""

from typing import Any, Dict, List, Optional, Tuple
from fincontroller.audit.hash_chain import AuditHashChain
from fincontroller.core.models import AuditBlock


class AuditVerifier:
    """Verifies that an audit trail has not been altered or corrupted."""

    @staticmethod
    def verify_chain(chain: List[AuditBlock]) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Verify all cryptographic linkages in the audit chain.
        Returns (is_valid, corrupted_index, failure_reason).
        """
        if not chain:
            return False, 0, "Audit chain is empty."

        # Check Genesis Block
        genesis = chain[0]
        if genesis.index != 0:
            return False, 0, f"Genesis block has invalid index: {genesis.index}"
        if genesis.previous_hash != AuditHashChain.GENESIS_PREV_HASH:
            return False, 0, f"Genesis block has invalid previous_hash: {genesis.previous_hash}"

        # Verify Genesis Hashes
        expected_payload_hash = AuditHashChain.compute_payload_hash(genesis.payload)
        if genesis.payload_hash != expected_payload_hash:
            return False, 0, f"Genesis block payload hash mismatch. Data was tampered."

        expected_block_hash = AuditHashChain.compute_block_hash(
            genesis.index,
            genesis.timestamp,
            genesis.previous_hash,
            genesis.event_type,
            genesis.payload_hash,
            genesis.operator,
        )
        if genesis.block_hash != expected_block_hash:
            return False, 0, f"Genesis block hash mismatch. Block header was tampered."

        # Verify Sequential Linkages
        for i in range(1, len(chain)):
            curr = chain[i]
            prev = chain[i - 1]

            if curr.index != i:
                return False, i, f"Block index discontinuity at index {i} (found {curr.index})."

            if curr.previous_hash != prev.block_hash:
                return (
                    False,
                    i,
                    f"Cryptographic link broken at block {i}: previous_hash '{curr.previous_hash[:12]}...' "
                    f"does not match block {i-1} hash '{prev.block_hash[:12]}...'.",
                )

            # Check Payload Integrity
            computed_payload_hash = AuditHashChain.compute_payload_hash(curr.payload)
            if curr.payload_hash != computed_payload_hash:
                return (
                    False,
                    i,
                    f"Tampering detected in payload of block {i}. Stored payload_hash does not match recomputed SHA-256.",
                )

            # Check Block Header Hash Integrity
            computed_block_hash = AuditHashChain.compute_block_hash(
                curr.index,
                curr.timestamp,
                curr.previous_hash,
                curr.event_type,
                curr.payload_hash,
                curr.operator,
            )
            if curr.block_hash != computed_block_hash:
                return (
                    False,
                    i,
                    f"Block hash forgery detected at block {i}. Header hash validation failed.",
                )

        return True, None, "Audit chain integrity 100% verified. Zero tampering detected."

    @classmethod
    def verify_stored_log(cls, storage_path: Optional[str] = None) -> Dict[str, Any]:
        """Convenience method to verify on-disk audit log."""
        chain_mgr = AuditHashChain(storage_path=storage_path)
        chain = chain_mgr.get_chain()
        is_valid, err_idx, msg = cls.verify_chain(chain)

        return {
            "verified": is_valid,
            "total_blocks": len(chain),
            "chain_head": chain[-1].block_hash if chain else None,
            "corrupted_block_index": err_idx,
            "message": msg,
        }
