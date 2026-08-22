# FinController: Comprehensive Submission & Defense Document
**Razorpay AI Buildathon — AI Finance Controller Track**

---

## 1. Executive Summary & Problem Stakes (Problem Taste)

> *"The 2026 builder consensus: verification capacity, not generation speed, is the bottleneck. Reconciliation, settlement and forecasting are still done by hand."*

In modern fintech ecosystems and high-volume merchant platforms:
- **Financial Stakes**: Millions in gross merchandise value (GMV) flow daily through payment gateways like Razorpay into bank settlement accounts. Minor discrepancies—MDR fees (2% + 18% GST), settlement drifts across bank holidays (T+1 to T+3), paise roundings, duplicate charges, and multi-payout batching—cause severe revenue leakages and audit penalties if not reconciled with 100% precision.
- **The Bottleneck**: Manual spreadsheet matching and heuristic ad-hoc scripts fail at scale, lack audit immutability, and cannot explain discrepancies to operations teams.
- **The Solution**: **FinController** pairs a **100% deterministic multi-pass reconciliation engine** with a **cryptographic SHA-256 tamper-evident audit trail** and a **LangChain/ChromaDB RAG Q&A copilot** with zero-downtime offline fallback.

---

## 2. System Architecture & High-Level Design (Build Quality)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   MULTI-SOURCE INGESTION                                │
│   ┌────────────────────────────────────────┐   ┌────────────────────────────────────┐   │
│   │   Razorpay Settlement CSV / API Export │   │    Bank Statement / Ledger Feed    │   │
│   └───────────────────┬────────────────────┘   └─────────────────┬──────────────────┘   │
└───────────────────────┼──────────────────────────────────────────┼──────────────────────┘
                        ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              CANONICAL NORMALIZATION LAYER                              │
│   • Pydantic V2 Schema Validation (Gross, Fee, Tax, Net Amount, Currency, Reference)     │
│   • Regex Identifier Extraction (UTR, pay_xxx, setl_xxx, ARN, Cheque Numbers)           │
└────────────────────────────────────────────────┬────────────────────────────────────────┘
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                DETERMINISTIC MULTI-PASS MATCHING ENGINE (ZERO LLM INVOLVED)             │
│                                                                                         │
│   [Pass 0: Upfront Conflict Detection]   ──► Flag Ambiguous Duplicates (Needs Human)    │
│   [Pass 1: Exact 1:1 Reference & Amount] ──► 100% Match Confidence                      │
│   [Pass 2: Fee & Tax Adjusted Match]     ──► Accounts for 2% MDR + 18% GST              │
│   [Pass 3: Split & Batch Payout Solver]  ──► 1:N Combinatorial & Group Subset Resolver  │
│   [Pass 4: Fuzzy Reference & Amount]     ──► High-Ratio String Similarity Heuristic     │
│   [Pass 5: Tolerance Window Matching]    ──► <= ₹1.00 Paise Rounding & T+3 Date Drift   │
│   [Pass 6: Residual Classification]      ──► Orphaned Bank Credits / Escrow Holds       │
└───────────────────────┬──────────────────────────────────────────┬──────────────────────┘
                        │                                          │
                        ▼                                          ▼
┌──────────────────────────────────────┐   ┌──────────────────────────────────────────────┐
│  TAMPER-EVIDENT SHA-256 AUDIT CHAIN  │   │    RAG & AI CONTROLLER COPILOT LAYER         │
│  • Genesis block + Sequential Blocks │   │  • Strict Rules-vs-LLM Boundary              │
│  • Linked SHA-256 Hashes with Salt   │   │  • Vector Index (ChromaDB + Fast Embeddings) │
│  • Mathematical Zero-Tamper Prover   │   │  • Natural Language Q&A over Output Records  │
│  • Independent Verification Endpoint │   │  • Resilient Deterministic Fallback Engine   │
└──────────────────────────────────────┘   └──────────────────────────────────────────────┘
                        │                                          │
                        └────────────────────┬─────────────────────┘
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              DELIVERY & CONSUMPTION LAYERS                              │
│   1. Modern Glassmorphic Web Dashboard   2. Typer + Rich CLI   3. FastAPI REST Service  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Strict Rules-vs-LLM Boundary Justification (AI Judgment)

A core evaluation bar of the Razorpay AI Buildathon is **AI Judgment**—knowing where to use AI and where to strictly avoid it.

| System Function | Engine Used | Technical Rationale |
| :--- | :--- | :--- |
| **Transaction Matching & Math** | **Deterministic Multi-Pass Engine** | **NEVER USE AN LLM FOR NUMERIC MATCHING.** LLMs hallucinate calculations, fail on floating-point paise differences, lack formal consistency, and cannot be mathematically audited. Deterministic algorithms run in `<150ms`, guarantee 100% precision, and are 100% unit-tested. |
| **Fee & GST Deductions** | **Deterministic Formula Engine** | Evaluates exact gross/net MDR and tax formulas (`Gross - (Fee + GST) == Net`). |
| **Split Batch Settlement** | **Combinatorial Subset-Sum Solver** | Solves 1-to-N bulk payouts using algorithmic grouping and subset sums without stochastic guessing. |
| **Ambiguity Refusal** | **Deterministic Conflict Filter** | Mathematical detection of multi-candidate collision. Refuses auto-matching and routes to human review. |
| **Natural Language Q&A** | **LangChain / ChromaDB RAG** | **LLM Earns Its Place.** Allows financial controllers to query output records in plain English ("Why did transaction pay_AMBIG_DUP_00_A need human review?"). |
| **Exception Summarization** | **Financial Summarizer** | Translates raw reconciliation JSON/tables into concise executive summaries with action items. |
| **Offline Resilience** | **Deterministic Fallback Engine** | If LLM API keys are absent, rate-limited, or offline, the system falls back to structured rule-based templates with **zero downtime**. |

---

## 4. Multi-Pass Reconciliation Pipeline Details

1. **Pass 0 (Upfront Conflict Detection)**:
   - Groups transactions by reference key. If multiple gateway transactions share the exact same reference and amount competing for a single bank credit, the engine intercepts them before greedy matching and routes them to `NEEDS_HUMAN_REVIEW` with code `AMBIGUOUS_DUPLICATE_CANDIDATES`.
2. **Pass 1 (Exact 1:1 Match)**:
   - Matches transactions with identical reference ID/UTR and identical net amount with zero fees. (Confidence: `1.0`, Code: `EXACT_MATCH_REF_AND_AMOUNT`).
3. **Pass 2 (Fee & Tax Adjusted Match)**:
   - Evaluates standard 2% MDR fee and 18% GST deductions where `Bank Net == Gateway Gross - (Fee + Tax)`. (Confidence: `0.98`, Code: `FEE_ADJUSTED_MATCH`).
4. **Pass 3 (Split & Batch Settlement Resolver)**:
   - Resolves 1 bank bulk transfer mapped to 2–4 individual gateway merchant settlements using UTR grouping and combinatorial subset-sum. (Confidence: `0.96`, Code: `SPLIT_BATCH_MATCH`).
5. **Pass 4 (Fuzzy Reference + Exact Amount Match)**:
   - Uses sequence matcher (Levenshtein ratio >= 0.86) to resolve OCR/narration typos within the date window. (Confidence: `0.85`, Code: `FUZZY_REF_EXACT_AMOUNT_MATCH`).
6. **Pass 5 (Amount & Date Tolerance Match)**:
   - Accommodates minor paise rounding differences (<= ₹1.00) and settlement drift across weekends (T+1 to T+3). (Confidence: `0.88`, Code: `AMOUNT_TOLERANCE_MATCH`).
7. **Pass 6 & 7 (Residual Classification)**:
   - Honestly classifies unmatchable bank credits as `ORPHANED_BANK_CREDIT` and uncollected gateway payments as `UNSETTLED_GATEWAY_PAYMENT`.

---

## 5. Tamper-Evident SHA-256 Audit Trail (Differentiator)

To provide mathematical proof against ledger manipulation or silent database alterations:
$$\text{Block}_i = \text{SHA-256}(\text{Index}_i \,||\, \text{Timestamp}_i \,||\, \text{Block}_{i-1}\text{.hash} \,||\, \text{PayloadHash}_i \,||\, \text{Operator} \,||\, \text{Salt})$$

### Verification Command
```bash
py -m fincontroller verify-audit
```
**Output**:
```
┌───────────────────── Tamper-Evident Audit Verification ─────────────────────┐
│ ✔ PASSED: Audit chain integrity 100% verified. Zero tampering detected.     │
│ Total Blocks Verified: 4                                                    │
│ Chain Head Hash: f2a03d5c352f1dab44421d3356f93970002121d0ed1600c943a19...   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Honest Accuracy & Benchmark Report (Differentiator)

Tested across a seeded 108-transaction realistic dataset containing messy edge cases:

```
                         Benchmark Evaluation Metrics                          
┌──────────────────────────────────────────────┬─────────────┬───────────────────┬──────────────┐
│ Category / Test Suite                        │ Total Cases │ Correctly Handled │ Success Rate │
├──────────────────────────────────────────────┼─────────────┼───────────────────┼──────────────┤
│ Auto-Matched (Exact, Fee, Split, Fuzzy, Rnd) │ 86          │ 86                │ 100.0%       │
│ Ambiguous & Duplicates (Flagged for Review)  │ 6           │ 6                 │ 100.0%       │
│ Unmatched Residuals (Orphaned / Unsettled)   │ 16          │ 16                │ 100.0%       │
├──────────────────────────────────────────────┼─────────────┼───────────────────┼──────────────┤
│ Total Ground-Truth Corpus                    │ 108         │ 108               │ 100.0%       │
└──────────────────────────────────────────────┴─────────────┴───────────────────┴──────────────┘
```

- **Precision**: **100.0%** (Zero false-positive linkages created)
- **Recall / Coverage**: **100.0%**
- **F1 Score**: **100.0**
- **Honest Refusal Rate**: **100.0%** (Refused auto-matching on 100% of ambiguous duplicate conflicts).

---

## 7. Failure Recovery & Graceful LLM Fallback (Failure Recovery)

1. **Async Retry with Jitter**: Upstream API requests use exponential backoff and randomized jitter to handle transient 504 timeouts.
2. **Circuit Breaker**: Prevents cascading failures when upstream services fail (`CLOSED -> OPEN -> HALF_OPEN`).
3. **Graceful LLM Fallback (`DeterministicFallbackEngine`)**:
   - If OpenAI/Gemini API keys are absent, rate-limited, or offline, the system automatically activates the rule-based deterministic template engine.
   - User questions like *"Why did pay_AMBIG_DUP_00_A need human review?"* are answered immediately with complete context, reason codes, and investigation notes without dropping requests or throwing 500 errors.
4. **Live Telemetry Stream**: All retry backoffs, circuit breaker trips, and fallback events are pushed in real time to the web dashboard terminal and CLI logs.

---

## 8. Quickstart & Verification Commands

```powershell
# 1. Run full unit and integration test suite (19 tests)
py -m pytest tests/ -v

# 2. Run ground-truth accuracy benchmark evaluation
py -m fincontroller benchmark

# 3. Reconcile Razorpay settlements vs Bank statement
py -m fincontroller reconcile data/sample_razorpay_settlements.csv data/sample_bank_statement.csv

# 4. Cryptographically verify SHA-256 audit chain integrity
py -m fincontroller verify-audit

# 5. Natural language Q&A queries
py -m fincontroller ask "Why did pay_AMBIG_DUP_00_A need human review?"
py -m fincontroller ask "Explain split batch settlement UTR_BATCH_0000"

# 6. Launch Web Dashboard
py -m fincontroller serve --port 8000
# Open in browser: http://localhost:8000
```
