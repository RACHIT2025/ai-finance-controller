"""
Unit tests for the Cryptographic Tamper-Evident Audit Trail.
"""

import tempfile
import pytest
from fincontroller.audit.hash_chain import AuditHashChain
from fincontroller.audit.verifier import AuditVerifier


def test_genesis_block_and_append():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        chain = AuditHashChain(storage_path=tmp.name)
        assert len(chain.get_chain()) == 1
        genesis = chain.get_chain()[0]
        assert genesis.index == 0
        assert genesis.previous_hash == AuditHashChain.GENESIS_PREV_HASH

        # Append event
        block1 = chain.append_event("TEST_EVENT", {"amount": 100.0, "status": "reconciled"})
        assert block1.index == 1
        assert block1.previous_hash == genesis.block_hash
        assert len(chain.get_chain()) == 2


def test_audit_verification_success():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        chain = AuditHashChain(storage_path=tmp.name)
        chain.append_event("RECON_1", {"reconciled_vol": 5000.0})
        chain.append_event("RECON_2", {"reconciled_vol": 12000.0})

        is_valid, err_idx, msg = AuditVerifier.verify_chain(chain.get_chain())
        assert is_valid is True
        assert err_idx is None


def test_audit_tampering_detection():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        chain = AuditHashChain(storage_path=tmp.name)
        chain.append_event("MATCH_1", {"tx_id": "pay_001", "amount": 1000.0})
        chain.append_event("MATCH_2", {"tx_id": "pay_002", "amount": 2000.0})

        # Maliciously alter payload of block 1
        chain_blocks = chain.get_chain()
        chain_blocks[1].payload["amount"] = 9999999.0

        is_valid, err_idx, msg = AuditVerifier.verify_chain(chain_blocks)
        assert is_valid is False
        assert err_idx == 1
        assert "Tampering detected" in msg or "mismatch" in msg


def test_audit_break_previous_hash_linkage():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        chain = AuditHashChain(storage_path=tmp.name)
        chain.append_event("EVENT_A", {"data": "A"})
        chain.append_event("EVENT_B", {"data": "B"})

        chain_blocks = chain.get_chain()
        chain_blocks[2].previous_hash = "forged_previous_hash_0000000000000000"

        is_valid, err_idx, msg = AuditVerifier.verify_chain(chain_blocks)
        assert is_valid is False
        assert err_idx == 2
        assert "broken" in msg or "does not match" in msg
