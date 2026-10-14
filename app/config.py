"""
Central configuration for the Intelligent Ticket Triage Platform.
All tunable parameters live here so behavior can be adjusted without
touching business logic.
"""
import os
from pathlib import Path
from typing import Dict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    # --- Paths ---
    DATA_DIR: Path = BASE_DIR / "app" / "data"
    STATIC_DIR: Path = BASE_DIR / "app" / "static"
    INDEX_DIR: Path = BASE_DIR / "storage"
    REPOS_DIR: Path = BASE_DIR / "sample_repos"

    @property
    def SAMPLE_TICKETS_PATH(self) -> Path:
        return self.DATA_DIR / "sample_tickets.json"

    @property
    def FAISS_INDEX_PATH(self) -> Path:
        self.INDEX_DIR.mkdir(exist_ok=True)
        return self.INDEX_DIR / "tickets.index"

    @property
    def FAISS_METADATA_PATH(self) -> Path:
        self.INDEX_DIR.mkdir(exist_ok=True)
        return self.INDEX_DIR / "tickets_metadata.json"

    @property
    def KG_STORAGE_PATH(self) -> Path:
        self.INDEX_DIR.mkdir(exist_ok=True)
        return self.INDEX_DIR / "knowledge_graph.gpickle"

    # --- Embedding model ---
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = 384

    # --- spaCy model ---
    SPACY_MODEL_NAME: str = os.getenv("SPACY_MODEL_NAME", "en_core_web_sm")

    # --- Topic modeling (Gensim) ---
    LSI_NUM_TOPICS: int = int(os.getenv("LSI_NUM_TOPICS", 20))
    TFIDF_MIN_DF: int = 1

    # --- Retrieval / RAG ---
    TOP_K_RETRIEVAL: int = int(os.getenv("TOP_K_RETRIEVAL", 5))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", 0.35))
    KG_EXPANSION_DEPTH: int = int(os.getenv("KG_EXPANSION_DEPTH", 1))

    # --- Classification ---
    CATEGORIES = [
        "Billing",
        "Technical Issue",
        "Account Access",
        "Feature Request",
        "Bug Report",
        "Performance",
        "Security",
        "General Inquiry",
    ]
    PRIORITIES = ["Low", "Medium", "High", "Critical"]

    # --- Git Repository & Applications Registry ---
    # Maps application names to their respective codebase directories and Git repos
    APP_REPO_MAPPINGS: Dict[str, dict] = {
        "AuthService": {
            "name": "AuthService",
            "repo_url": "https://github.com/org/auth-service.git",
            "local_path": "AuthService",
            "description": "User authentication, JWT token generation, OAuth2, and session management.",
            "language": "Python",
        },
        "PaymentGateway": {
            "name": "PaymentGateway",
            "repo_url": "https://github.com/org/payment-gateway.git",
            "local_path": "PaymentGateway",
            "description": "Payment processor integration, currency conversions, refunds, and webhook listeners.",
            "language": "Python",
        },
        "BillingEngine": {
            "name": "BillingEngine",
            "repo_url": "https://github.com/org/billing-engine.git",
            "local_path": "BillingEngine",
            "description": "Invoice generation, subscription renewal calculations, and tax jurisdiction rules.",
            "language": "Python",
        },
        "OrderProcessing": {
            "name": "OrderProcessing",
            "repo_url": "https://github.com/org/order-processing.git",
            "local_path": "OrderProcessing",
            "description": "Order fulfillment, inventory reservations, checkout pipelines, and catalog integration.",
            "language": "Python",
        },
        "MobileAppBackend": {
            "name": "MobileAppBackend",
            "repo_url": "https://github.com/org/mobile-backend.git",
            "local_path": "MobileAppBackend",
            "description": "Mobile REST/GraphQL API gateway, push notifications, and device telemetry.",
            "language": "Python",
        },
    }

    # --- API ---
    API_TITLE = "Intelligent Ticket Triage & Recommendation System"
    API_VERSION = "1.1.0"


settings = Settings()
