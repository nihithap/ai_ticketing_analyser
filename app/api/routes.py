"""
API routes for the ticket triage & recommendation system.
"""
import csv
import io
import logging
from collections import Counter
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from app.models.schemas import (
    BatchProcessResponse,
    BatchTicketResult,
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
    retrieved = pipeline.retrieve_similar(payload.title or "", payload.description or "")
    result = pipeline.classify(payload.title or "", payload.description or "", retrieved)
    return ClassificationResult(**result)


@router.post("/tickets/recommend", response_model=RecommendationResponse)
def recommend_resolution(payload: TicketQueryRequest, request: Request):
    pipeline = get_pipeline(request)
    title = payload.title or ""
    desc = payload.description or payload.issue_details or ""
    if not title and desc:
        title = desc[:80]

    result = pipeline.generate_recommendation(title, desc)

    return RecommendationResponse(
        ticket_number=payload.ticket_number,
        query_title=title,
        classification=ClassificationResult(**result["classification"]),
        similar_tickets=[SimilarTicket(**t) for t in result["similar_tickets"]],
        graph_related_ticket_ids=result["graph_related_ticket_ids"],
        recommended_resolution=result["recommended_resolution"],
        recommendation_confidence=result["recommendation_confidence"],
        reasoning=result["reasoning"],
    )


@router.post("/tickets/batch-csv", response_model=BatchProcessResponse)
async def process_batch_csv(request: Request, file: UploadFile = File(...)):
    """
    Accepts an uploaded CSV file with ticket numbers and issue details,
    processes all tickets through the RAG pipeline, and returns triage
    and recommendations for each ticket along with batch statistics.
    """
    pipeline = get_pipeline(request)

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .csv file.")

    content_bytes = await file.read()
    try:
        content_text = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content_text = content_bytes.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Could not decode CSV file. Please upload a standard UTF-8 CSV.")

    csv_reader = csv.DictReader(io.StringIO(content_text))
    if not csv_reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or headers could not be found.")

    # Normalize headers to lowercase stripped strings
    field_map = {f.strip().lower(): f for f in csv_reader.fieldnames if f}

    def find_field(candidates: List[str]) -> Optional[str]:
        for c in candidates:
            if c in field_map:
                return field_map[c]
        return None

    ticket_num_col = find_field(["ticket_number", "ticket_no", "ticket_id", "ticket", "id", "inc_number", "ticket #", "ticket num"])
    title_col = find_field(["title", "summary", "subject", "issue_title", "short_description", "header"])
    desc_col = find_field(["issue_details", "description", "details", "issue", "problem", "notes", "body", "long_description"])

    if not desc_col and not title_col:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain at least an issue description or title column. Found headers: {list(csv_reader.fieldnames)}",
        )

    results: List[BatchTicketResult] = []
    category_counter = Counter()
    priority_counter = Counter()
    confidences: List[float] = []

    for idx, row in enumerate(csv_reader, start=1):
        ticket_num = (row.get(ticket_num_col) or "").strip() if ticket_num_col else f"T-{idx:04d}"
        if not ticket_num:
            ticket_num = f"T-{idx:04d}"

        title = (row.get(title_col) or "").strip() if title_col else ""
        desc = (row.get(desc_col) or "").strip() if desc_col else ""

        if not desc and title:
            desc = title
        elif not title and desc:
            title = desc[:80]

        if not desc:
            continue  # Skip completely empty rows

        res = pipeline.generate_recommendation(title, desc)
        classification = res["classification"]
        pred_cat = classification["predicted_category"]
        pred_pri = classification["predicted_priority"]
        cat_conf = classification["category_confidence"]
        pri_conf = classification["priority_confidence"]
        rec_conf = res["recommendation_confidence"]

        category_counter[pred_cat] += 1
        priority_counter[pred_pri] += 1
        confidences.append(rec_conf)

        top_sim = res["similar_tickets"][0] if res["similar_tickets"] else None

        results.append(
            BatchTicketResult(
                ticket_number=ticket_num,
                title=title,
                description=desc,
                predicted_category=pred_cat,
                predicted_priority=pred_pri,
                category_confidence=cat_conf,
                priority_confidence=pri_conf,
                recommended_resolution=res["recommended_resolution"],
                recommendation_confidence=rec_conf,
                dominant_topics=classification.get("dominant_topics", []),
                top_similar_ticket_id=top_sim["id"] if top_sim else None,
                top_similar_ticket_title=top_sim["title"] if top_sim else None,
                top_similarity_score=top_sim["similarity_score"] if top_sim else None,
                reasoning=res["reasoning"],
            )
        )

    avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

    return BatchProcessResponse(
        total_tickets=len(results),
        processed_count=len(results),
        category_summary=dict(category_counter),
        priority_summary=dict(priority_counter),
        average_confidence=avg_conf,
        results=results,
    )


@router.get("/tickets/sample-csv")
def download_sample_csv():
    """Generates and returns a downloadable sample CSV template for support teams."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ticket_number", "title", "issue_details"])
    writer.writerow(["INC-3001", "Cannot connect to company VPN", "User gets Error 691 authentication failure when connecting to the US-East VPN server gateway."])
    writer.writerow(["INC-3002", "Billing overcharge on annual renewal", "Customer was billed $499 instead of the discounted $399 renewal promo rate on invoice INV-9821."])
    writer.writerow(["INC-3003", "Mobile app keeps crashing on dashboard load", "iOS app version 4.2.1 crashes immediately upon opening the analytics dashboard tab."])
    writer.writerow(["INC-3004", "Password reset email not received", "Customer requested password reset link multiple times but email never arrives in inbox or spam."])
    writer.writerow(["INC-3005", "Database query timeout in reporting module", "Monthly CSV report export times out after 60 seconds with 504 Gateway Error."])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sample_support_tickets.csv"},
    )


@router.get("/tickets/list")
def list_all_tickets(request: Request):
    """Returns the list of historical tickets loaded in the vector store."""
    pipeline = get_pipeline(request)
    return {
        "count": len(pipeline.vector_store.metadata),
        "tickets": pipeline.vector_store.metadata,
    }


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
