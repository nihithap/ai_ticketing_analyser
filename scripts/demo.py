"""
Standalone demo script: exercises the RAG pipeline directly (no HTTP layer)
so you can sanity-check retrieval, classification, and recommendation
generation from the command line.

Usage:
    python scripts/demo.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.core.rag_pipeline import TicketRAGPipeline


def main():
    with open(settings.SAMPLE_TICKETS_PATH) as f:
        tickets = json.load(f)

    pipeline = TicketRAGPipeline()
    pipeline.build_from_corpus(tickets)

    new_ticket = {
        "title": "Getting logged out randomly and 2FA text never shows up",
        "description": (
            "I keep getting kicked out of my account and when I try to log back in, "
            "the text message with the verification code never arrives."
        ),
    }

    print("\n=== New Ticket ===")
    print(json.dumps(new_ticket, indent=2))

    result = pipeline.generate_recommendation(new_ticket["title"], new_ticket["description"])

    print("\n=== Classification ===")
    print(json.dumps(result["classification"], indent=2))

    print("\n=== Top Similar Tickets ===")
    for t in result["similar_tickets"]:
        print(f"  [{t['similarity_score']:.3f}] {t['id']} - {t['title']}")

    print("\n=== Knowledge-Graph Related Ticket IDs ===")
    print(result["graph_related_ticket_ids"])

    print("\n=== Recommended Resolution ===")
    print(result["recommended_resolution"])
    print(f"\nConfidence: {result['recommendation_confidence']}")

    print("\n=== Reasoning Trace ===")
    for r in result["reasoning"]:
        print(f"  - {r}")


if __name__ == "__main__":
    main()
