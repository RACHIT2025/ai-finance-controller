"""
LangChain RAG Q&A Agent with Automatic Deterministic Fallback.
Allows natural-language querying of reconciliation results, match reasons, and exceptions.
"""

from typing import Any, Dict, List, Optional
from fincontroller.core.config import settings
from fincontroller.core.models import ReconciliationReport
from fincontroller.rag.fallback_templates import DeterministicFallbackEngine
from fincontroller.rag.vector_store import ReconciliationDocStore
from fincontroller.resilience.logger import telemetry


class ReconciliationQAAgent:
    """
    RAG agent over reconciliation results.
    Strictly answers questions and explains reasons — NEVER performs numeric matching.
    """

    def __init__(self, doc_store: Optional[ReconciliationDocStore] = None):
        self.doc_store = doc_store or ReconciliationDocStore()
        self.active_report: Optional[ReconciliationReport] = None

    def set_report(self, report: ReconciliationReport) -> None:
        self.active_report = report
        self.doc_store.index_report(report)

    def answer_query(self, user_query: str) -> Dict[str, Any]:
        """
        Answer user question regarding reconciliation output.
        """
        if not self.active_report:
            return {
                "query": user_query,
                "answer": "No active reconciliation report is loaded. Please run a reconciliation first.",
                "source": "AGENT_ERROR",
                "retrieved_context": [],
            }

        query_clean = user_query.strip()

        # Check if external LLM configured and requested
        if (settings.OPENAI_API_KEY or settings.get_effective_gemini_key()) and settings.LLM_PROVIDER in ("openai", "gemini"):

            try:
                answer = self._run_llm_rag(query_clean)
                return {
                    "query": user_query,
                    "answer": answer,
                    "source": f"LLM_RAG_{settings.LLM_PROVIDER.upper()}",
                    "retrieved_context": self.doc_store.search(query_clean, top_k=3),
                }
            except Exception as e:
                telemetry.push(
                    level="WARNING",
                    component="LLM_DEGRADATION",
                    message=f"LLM call encountered error ({str(e)}). Gracefully falling back to deterministic template engine.",
                    metadata={"error": str(e)},
                )

        # Resilient Deterministic Engine
        retrieved = self.doc_store.search(query_clean, top_k=3)
        explanation = DeterministicFallbackEngine.explain_transaction(query_clean, self.active_report)

        return {
            "query": user_query,
            "answer": explanation,
            "source": "DETERMINISTIC_FALLBACK_ENGINE",
            "retrieved_context": retrieved,
        }

    def _run_llm_rag(self, query: str) -> str:
        """Internal LangChain RAG pipeline invocation."""
        context_docs = self.doc_store.search(query, top_k=4)
        context_str = "\n\n".join(d["text"] for d in context_docs)

        # Formulate grounded prompt strictly bounded to context
        prompt = (
            f"You are the AI Finance Controller Assistant at Razorpay.\n"
            f"Your job is ONLY to explain reconciliation results and exception reasons using the provided context.\n"
            f"CRITICAL RULE: Do NOT perform numeric matching. Only summarize and explain facts from the deterministic engine.\n\n"
            f"CONTEXT:\n{context_str}\n\n"
            f"USER QUESTION: {query}\n\n"
            f"ANSWER:"
        )

        gemini_key = settings.get_effective_gemini_key()
        provider = settings.LLM_PROVIDER.lower()

        if provider == "gemini" and gemini_key:
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={gemini_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 800,
                }
            }
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                raise RuntimeError(f"Gemini API returned status {res.status_code}: {res.text}")

        elif provider == "openai" and settings.OPENAI_API_KEY:
            try:
                from langchain_community.chat_models import ChatOpenAI
                llm = ChatOpenAI(temperature=0.0, openai_api_key=settings.OPENAI_API_KEY, model_name=settings.OPENAI_MODEL)
                resp = llm.invoke(prompt)
                return resp.content if hasattr(resp, "content") else str(resp)
            except Exception:
                import httpx
                headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": settings.OPENAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                }
                with httpx.Client(timeout=10.0) as client:
                    res = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                    if res.status_code == 200:
                        return res.json()["choices"][0]["message"]["content"].strip()
                    raise RuntimeError(f"OpenAI API returned status {res.status_code}: {res.text}")

        return DeterministicFallbackEngine.explain_transaction(query, self.active_report)

