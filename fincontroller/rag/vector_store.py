"""
Vector Store Indexer for Reconciliation Documents and Exception Records.
Uses ChromaDB where available with seamless fallback to in-memory index.
"""

from typing import Any, Dict, List, Optional
from fincontroller.core.config import settings
from fincontroller.core.models import NormalizedTransaction, ReconciliationReport
from fincontroller.resilience.logger import telemetry


import hashlib
import numpy as np


class FastEmbeddingFunction:
    """Zero-network deterministic token hashing embedding for instant ChromaDB indexing."""
    def __call__(self, input: List[str]) -> List[List[float]]:
        embeddings = []
        for text in input:
            vec = np.zeros(64, dtype=np.float32)
            tokens = text.lower().split()
            for t in tokens:
                h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
                idx = h % 64
                vec[idx] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            embeddings.append(vec.tolist())
        return embeddings


class ReconciliationDocStore:
    """
    Indexes reconciliation reports, matches, exceptions, and audit records
    for semantic and hybrid retrieval.
    """

    def __init__(self):
        self.documents: List[Dict[str, Any]] = []
        self.chroma_collection = None
        self._init_chroma()

    def _init_chroma(self) -> None:
        """Attempt to initialize ChromaDB collection with fast local embedding."""
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            client = chromadb.EphemeralClient(
                settings=ChromaSettings(anonymized_telemetry=False, is_persistent=False)
            )
            self.chroma_collection = client.get_or_create_collection(
                name="reconciliation_knowledge",
                embedding_function=FastEmbeddingFunction(),
            )
            telemetry.push("INFO", "RAG_VECTOR_STORE", "ChromaDB ephemeral vector store initialized with FastEmbedding.")
        except Exception as e:
            self.chroma_collection = None
            telemetry.push(
                "INFO",
                "RAG_VECTOR_STORE",
                f"Using fast in-memory hybrid document store.",
            )

    def index_report(self, report: ReconciliationReport) -> int:
        """Extract and index documents from a reconciliation report."""
        self.documents.clear()
        doc_count = 0

        # 1. Summary Document
        summary_text = (
            f"Reconciliation Summary Session {report.session_id}. "
            f"Auto matched: {report.summary.auto_matched_count}, "
            f"Human review: {report.summary.human_review_count}, "
            f"Unmatched gateway: {report.summary.unmatched_gateway_count}, "
            f"Unmatched bank: {report.summary.unmatched_bank_count}, "
            f"Reconciled volume: INR {report.summary.reconciled_volume:,.2f}, "
            f"Total gateway volume: INR {report.summary.total_gateway_volume:,.2f}, "
            f"Total bank volume: INR {report.summary.total_bank_volume:,.2f}."
        )
        self._add_doc(
            doc_id=f"summary_{report.session_id}",
            text=summary_text,
            metadata={"type": "summary", "session_id": report.session_id},
        )
        doc_count += 1

        # 2. Match Documents
        for m in report.matches:
            match_text = (
                f"Match {m.match_id}: Status {m.category.value}, Reason {m.reason_code.value}. "
                f"Gateway transactions: {', '.join(m.gateway_tx_ids)}. "
                f"Bank transactions: {', '.join(m.bank_tx_ids)}. "
                f"Explanation: {m.explanation}. "
                f"Fee detected: INR {m.fee_detected}. "
                f"Discrepancy: INR {m.amount_discrepancy}. "
                f"Settlement drift: {m.date_diff_hours} hours. "
                f"Confidence score: {m.confidence}."
            )
            self._add_doc(
                doc_id=m.match_id,
                text=match_text,
                metadata={
                    "type": "match",
                    "category": m.category.value,
                    "reason_code": m.reason_code.value,
                    "confidence": m.confidence,
                },
            )
            doc_count += 1

        # 3. Human Review Documents
        for hr in report.human_reviews:
            hr_text = (
                f"Human Review Case {hr.match_id}: Reason {hr.reason_code.value}. "
                f"Gateway items: {', '.join(hr.gateway_tx_ids)}. "
                f"Bank items: {', '.join(hr.bank_tx_ids)}. "
                f"Ambiguity note: {hr.explanation}."
            )
            self._add_doc(
                doc_id=hr.match_id,
                text=hr_text,
                metadata={"type": "human_review", "reason_code": hr.reason_code.value},
            )
            doc_count += 1

        # 4. Unmatched Items
        for gw in report.unmatched_gateway:
            gw_text = (
                f"Unmatched Razorpay Gateway Transaction {gw.id}. Reference ID: {gw.reference_id}. "
                f"Amount: INR {gw.amount}, Net: INR {gw.net_amount}. "
                f"Status: {gw.status.value}. Date: {gw.timestamp}. Description: {gw.description}."
            )
            self._add_doc(
                doc_id=f"unmatched_gw_{gw.id}",
                text=gw_text,
                metadata={"type": "unmatched_gateway", "tx_id": gw.id, "ref": gw.reference_id},
            )
            doc_count += 1

        for bnk in report.unmatched_bank:
            bnk_text = (
                f"Unmatched Bank Deposit {bnk.id}. Reference ID: {bnk.reference_id}. "
                f"Net Credit: INR {bnk.net_amount}. Date: {bnk.timestamp}. Description: {bnk.description}."
            )
            self._add_doc(
                doc_id=f"unmatched_bnk_{bnk.id}",
                text=bnk_text,
                metadata={"type": "unmatched_bank", "tx_id": bnk.id, "ref": bnk.reference_id},
            )
            doc_count += 1

        return doc_count

    def _add_doc(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
        doc = {"id": doc_id, "text": text, "metadata": metadata}
        self.documents.append(doc)
        if self.chroma_collection:
            try:
                self.chroma_collection.add(
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[metadata],
                )
            except Exception:
                pass

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant context for a query."""
        if self.chroma_collection:
            try:
                res = self.chroma_collection.query(query_texts=[query], n_results=top_k)
                if res and res.get("documents") and len(res["documents"][0]) > 0:
                    matched_docs = []
                    for i, doc_text in enumerate(res["documents"][0]):
                        matched_docs.append({
                            "id": res["ids"][0][i],
                            "text": doc_text,
                            "metadata": res["metadatas"][0][i],
                        })
                    return matched_docs
            except Exception:
                pass

        # In-memory keyword & token similarity fallback
        q_tokens = set(query.lower().split())
        scored_docs = []
        for doc in self.documents:
            d_tokens = set(doc["text"].lower().split())
            overlap = len(q_tokens.intersection(d_tokens))
            if overlap > 0:
                scored_docs.append((overlap, doc))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [d[1] for d in scored_docs[:top_k]]
