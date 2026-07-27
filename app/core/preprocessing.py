"""
NLP preprocessing layer.

Responsibilities:
  1. TextPreprocessor  - cleans raw ticket text using spaCy + NLTK
                         (tokenization, stop-word removal, lemmatization).
  2. TopicModeler       - builds a TF-IDF representation and an LSI
                         (Latent Semantic Indexing) topic model via Gensim,
                         used to extract dominant topics for a ticket and
                         to enrich the knowledge graph with topical edges.
"""
import re
import logging
from typing import List, Tuple

import nltk
import spacy
from gensim import corpora, models
from gensim.matutils import sparse2full

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# One-time resource bootstrap (safe to call repeatedly; NLTK/spacy no-op if
# resources already exist).
# ---------------------------------------------------------------------------
def ensure_nltk_resources() -> None:
    resources = ["punkt", "punkt_tab", "stopwords", "wordnet", "omw-1.4"]
    for res in resources:
        nltk.download(res, quiet=True)


class TextPreprocessor:
    """
    Cleans and normalizes raw ticket text.

    Pipeline: lowercase -> regex clean -> spaCy tokenization/lemmatization
    -> NLTK stop-word removal -> optional NER-based entity tagging.
    """

    def __init__(self, spacy_model_name: str = settings.SPACY_MODEL_NAME):
        ensure_nltk_resources()
        from nltk.corpus import stopwords

        self.stopwords = set(stopwords.words("english"))

        try:
            self.nlp = spacy.load(spacy_model_name, disable=["parser", "ner"])
        except OSError:
            logger.warning(
                f"spaCy model '{spacy_model_name}' not found locally; "
                "attempting blank English pipeline with a rule-based tokenizer. "
                f"Run `python -m spacy download {spacy_model_name}` for full lemmatization."
            )
            self.nlp = spacy.blank("en")

        # Separate pipeline instance with NER enabled for entity extraction
        try:
            self.nlp_ner = spacy.load(spacy_model_name, disable=["parser"])
        except OSError:
            self.nlp_ner = self.nlp

    @staticmethod
    def clean_text(text: str) -> str:
        """Lowercase, strip URLs/emails/special chars, collapse whitespace."""
        text = text.lower()
        text = re.sub(r"http\S+|www\.\S+", " ", text)
        text = re.sub(r"\S+@\S+", " ", text)
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def tokenize_and_lemmatize(self, text: str) -> List[str]:
        """
        Tokenizes via spaCy, removes stop-words/punctuation/whitespace tokens,
        and lemmatizes each remaining token.
        """
        cleaned = self.clean_text(text)
        doc = self.nlp(cleaned)
        tokens = []
        for tok in doc:
            if tok.is_space or tok.is_punct:
                continue
            lemma = tok.lemma_.strip() if tok.lemma_ != "-PRON-" else tok.text
            if not lemma or lemma in self.stopwords or len(lemma) < 2:
                continue
            tokens.append(lemma)
        return tokens

    def preprocess(self, text: str) -> str:
        """Returns a cleaned, lemmatized, stop-word-free string."""
        return " ".join(self.tokenize_and_lemmatize(text))

    def extract_entities(self, text: str) -> List[Tuple[str, str]]:
        """Returns (entity_text, entity_label) pairs — useful for KG enrichment."""
        doc = self.nlp_ner(text)
        return [(ent.text, ent.label_) for ent in getattr(doc, "ents", [])]


class TopicModeler:
    """
    Builds TF-IDF + LSI (Latent Semantic Indexing) models over a corpus of
    historical tickets using Gensim. Used to:
      - extract a compact topic-vector representation of any ticket
      - surface human-readable dominant topics for explainability
    """

    def __init__(self, num_topics: int = settings.LSI_NUM_TOPICS):
        self.num_topics = num_topics
        self.dictionary: corpora.Dictionary = None
        self.tfidf_model: models.TfidfModel = None
        self.lsi_model: models.LsiModel = None
        self.is_trained = False

    def fit(self, tokenized_docs: List[List[str]]) -> None:
        """Train dictionary, TF-IDF, and LSI models on the historical corpus."""
        if not tokenized_docs:
            logger.warning("TopicModeler.fit called with empty corpus; skipping.")
            return

        self.dictionary = corpora.Dictionary(tokenized_docs)
        self.dictionary.filter_extremes(no_below=settings.TFIDF_MIN_DF, no_above=0.9)

        bow_corpus = [self.dictionary.doc2bow(doc) for doc in tokenized_docs]
        self.tfidf_model = models.TfidfModel(bow_corpus)
        tfidf_corpus = self.tfidf_model[bow_corpus]

        effective_topics = min(self.num_topics, max(2, len(tokenized_docs) - 1))
        self.lsi_model = models.LsiModel(
            tfidf_corpus, id2word=self.dictionary, num_topics=effective_topics
        )
        self.is_trained = True
        logger.info(
            f"TopicModeler trained on {len(tokenized_docs)} docs, "
            f"{len(self.dictionary)} vocab terms, {effective_topics} LSI topics."
        )

    def get_topic_vector(self, tokens: List[str]) -> List[float]:
        """Returns the dense LSI topic vector for a tokenized document."""
        if not self.is_trained:
            return []
        bow = self.dictionary.doc2bow(tokens)
        tfidf_vec = self.tfidf_model[bow]
        lsi_vec = self.lsi_model[tfidf_vec]
        return sparse2full(lsi_vec, self.num_topics).tolist()

    def get_dominant_topics(self, tokens: List[str], top_n: int = 3) -> List[str]:
        """
        Returns human-readable labels for the top-n LSI topics a document
        loads most heavily on, expressed as their strongest constituent terms.
        """
        if not self.is_trained:
            return []
        bow = self.dictionary.doc2bow(tokens)
        tfidf_vec = self.tfidf_model[bow]
        lsi_vec = self.lsi_model[tfidf_vec]
        if not lsi_vec:
            return []

        ranked = sorted(lsi_vec, key=lambda x: abs(x[1]), reverse=True)[:top_n]
        labels = []
        for topic_id, _weight in ranked:
            terms = self.lsi_model.show_topic(topic_id, topn=4)
            label = " / ".join(term for term, _ in terms)
            labels.append(label)
        return labels
