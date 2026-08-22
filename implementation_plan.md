# Implementation Plan: AI Finance Controller (Settlement Reconciliation & Q&A Agent)

Building a high-throughput, explainable, and tamper-evident financial settlement reconciliation engine with natural language Q&A and honest exception reporting for the **Razorpay AI Buildathon (AI Finance Controller Track)**.

## Architectural & Design Philosophy

Against Razorpay's 4 Evaluation Criteria:
1. **Problem Taste**: Addresses verification bottlenecks in fintech settlement & merchant ledger reconciliation. Handles realistic real-world discrepancies: gateway fees, TDS/taxes, split batch settlements, settlement delay windows (T+1/T+2), chargebacks, currency rounding, duplicate refund references, and merchant identifier typos.
2. **Build Quality**: Clean modular Python package (`fincontroller`), typed Pydantic models, deterministic multi-pass reconciliation engine, rich CLI (Typer + Rich), FastAPI web service + interactive web dashboard, Dockerfile, GitHub Actions CI pipeline, and exhaustive test coverage (`pytest` + `pytest-asyncio`).
3. **AI Judgment**: **Strict Rules-vs-LLM Boundary**. Numeric reconciliation is **100% deterministic** (no hallucinated matches, strict math & tolerance algorithms). AI/LLM (LangChain + ChromaDB) is exclusively used for contextual natural language querying, root-cause explanation synthesis, and daily finance executive summaries.
4. **Failure Recovery**: Visually instrumented resilience! Async retries with exponential backoff & jitter for ingestion sources, circuit breaker pattern, and deterministic template fallback when LLM API keys are absent, offline, or rate-limited.
5. **Tamper-Evident Audit Trail (Differentiator)**: Every reconciliation decision is linked in a cryptographic SHA-256 hash chain with block verification tools to guarantee audit immutability for compliance & regulators.
6. **Honest Accuracy Reporting**: Pre-seeded benchmark evaluation suite containing realistic edge cases with automated confusion matrices, precision/recall/F1 metrics, and honest reporting of human-review allocations.

---

## Repository Architecture

```
ai-finance-controller/
├── .github/
│   └── workflows/
│       └── ci.yml                     # GitHub Actions CI (lint, test, coverage)
├── Dockerfile                         # Container definition
├── docker-compose.yml                 # Standalone service compose
├── requirements.txt                   # Dependencies
├── pyproject.toml                     # Package metadata and test tools configuration
├── README.md                          # Comprehensive README (Architecture, Rules-vs-LLM, Benchmarks)
├── fincontroller/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py                  # Pydantic schema: NormalizedTransaction, MatchResult, AuditRecord
│   │   ├── exceptions.py              # Custom domain exceptions
│   │   └── config.py                  # Environment config & tolerance settings
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseIngestionAdapter
│   │   ├── razorpay_adapter.py        # Razorpay settlement/payment API & CSV parser
│   │   ├── bank_ledger_adapter.py     # Bank statement/ledger CSV & MT940-like parser
│   │   └── generator.py               # Seed data generator with ground truth annotations
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── matching_engine.py         # Multi-pass deterministic matching engine
│   │   ├── rules.py                   # Rule definitions (Exact, Fee-adjusted, Fuzzy Ref, Split, Window)
│   │   ├── split_resolver.py          # 1-to-N and N-to-1 batch settlement resolver
│   │   └── confidence.py              # Confidence scoring & 3-bucket classification logic
│   ├── audit/
│   │   ├── __init__.py
│   │   ├── hash_chain.py              # SHA-256 block ledger for tamper-evident decision logs
│   │   └── verifier.py                # Audit chain integrity verifier
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── vector_store.py            # ChromaDB document indexer for reconciliation results
│   │   ├── qa_agent.py                # LangChain Q&A agent over reconciliation & exceptions
│   │   ├── summarizer.py              # Daily financial controller executive summary generator
│   │   └── fallback_templates.py      # Resilient deterministic fallback generator when LLM is offline
│   ├── resilience/
│   │   ├── __init__.py
│   │   ├── retry.py                   # Async retry with exponential backoff & jitter
│   │   ├── circuit_breaker.py         # Circuit breaker for external sources & LLMs
│   │   └── logger.py                  # Structured JSON & console logger with telemetry
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py                     # FastAPI REST API
│   │   └── routes.py                  # Endpoints: /reconcile, /query, /audit/verify, /summary, /metrics
│   ├── ui/
│   │   ├── static/                    # Frontend assets (CSS, JS, icons)
│   │   │   ├── style.css              # Premium dark-mode modern dashboard styling
│   │   │   └── app.js                 # Dynamic UI logic, interactive query, audit visualizer
│   │   └── templates/
│   │       └── index.html             # Rich finance controller dashboard
│   └── cli/
│       ├── __init__.py
│       └── main.py                    # Typer CLI (reconcile, benchmark, verify-audit, ask, serve)
├── data/
│   ├── benchmark_ground_truth.json    # Seeded messy dataset with labeled truth
│   ├── sample_razorpay_settlements.csv
│   └── sample_bank_statement.csv
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_ingestion.py              # Test CSV/API parsing & normalization
    ├── test_matching_engine.py        # Comprehensive test of deterministic rules & splits
    ├── test_audit_trail.py            # Test tamper detection & chain verification
    ├── test_resilience.py             # Test retry, circuit breaker & fallback mechanism
    ├── test_rag_and_fallbacks.py      # Test Q&A and offline template fallbacks
    └── test_benchmarks.py             # Accuracy evaluation & metrics verification
```

---

## Proposed Implementation Phases

### Phase 1: Core Models, Ingestion & Ground Truth Generator
- **Normalized Schema**: `NormalizedTransaction` (id, source, amount, fee, tax, net_amount, currency, timestamp, reference_id, counterparty, status, raw_data).
- **Ingestion Adapters**:
  - `RazorpayAdapter`: Parses Razorpay settlements (settlement IDs, payout batches, fee breakdown, payment entity IDs).
  - `BankLedgerAdapter`: Parses bank statement feeds (UTR numbers, credit/debit remarks, value dates).
- **Messy Dataset Generator**:
  - Exact matches (standard happy path)
  - Fee deduction differences (Gross vs Net with 2% + 18% GST deductions)
  - Split payouts (1 bulk bank credit = 3 merchant settlements)
  - Date drift / delayed settlements (T+1, T+2, weekend drifts)
  - Fuzzy reference typos (e.g. `pay_N8z1aB` vs `pay_N8z1a8`, missing leading zeros)
  - Duplicate refund attempts & currency roundings (paise differences)
  - Genuinely unmatchable / missing counter-entries (orphaned bank credits, unpayout Razorpay balances)

### Phase 2: Deterministic Multi-Pass Matching Engine
- Multi-pass pipeline:
  - **Pass 1 (Exact Match)**: Exact reference ID + exact net amount + currency. (Confidence = 1.0, Code: `EXACT_MATCH_REF_AND_AMOUNT`)
  - **Pass 2 (Fee & Tax Adjusted Match)**: Reference ID matches + `amount_bank == amount_gateway - (fee + tax)`. (Confidence = 0.98, Code: `FEE_ADJUSTED_MATCH`)
  - **Pass 3 (Split / Batch Settlement Resolver)**: Greedy subset-sum / windowed matching for 1-to-N settlements matching a bulk UTR transfer within a date window. (Confidence = 0.95, Code: `SPLIT_BATCH_MATCH`)
  - **Pass 4 (Fuzzy Reference + Amount Match)**: High string similarity (Levenshtein / Jaro-Winkler >= 0.88) + exact amount within T+3 window. (Confidence = 0.85, Code: `FUZZY_REF_EXACT_AMOUNT_MATCH`)
  - **Pass 5 (Tolerance Window Match)**: Reference match with minor rounding difference (<= ₹1.00 or 0.05%) within 2 days. (Confidence = 0.80, Code: `AMOUNT_TOLERANCE_MATCH`)
  - **Pass 6 (Ambiguous & Exception Classification)**: Assigns remaining items to `NEEDS_HUMAN_REVIEW` (e.g., matching amount but ambiguous duplicate reference, or date outside tolerance) or `UNMATCHED`.
- **Classification Buckets**:
  - `AUTO_MATCHED` (Score >= 0.85)
  - `NEEDS_HUMAN_REVIEW` (0.40 <= Score < 0.85 or ambiguity detected)
  - `UNMATCHED` (Score < 0.40)

### Phase 3: Tamper-Evident Hash Chain Audit Log
- Implements cryptographic block chain: `Record_i = SHA256(Record_{i-1}.hash + timestamp + transaction_ids + match_decision + reason_code + confidence_score + operator)`.
- Exportable / verifiable audit journal.
- Standalone verification command `verify-audit` returns cryptographic proof of chain integrity or pinpoints exact index of any tampering.

### Phase 4: Failure Recovery & Resilience
- `AsyncRetryManager`: Exponential backoff with jitter for network/API requests.
- `CircuitBreaker`: Prevents cascading failure when upstream APIs fail.
- `ResilientFallbackEngine`: When ChromaDB or LLM (e.g., OpenAI / Gemini API) fails or times out, immediately activates rule-based natural language template generators without dropping user requests.
- Visually logged telemetry stream.

### Phase 5: RAG & Natural Language Q&A Layer
- Embeds reconciliation results, match metadata, reason codes, and exception details into ChromaDB vector store.
- Structured retriever + LangChain agent for queries:
  - "Why didn't transaction pay_K91827 reconcile?"
  - "Show me all split settlements from HDFC bank account on August 15th."
  - "What is our total unmatched exposure in INR?"
- Daily Finance Controller Summary generator with breakdown of reconciled volume, fees deducted, pending reviews, and risk alerts.

### Phase 6: FastAPI Backend, CLI & Modern Web Dashboard
- **FastAPI backend**: REST endpoints for file uploads, reconciliation triggers, audit chain validation, streaming Q&A, and live telemetry logs.
- **Web UI**: Modern dark-mode dashboard with glassmorphism, animated stat counters, reconciliation table with filters (Auto-matched, Human Review, Unmatched), interactive RAG Q&A chat, audit chain explorer with live tampering verification button, and live failure-recovery simulator.
- **Rich CLI**: CLI commands `fincontroller reconcile`, `fincontroller benchmark`, `fincontroller verify-audit`, `fincontroller ask`, `fincontroller serve`.

### Phase 7: Automated Tests, Benchmarks & CI
- Comprehensive test suite covering all modules.
- Labeled benchmark suite testing accuracy, precision, recall, and false-positive refusal rates.
- GitHub Actions workflow (`.github/workflows/ci.yml`) and `Dockerfile` + `docker-compose.yml`.

---

## Verification Plan

### Automated Testing
- Run full pytest test suite: `pytest tests/ -v --cov=fincontroller`
- Run accuracy & benchmark reporting: `python -m fincontroller.cli.main benchmark`
- Run audit chain verification test: `python -m fincontroller.cli.main verify-audit`
- Validate offline fallback behavior: Test RAG queries with LLM API disabled.

### Manual / Browser Verification
- Start FastAPI server and open web UI.
- Test reconciliation of sample messy datasets.
- Test interactive RAG Q&A ("Why did transaction X fail?").
- Trigger live audit verification and simulated network failure fallback to inspect visual resilience telemetry.
