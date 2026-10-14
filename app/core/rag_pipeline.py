"""
Custom RAG (Retrieval-Augmented Generation) pipeline for ticket triage.

Flow for an incoming ticket:
  1. Preprocess text (spaCy/NLTK) and compute LSI topic vector (Gensim).
  2. Embed text with Sentence Transformers.
  3. Retrieve top-k semantically similar historical tickets via FAISS.
  4. Expand context using the NetworkX knowledge graph (category/tag/topic
     neighbors + graph-derived relevance signals).
  5. Classify category & priority via k-NN vote over retrieved neighbors.
  6. If no strong match in ticket history (or if runtime stacktrace exists),
     connect to the application's Git repository and analyze the source code.
  7. Generate a grounded recommendation by synthesizing the retrieved
     resolutions or code-level bugfix patch.
"""
import logging
import uuid
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.core.code_analyzer import GitCodeAnalyzer
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
        self.code_analyzer = GitCodeAnalyzer()
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
            "application_name": ticket.get("application_name"),
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
                "predicted_category": "Technical Issue",
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

        top_category, cat_weight = (category_votes.most_common(1) or [("Technical Issue", 0)])[0]
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
    # Recommendation generation (with Git Codebase fallback)
    # -----------------------------------------------------------------
    def generate_recommendation(
        self,
        title: str,
        description: str,
        application_name: Optional[str] = None,
    ) -> Dict:
        retrieved = self.retrieve_similar(title, description)
        classification = self.classify(title, description, retrieved)
        graph_related = self.expand_context_via_graph(retrieved)

        reasoning = []
        top_similarity = retrieved[0][1] if retrieved else 0.0

        if retrieved and top_similarity >= settings.SIMILARITY_THRESHOLD:
            reasoning.append(
                f"Retrieved {len(retrieved)} semantically similar historical tickets "
                f"(top similarity: {top_similarity:.2f})."
            )
        else:
            reasoning.append(
                f"No high-similarity ticket found in historical index (top score: {top_similarity:.2f} < {settings.SIMILARITY_THRESHOLD})."
            )

        if graph_related:
            reasoning.append(
                f"Knowledge graph expanded context with {len(graph_related)} additional related tickets."
            )

        if classification["dominant_topics"]:
            reasoning.append(f"Dominant LSI topics detected: {', '.join(classification['dominant_topics'])}.")

        # Check if historical resolution is available
        strong_matches = [(m, s) for m, s in retrieved if s >= settings.SIMILARITY_THRESHOLD and m.get("resolution")]

        code_analysis_res = None
        source_channel = "Historical Ticket RAG"

        # Check for stacktrace or fallback to Git Code Analysis when ticket history is insufficient
        has_stacktrace = bool(
            "Traceback" in description
            or "line " in description
            or "Exception" in description
            or "Error:" in description
            or "at " in description
        )

        if (not strong_matches or has_stacktrace):
            logger.info("Attempting Git codebase & stacktrace inspection...")
            code_analysis_res = self.code_analyzer.analyze_ticket_code(
                application_name=application_name,
                title=title,
                description=description,
            )

        if code_analysis_res:
            source_channel = f"Git Codebase Analysis ({code_analysis_res['application_name']})"
            reasoning.append(
                f"Connected to Git repo for '{code_analysis_res['application_name']}' "
                f"({code_analysis_res.get('repo_url')})."
            )
            reasoning.append(
                f"Parsed runtime stacktrace: {code_analysis_res['error_type']} at "
                f"{code_analysis_res['file_path']}:{code_analysis_res['line_number']}."
            )
            reasoning.append("Analyzed source code AST and synthesized code-level patch.")

            # Formulate code-level recommendation
            recommendation = (
                f"⚠️ [Git Code Analysis - {code_analysis_res['application_name']}]\n"
                f"File: {code_analysis_res['file_path']}:{code_analysis_res['line_number']} (Function: {code_analysis_res['function_name']})\n\n"
                f"📌 Root Cause:\n{code_analysis_res['root_cause']}\n\n"
                f"🛠️ Suggested Code Fix:\n{code_analysis_res['suggested_fix']}"
            )
            confidence = 0.94

            # Refine classification if ticket history was weak
            if not strong_matches:
                classification["predicted_category"] = "Bug Report"
                classification["predicted_priority"] = "High" if "Error" in code_analysis_res["error_type"] else "Medium"
                classification["category_confidence"] = 0.95
                classification["priority_confidence"] = 0.90
        else:
            recommendation, confidence = self._synthesize_resolution(retrieved)
            reasoning.append(
                f"Synthesized recommendation from {min(len(retrieved), 3)} highest-similarity resolutions."
            )

        return {
            "application_name": application_name or (code_analysis_res["application_name"] if code_analysis_res else None),
            "classification": classification,
            "similar_tickets": [
                {**meta, "similarity_score": round(score, 4)} for meta, score in retrieved
            ],
            "graph_related_ticket_ids": [r["id"] for r in graph_related],
            "recommended_resolution": recommendation,
            "recommendation_confidence": confidence,
            "code_analysis": code_analysis_res,
            "source_channel": source_channel,
            "reasoning": reasoning,
        }

    def _synthesize_resolution(self, retrieved: List[Tuple[Dict, float]]) -> Tuple[str, float]:
        """
        Extractive synthesis: takes resolutions from the highest-similarity
        matches above threshold and combines them into a single recommendation.
        """
        strong_matches = [(m, s) for m, s in retrieved if s >= settings.SIMILARITY_THRESHOLD and m.get("resolution")]

        if not strong_matches:
            return (
                "No high-confidence historical match found in the vector database and no runtime stacktrace "
                "detected. Recommend routing to support engineers for manual triage.",
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
