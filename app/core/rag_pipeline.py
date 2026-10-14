"""
Custom RAG (Retrieval-Augmented Generation) pipeline for ticket triage.

Flow for an incoming ticket:
  1. Preprocess text (spaCy/NLTK) and compute LSI topic vector (Gensim).
  2. Embed text with Sentence Transformers.
  3. Retrieve top-k semantically similar historical tickets via FAISS (Facebook AI Similarity Search).
  4. Expand context using the NetworkX knowledge graph (category/tag/topic
     neighbors + graph-derived relevance signals).
  5. Classify category & priority via k-NN vote over retrieved neighbors.
  6. Generate a grounded recommendation by synthesizing the retrieved
     resolutions ("generation" here is extractive/template-based so the
     system runs fully offline; see `generate_with_llm` for how to swap in
     a call to the Anthropic API for abstractive generation).
"""
import logging
import uuid
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.core.embeddings import EmbeddingModel
from app.core.knowledge_graph import TicketKnowledgeGraph
from app.core.preprocessing import TextPreprocessor, TopicModeler
from app.core.vector_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class TicketRAGPipeline:
    def __init__(self):
        self.preprocessor = TextPreprocessor()
        self.topic_modeler = TopicModeler()
        self.embedder = EmbeddingModel()
        self.vector_store = FAISSVectorStore(dim=self.embedder.dim)
        self.knowledge_graph = TicketKnowledgeGraph()
        self._corpus_tokens_cache: List[List[str]] = []

    # -----------------------------------------------------------------
    # Corpus bootstrap
    # -----------------------------------------------------------------
    def build_from_corpus(self, tickets: List[Dict]) -> None:
        """
        Trains the topic model on the full historical corpus, then ingests
        every ticket into the vector store and knowledge graph. Call once
        at startup (or whenever the historical dataset changes materially).
        """
        logger.info(f"Building RAG pipeline from {len(tickets)} historical tickets...")
        full_texts = [f"{t['title']}. {t['description']}" for t in tickets]
        tokenized = [self.preprocessor.tokenize_and_lemmatize(t) for t in full_texts]
        self._corpus_tokens_cache = tokenized

        self.topic_modeler.fit(tokenized)

        for ticket, tokens in zip(tickets, tokenized):
            self._ingest_single(ticket, tokens, link_similarity=False)

        # Now that everything is embedded, wire up SIMILAR_TO edges based on
        # actual vector similarity (do this after full ingestion so every
        # ticket can see the complete neighbor set).
        self._build_similarity_edges()
        logger.info(
            f"Pipeline ready. Vector store: {self.vector_store.size()} vectors | "
            f"Knowledge graph: {self.knowledge_graph.node_count()} nodes, "
            f"{self.knowledge_graph.edge_count()} edges."
        )

    def _ingest_single(self, ticket: Dict, tokens: List[str], link_similarity: bool = True) -> str:
        ticket_id = ticket.get("id") or str(uuid.uuid4())
        ticket["id"] = ticket_id
        full_text = f"{ticket['title']}. {ticket['description']}"

        embedding = self.embedder.encode_single(full_text)
        metadata = {
            "id": ticket_id,
            "title": ticket["title"],
            "description": ticket["description"],
            "category": ticket.get("category"),
            "priority": ticket.get("priority"),
            "resolution": ticket.get("resolution"),
            "tags": ticket.get("tags", []),
        }
        self.vector_store.add(embedding.reshape(1, -1), [metadata])

        dominant_topics = self.topic_modeler.get_dominant_topics(tokens) if self.topic_modeler.is_trained else []
        self.knowledge_graph.add_ticket(
            ticket_id=ticket_id,
            title=ticket["title"],
            category=ticket.get("category"),
            priority=ticket.get("priority"),
            tags=ticket.get("tags", []),
            topics=dominant_topics,
        )

        if link_similarity:
            self._link_new_ticket_similarity(ticket_id, embedding)

        return ticket_id

    def _link_new_ticket_similarity(self, ticket_id: str, embedding) -> None:
        neighbors = self.vector_store.search(embedding, k=settings.TOP_K_RETRIEVAL + 1)
        for meta, score in neighbors:
            if meta["id"] != ticket_id and score >= settings.SIMILARITY_THRESHOLD:
                self.knowledge_graph.add_similarity_edge(ticket_id, meta["id"], score)

    def _build_similarity_edges(self) -> None:
        for meta in self.vector_store.metadata:
            embedding = self.embedder.encode_single(f"{meta['title']}. {meta['description']}")
            self._link_new_ticket_similarity(meta["id"], embedding)

    def ingest_ticket(self, ticket: Dict) -> str:
        """Adds a single new ticket (e.g. after resolution) to the live index."""
        full_text = f"{ticket['title']}. {ticket['description']}"
        tokens = self.preprocessor.tokenize_and_lemmatize(full_text)
        return self._ingest_single(ticket, tokens, link_similarity=True)

    # -----------------------------------------------------------------
    # Retrieval
    # -----------------------------------------------------------------
    def retrieve_similar(self, title: str, description: str, k: int = settings.TOP_K_RETRIEVAL) -> List[Tuple[Dict, float]]:
        full_text = f"{title}. {description}"
        query_embedding = self.embedder.encode_single(full_text)
        return self.vector_store.search(query_embedding, k=k)

    # -----------------------------------------------------------------
    # Classification (k-NN vote over retrieved neighbors)
    # -----------------------------------------------------------------
    def classify(self, title: str, description: str, retrieved: List[Tuple[Dict, float]]) -> Dict:
        full_text = f"{title}. {description}"
        tokens = self.preprocessor.tokenize_and_lemmatize(full_text)
        dominant_topics = self.topic_modeler.get_dominant_topics(tokens) if self.topic_modeler.is_trained else []

        if not retrieved:
            return {
                "predicted_category": "General Inquiry",
                "predicted_priority": "Medium",
                "category_confidence": 0.0,
                "priority_confidence": 0.0,
                "dominant_topics": dominant_topics,
            }

        category_votes, priority_votes = Counter(), Counter()
        for meta, score in retrieved:
            if meta.get("category"):
                category_votes[meta["category"]] += score
            if meta.get("priority"):
                priority_votes[meta["priority"]] += score

        total_cat_weight = sum(category_votes.values()) or 1.0
        total_pri_weight = sum(priority_votes.values()) or 1.0

        top_category, cat_weight = (category_votes.most_common(1) or [("General Inquiry", 0)])[0]
        top_priority, pri_weight = (priority_votes.most_common(1) or [("Medium", 0)])[0]

        return {
            "predicted_category": top_category,
            "predicted_priority": top_priority,
            "category_confidence": round(cat_weight / total_cat_weight, 4),
            "priority_confidence": round(pri_weight / total_pri_weight, 4),
            "dominant_topics": dominant_topics,
        }

    # -----------------------------------------------------------------
    # Graph-context expansion
    # -----------------------------------------------------------------
    def expand_context_via_graph(self, retrieved: List[Tuple[Dict, float]]) -> List[Dict]:
        related_ids, seen = [], {meta["id"] for meta, _ in retrieved}
        for meta, _ in retrieved:
            for related in self.knowledge_graph.get_related_tickets(meta["id"]):
                if related["id"] not in seen:
                    seen.add(related["id"])
                    related_ids.append(related)
        related_ids.sort(key=lambda x: x["relevance"], reverse=True)
        return related_ids[:5]

    # -----------------------------------------------------------------
    # Recommendation generation (extractive/template synthesis)
    # -----------------------------------------------------------------
    def generate_recommendation(self, title: str, description: str) -> Dict:
        retrieved = self.retrieve_similar(title, description)
        classification = self.classify(title, description, retrieved)
        graph_related = self.expand_context_via_graph(retrieved)

        reasoning = []
        if retrieved:
            reasoning.append(
                f"Retrieved {len(retrieved)} semantically similar historical tickets "
                f"(top similarity: {retrieved[0][1]:.2f})."
            )
        else:
            reasoning.append("No sufficiently similar historical tickets found in the vector store.")

        if graph_related:
            reasoning.append(
                f"Knowledge graph expanded context with {len(graph_related)} additional "
                f"related tickets via category/tag/topic links."
            )

        if classification["dominant_topics"]:
            reasoning.append(f"Dominant LSI topics detected: {', '.join(classification['dominant_topics'])}.")

        recommendation, confidence = self._synthesize_resolution(retrieved)
        reasoning.append(
            f"Synthesized recommendation from {min(len(retrieved), 3)} highest-similarity resolutions."
        )

        return {
            "classification": classification,
            "similar_tickets": [
                {**meta, "similarity_score": round(score, 4)} for meta, score in retrieved
            ],
            "graph_related_ticket_ids": [r["id"] for r in graph_related],
            "recommended_resolution": recommendation,
            "recommendation_confidence": confidence,
            "reasoning": reasoning,
        }

    def _synthesize_resolution(self, retrieved: List[Tuple[Dict, float]]) -> Tuple[str, float]:
        """
        Extractive synthesis: takes resolutions from the highest-similarity
        matches above threshold and combines them into a single recommendation.
        This is the 'G' in RAG done without an external LLM call so the
        service has zero external dependencies at inference time.
        """
        strong_matches = [(m, s) for m, s in retrieved if s >= settings.SIMILARITY_THRESHOLD and m.get("resolution")]

        if not strong_matches:
            return (
                "No high-confidence historical match found. Recommend routing to a human "
                "agent for manual triage; consider tagging as a novel issue category.",
                0.0,
            )

        if len(strong_matches) == 1:
            meta, score = strong_matches[0]
            return (
                f"Based on a highly similar prior ticket (\"{meta['title']}\"): {meta['resolution']}",
                round(score, 4),
            )

        top = strong_matches[:3]
        lines = [f"- (from \"{m['title']}\", similarity {s:.2f}): {m['resolution']}" for m, s in top]
        avg_conf = sum(s for _, s in top) / len(top)
        combined = (
            "Multiple similar historical tickets suggest the following combined resolution path:\n"
            + "\n".join(lines)
        )
        return combined, round(avg_conf, 4)

    # -----------------------------------------------------------------
    # Optional: abstractive generation via the Anthropic API
    # -----------------------------------------------------------------
    def generate_with_llm_prompt(self, title: str, description: str, retrieved: List[Tuple[Dict, float]]) -> str:
        """
        Builds a grounded prompt suitable for passing to an LLM (e.g. the
        Anthropic Messages API) for abstractive recommendation generation.
        Returning the prompt string (rather than calling out) keeps this
        module dependency-free; wire it up to your model client of choice.
        """
        context_blocks = "\n\n".join(
            f"Historical Ticket: {m['title']}\nResolution: {m.get('resolution', 'N/A')}\nSimilarity: {s:.2f}"
            for m, s in retrieved
        )
        prompt = (
            "You are a support engineer assistant. Given a new ticket and similar "
            "historical tickets with their resolutions, recommend a concise, actionable "
            "resolution grounded ONLY in the provided context.\n\n"
            f"New Ticket:\nTitle: {title}\nDescription: {description}\n\n"
            f"Historical Context:\n{context_blocks}\n\n"
            "Recommended Resolution:"
        )
        return prompt
