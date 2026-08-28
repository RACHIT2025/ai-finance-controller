"""
Configuration and tolerances for the reconciliation engine.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # System settings
    APP_NAME: str = "Razorpay AI Finance Controller"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "127.0.0.1"

    # Reconciliation Engine Tolerances
    AMOUNT_ABSOLUTE_TOLERANCE: float = 1.00  # Max ₹1.00 rounding discrepancy
    AMOUNT_PERCENT_TOLERANCE: float = 0.0005  # 0.05% percentage tolerance
    DATE_WINDOW_DAYS: int = 3  # Max 3 days settlement drift (T+1, T+2, weekend)
    SPLIT_MAX_ITEMS: int = 5  # Max subset size for split batch settlement combinations
    FUZZY_STRING_SIMILARITY_THRESHOLD: float = 0.86  # Levenshtein/Jaro-Winkler ratio threshold

    # Standard Gateway Fee Deductions (for India / Razorpay standard MDR)
    DEFAULT_MDR_PERCENT: float = 0.02  # 2% standard MDR
    DEFAULT_GST_ON_FEE_PERCENT: float = 0.18  # 18% GST on MDR

    # Confidence Score Thresholds
    AUTO_MATCH_THRESHOLD: float = 0.85
    HUMAN_REVIEW_THRESHOLD: float = 0.40

    # RAG / LLM Configuration
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_MODEL: str = "gpt-4o-mini"
    LLM_PROVIDER: str = "fallback"  # 'openai', 'gemini', or 'fallback'
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # Audit Trail Configuration
    AUDIT_SECRET_SALT: str = "razorpay_ai_controller_audit_salt_2026"
    AUDIT_STORAGE_PATH: str = "./data/audit_log.json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def get_effective_gemini_key(self) -> Optional[str]:
        return self.GEMINI_API_KEY or self.GOOGLE_API_KEY



settings = Settings()
