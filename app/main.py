"""
FastAPI application entrypoint for the Intelligent Ticket Triage &
Recommendation System.

On startup, builds (or loads) the RAG pipeline: NLP preprocessing models,
Sentence Transformer embeddings, FAISS vector index, and the NetworkX
knowledge graph, all seeded from historical ticket data.
"""
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings
from app.core.rag_pipeline import TicketRAGPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


def load_historical_tickets() -> list:
    with open(settings.SAMPLE_TICKETS_PATH, "r") as f:
        return json.load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up: initializing RAG pipeline...")
    pipeline = TicketRAGPipeline()
    tickets = load_historical_tickets()
    pipeline.build_from_corpus(tickets)
    app.state.pipeline = pipeline
    logger.info("Startup complete. Pipeline is ready to serve requests.")
    yield
    logger.info("Shutting down: persisting index and graph state...")
    try:
        pipeline.vector_store.save()
        pipeline.knowledge_graph.save()
    except Exception as exc:
        logger.warning(f"Could not persist state on shutdown: {exc}")


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=(
        "NLP-driven ticket triage combining Sentence Transformer embeddings, "
        "FAISS vector search, Gensim topic modeling, a NetworkX knowledge graph, "
        "and a custom retrieval-augmented recommendation pipeline."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

# Include API routes
app.include_router(router, prefix="/api/v1", tags=["tickets"])


@app.get("/", include_in_schema=False)
def index_page():
    """Serves the Support Team Triage & Resolution GUI."""
    index_file = settings.STATIC_DIR / "index.html"
    return FileResponse(index_file)


@app.get("/api")
def api_info():
    return {
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
