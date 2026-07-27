"""
Ticket Knowledge Graph built with NetworkX.

Models tickets as nodes and connects them via typed, weighted edges:
  - SAME_CATEGORY  : tickets sharing a category
  - SHARED_TAG     : tickets sharing one or more tags
  - SHARED_TOPIC    : tickets whose dominant LSI topics overlap
  - SIMILAR_TO      : tickets above the embedding-similarity threshold
                      (populated by the RAG pipeline after vector search)

This lets the recommendation engine reason beyond pure vector similarity —
e.g. surfacing a ticket that's topically/categorically related even if its
raw text embedding wasn't in the top-k nearest neighbors.
"""
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Set

import networkx as nx

from app.config import settings

logger = logging.getLogger(__name__)


class TicketKnowledgeGraph:
    def __init__(self):
        self.graph = nx.Graph()

    # -- node / edge construction -------------------------------------------------
    def add_ticket(
        self,
        ticket_id: str,
        title: str,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
    ) -> None:
        self.graph.add_node(
            ticket_id,
            title=title,
            category=category,
            priority=priority,
            tags=tags or [],
            topics=topics or [],
        )
        self._link_by_category(ticket_id, category)
        self._link_by_tags(ticket_id, tags or [])
        self._link_by_topics(ticket_id, topics or [])

    def add_similarity_edge(self, ticket_id_a: str, ticket_id_b: str, score: float) -> None:
        """Adds/reinforces a SIMILAR_TO edge discovered via vector search."""
        if ticket_id_a == ticket_id_b:
            return
        if self.graph.has_edge(ticket_id_a, ticket_id_b):
            self.graph[ticket_id_a][ticket_id_b]["weight"] = max(
                self.graph[ticket_id_a][ticket_id_b].get("weight", 0), score
            )
        else:
            self.graph.add_edge(ticket_id_a, ticket_id_b, relation="SIMILAR_TO", weight=score)

    def _link_by_category(self, ticket_id: str, category: Optional[str]) -> None:
        if not category:
            return
        for node_id, data in self.graph.nodes(data=True):
            if node_id != ticket_id and data.get("category") == category:
                self._add_or_strengthen_edge(ticket_id, node_id, "SAME_CATEGORY", weight=0.3)

    def _link_by_tags(self, ticket_id: str, tags: List[str]) -> None:
        if not tags:
            return
        tag_set = set(tags)
        for node_id, data in self.graph.nodes(data=True):
            if node_id == ticket_id:
                continue
            overlap = tag_set.intersection(set(data.get("tags", [])))
            if overlap:
                weight = 0.2 * len(overlap)
                self._add_or_strengthen_edge(ticket_id, node_id, "SHARED_TAG", weight=weight)

    def _link_by_topics(self, ticket_id: str, topics: List[str]) -> None:
        if not topics:
            return
        topic_set = set(topics)
        for node_id, data in self.graph.nodes(data=True):
            if node_id == ticket_id:
                continue
            overlap = topic_set.intersection(set(data.get("topics", [])))
            if overlap:
                weight = 0.25 * len(overlap)
                self._add_or_strengthen_edge(ticket_id, node_id, "SHARED_TOPIC", weight=weight)

    def _add_or_strengthen_edge(self, a: str, b: str, relation: str, weight: float) -> None:
        if self.graph.has_edge(a, b):
            self.graph[a][b]["weight"] = self.graph[a][b].get("weight", 0) + weight
        else:
            self.graph.add_edge(a, b, relation=relation, weight=weight)

    # -- querying -------------------------------------------------------------
    def get_related_tickets(self, ticket_id: str, depth: int = settings.KG_EXPANSION_DEPTH, top_n: int = 5) -> List[Dict]:
        """
        Returns tickets within `depth` hops of ticket_id, ranked by aggregate
        edge weight (a proxy for contextual relevance).
        """
        if ticket_id not in self.graph:
            return []

        subgraph_nodes: Set[str] = {ticket_id}
        frontier = {ticket_id}
        for _ in range(depth):
            next_frontier = set()
            for node in frontier:
                next_frontier.update(self.graph.neighbors(node))
            subgraph_nodes.update(next_frontier)
            frontier = next_frontier
        subgraph_nodes.discard(ticket_id)

        scored = []
        for node in subgraph_nodes:
            if self.graph.has_edge(ticket_id, node):
                weight = self.graph[ticket_id][node].get("weight", 0)
            else:
                # multi-hop node: approximate relevance via shortest path weight sum
                try:
                    path = nx.shortest_path(self.graph, ticket_id, node)
                    weight = sum(
                        self.graph[path[i]][path[i + 1]].get("weight", 0)
                        for i in range(len(path) - 1)
                    ) / max(1, len(path) - 1)
                except nx.NetworkXNoPath:
                    weight = 0.0
            data = self.graph.nodes[node]
            scored.append(
                {
                    "id": node,
                    "title": data.get("title"),
                    "category": data.get("category"),
                    "priority": data.get("priority"),
                    "relevance": round(weight, 4),
                }
            )

        scored.sort(key=lambda x: x["relevance"], reverse=True)
        return scored[:top_n]

    def centrality_score(self, ticket_id: str) -> float:
        """
        Degree centrality as a cheap proxy for how 'canonical' or central a
        historical ticket/resolution is within its neighborhood — central
        tickets are often good candidates for a stable recommendation.
        """
        if ticket_id not in self.graph or self.graph.number_of_nodes() < 2:
            return 0.0
        centrality = nx.degree_centrality(self.graph)
        return round(centrality.get(ticket_id, 0.0), 4)

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    # -- persistence ------------------------------------------------------------
    def save(self, path: Path = settings.KG_STORAGE_PATH) -> None:
        with open(path, "wb") as f:
            pickle.dump(self.graph, f)
        logger.info(f"Saved knowledge graph ({self.node_count()} nodes) to {path}")

    def load(self, path: Path = settings.KG_STORAGE_PATH) -> bool:
        if not path.exists():
            return False
        with open(path, "rb") as f:
            self.graph = pickle.load(f)
        logger.info(f"Loaded knowledge graph with {self.node_count()} nodes from {path}")
        return True
