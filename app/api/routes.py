"""
API routes for the ticket triage & recommendation system.
"""
import csv
import io
import logging
from collections import Counter
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from app.config import settings
from app.models.schemas import (
    BatchProcessResponse,
    BatchTicketResult,
    ClassificationResult,
    CodeAnalysisResult,
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
        "mapped_apps": list(settings.APP_REPO_MAPPINGS.keys()),
    }


@router.get("/applications")
def list_applications():
    """Returns the list of configured applications and their Git repo mappings."""
    return {
        "applications": list(settings.APP_REPO_MAPPINGS.values())
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

    result = pipeline.generate_recommendation(
        title=title,
        description=desc,
        application_name=payload.application_name,
    )

    code_analysis_obj = (
        CodeAnalysisResult(**result["code_analysis"]) if result.get("code_analysis") else None
    )

    return RecommendationResponse(
        ticket_number=payload.ticket_number,
        application_name=result.get("application_name"),
        query_title=title,
        classification=ClassificationResult(**result["classification"]),
        similar_tickets=[SimilarTicket(**t) for t in result["similar_tickets"]],
        graph_related_ticket_ids=result["graph_related_ticket_ids"],
        recommended_resolution=result["recommended_resolution"],
        recommendation_confidence=result["recommendation_confidence"],
        code_analysis=code_analysis_obj,
        source_channel=result.get("source_channel", "Historical Ticket RAG"),
        reasoning=result["reasoning"],
    )


@router.post("/tickets/batch-csv", response_model=BatchProcessResponse)
async def process_batch_csv(request: Request, file: UploadFile = File(...)):
    """
    Accepts an uploaded CSV file with ticket numbers, application names, and issue details,
    processes all tickets through the RAG & Git Code Analysis pipeline, and returns triage
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
    app_col = find_field(["application_name", "application", "app_name", "app", "service", "repo"])
    title_col = find_field(["title", "summary", "subject", "issue_title", "short_description", "header"])
    desc_col = find_field(["issue_details", "description", "details", "issue", "problem", "notes", "body", "long_description", "stacktrace"])

    if not desc_col and not title_col:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain at least an issue description or title column. Found headers: {list(csv_reader.fieldnames)}",
        )

    results: List[BatchTicketResult] = []
    category_counter = Counter()
    priority_counter = Counter()
    confidences: List[float] = []
    git_analyses_count = 0

    for idx, row in enumerate(csv_reader, start=1):
        ticket_num = (row.get(ticket_num_col) or "").strip() if ticket_num_col else f"T-{idx:04d}"
        if not ticket_num:
            ticket_num = f"T-{idx:04d}"

        app_name = (row.get(app_col) or "").strip() if app_col else None
        title = (row.get(title_col) or "").strip() if title_col else ""
        desc = (row.get(desc_col) or "").strip() if desc_col else ""

        if not desc and title:
            desc = title
        elif not title and desc:
            title = desc[:80]

        if not desc:
            continue  # Skip completely empty rows

        res = pipeline.generate_recommendation(
            title=title,
            description=desc,
            application_name=app_name,
        )
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
        code_analysis_data = res.get("code_analysis")
        if code_analysis_data:
            git_analyses_count += 1

        code_analysis_obj = CodeAnalysisResult(**code_analysis_data) if code_analysis_data else None

        results.append(
            BatchTicketResult(
                ticket_number=ticket_num,
                application_name=app_name or (code_analysis_data["application_name"] if code_analysis_data else None),
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
                code_analysis=code_analysis_obj,
                code_analysis_applied=bool(code_analysis_obj),
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
        git_code_analyses_count=git_analyses_count,
        results=results,
    )


@router.get("/tickets/sample-csv")
def download_sample_csv():
    """Generates and returns a downloadable sample CSV template for support teams."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ticket_number", "application_name", "title", "issue_details"])
    writer.writerow([
        "INC-4001",
        "AuthService",
        "KeyError: 'user' when validating expired session payload",
        'File "AuthService/token_handler.py", line 10, in validate_user_session\n    user_id = session_data["user"]["id"]\nKeyError: \'user\'',
    ])
    writer.writerow([
        "INC-4002",
        "PaymentGateway",
        "ZeroDivisionError in currency conversion during refund",
        'File "PaymentGateway/processor.py", line 15, in process_refund\n    converted_amount = refund_amount / rate\nZeroDivisionError: division by zero',
    ])
    writer.writerow([
        "INC-4003",
        "BillingEngine",
        "Invoice tax jurisdiction calculation error",
        "Customer's latest invoice applied an 18% tax rate instead of the expected 8% based on their billing region.",
    ])
    writer.writerow([
        "INC-4004",
        "AuthService",
        "IndexError when extracting bearer token header",
        'File "AuthService/token_handler.py", line 24, in decode_auth_header\n    token = parts[1]\nIndexError: list index out of range',
    ])
    writer.writerow([
        "INC-4005",
        "MobileAppBackend",
        "App crashes when uploading files over 50MB",
        "Mobile app crashes consistently when attempting to upload files larger than 50MB from attachments screen.",
    ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sample_support_tickets_with_git.csv"},
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
