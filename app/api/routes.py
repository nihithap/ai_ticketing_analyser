"""
API routes for the ticket triage & recommendation system.
"""
import logging

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import (
    ClassificationResult,
    GraphRelatedResponse,
    IngestResponse,
    RecommendationResponse,
    SimilarTicket,
    TicketIngestRequest,
    TicketNode,
    TicketQueryRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_pipeline(request: Request):
    """Retrieves the singleton RAG pipeline stored on app.state at startup."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialized yet")
    return pipeline


@router.get("/health")
def health_check(request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    return {
        "status": "ok" if pipeline else "initializing",
        "vector_count": pipeline.vector_store.size() if pipeline else 0,
        "graph_nodes": pipeline.knowledge_graph.node_count() if pipeline else 0,
    }


@router.post("/tickets/classify", response_model=ClassificationResult)
def classify_ticket(payload: TicketQueryRequest, request: Request):
    pipeline = get_pipeline(request)
    retrieved = pipeline.retrieve_similar(payload.title, payload.description)
    result = pipeline.classify(payload.title, payload.description, retrieved)
    return ClassificationResult(**result)


@router.post("/tickets/recommend", response_model=RecommendationResponse)
def recommend_resolution(payload: TicketQueryRequest, request: Request):
    pipeline = get_pipeline(request)
    result = pipeline.generate_recommendation(payload.title, payload.description)

    return RecommendationResponse(
        query_title=payload.title,
        classification=ClassificationResult(**result["classification"]),
        similar_tickets=[SimilarTicket(**t) for t in result["similar_tickets"]],
        graph_related_ticket_ids=result["graph_related_ticket_ids"],
        recommended_resolution=result["recommended_resolution"],
        recommendation_confidence=result["recommendation_confidence"],
        reasoning=result["reasoning"],
    )


@router.post("/tickets/ingest", response_model=IngestResponse)
def ingest_ticket(payload: TicketIngestRequest, request: Request):
    pipeline = get_pipeline(request)
    ticket_id = pipeline.ingest_ticket(payload.model_dump())
    return IngestResponse(id=ticket_id, message="Ticket ingested and indexed successfully.")


@router.get("/tickets/similar/{ticket_id}")
def get_similar_by_id(ticket_id: str, request: Request):
    pipeline = get_pipeline(request)
    ticket = pipeline.vector_store.get_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")
    retrieved = pipeline.retrieve_similar(ticket["title"], ticket["description"])
    # Exclude the ticket itself from its own neighbor list
    filtered = [(m, s) for m, s in retrieved if m["id"] != ticket_id]
    return {
        "ticket_id": ticket_id,
        "similar_tickets": [SimilarTicket(**m, similarity_score=round(s, 4)) for m, s in filtered],
    }


@router.get("/knowledge-graph/related/{ticket_id}", response_model=GraphRelatedResponse)
def get_graph_related(ticket_id: str, request: Request):
    pipeline = get_pipeline(request)
    if ticket_id not in pipeline.knowledge_graph.graph:
        raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found in knowledge graph")

    related = pipeline.knowledge_graph.get_related_tickets(ticket_id)
    centrality = pipeline.knowledge_graph.centrality_score(ticket_id)

    return GraphRelatedResponse(
        ticket_id=ticket_id,
        related=[
            TicketNode(id=r["id"], title=r["title"], category=r["category"], priority=r["priority"])
            for r in related
        ],
        centrality_score=centrality,
    )
