# Intelligent Ticket Triage & Recommendation System

An NLP-powered support-ticket triage platform combining semantic search,
topic modeling, a knowledge graph, and a custom Retrieval-Augmented
Generation (RAG) pipeline to classify incoming tickets and recommend
resolutions grounded in historical ticket data.

## Architecture

```
                        ┌────────────────────┐
                        │   FastAPI Layer     │  app/main.py, app/api/routes.py
                        │  (REST endpoints)   │
                        └─────────┬───────────┘
                                  │
                        ┌─────────▼───────────┐
                        │   RAG Pipeline       │  app/core/rag_pipeline.py
                        │ (orchestration)      │
                        └──┬───────┬───────┬───┘
             ┌─────────────┘       │       └─────────────┐
             ▼                    ▼                       ▼
   ┌──────────────────┐ ┌──────────────────┐   ┌───────────────────────┐
   │  Preprocessing    │ │   Embeddings +    │   │   Knowledge Graph      │
   │  spaCy / NLTK     │ │  FAISS Vector      │   │   (NetworkX)           │
   │  TF-IDF / LSI     │ │  Store             │   │  category/tag/topic/   │
   │  (Gensim)         │ │ (Sentence          │   │  similarity edges      │
   │                   │ │  Transformers)      │   │                        │
   └──────────────────┘ └──────────────────┘   └───────────────────────┘
```

### Pipeline flow (per incoming ticket)

1. **Preprocess** (`app/core/preprocessing.py`) — clean text, tokenize and
   lemmatize with spaCy, strip stop-words via NLTK, and derive a Gensim
   TF-IDF → LSI topic vector plus human-readable dominant topics.
2. **Embed** (`app/core/embeddings.py`) — encode the ticket with a Sentence
   Transformer (`all-MiniLM-L6-v2` by default) into a normalized dense vector.
3. **Retrieve** (`app/core/vector_store.py`) — run cosine-equivalent
   nearest-neighbor search over historical ticket embeddings using a FAISS
   `IndexFlatIP`.
4. **Expand context** (`app/core/knowledge_graph.py`) — walk the NetworkX
   knowledge graph from the retrieved tickets to surface additional
   contextually related tickets (shared category, tags, topics, or prior
   similarity links) that pure vector search might miss.
5. **Classify** — a similarity-weighted k-NN vote over retrieved neighbors'
   category/priority labels.
6. **Generate** (`app/core/rag_pipeline.py::_synthesize_resolution`) —
   synthesize a grounded recommendation from the retrieved resolutions.
   This is extractive/template-based by default (zero external
   dependencies at inference time); `generate_with_llm_prompt(...)` builds
   a ready-to-send prompt if you want to swap in an LLM call (e.g. the
   Anthropic Messages API) for abstractive generation.

## Project layout

```
ticket_triage_system/
├── app/
│   ├── main.py                 # FastAPI app + startup lifecycle
│   ├── config.py                # Central settings
│   ├── models/schemas.py        # Pydantic request/response models
│   ├── api/routes.py            # REST endpoints
│   ├── core/
│   │   ├── preprocessing.py     # spaCy/NLTK cleaning + Gensim TF-IDF/LSI
│   │   ├── embeddings.py        # Sentence Transformer wrapper
│   │   ├── vector_store.py      # FAISS similarity search
│   │   ├── knowledge_graph.py   # NetworkX ticket relationship graph
│   │   └── rag_pipeline.py      # Orchestrates retrieval + recommendation
│   └── data/sample_tickets.json # Seed historical ticket dataset (20 tickets)
├── scripts/demo.py              # CLI smoke-test of the pipeline
├── requirements.txt
└── README.md
```

## Setup (Windows)

> **Note:** These instructions are tailored for **Windows (PowerShell/CMD)**.  
> If using Linux/macOS, replace `venv\Scripts\activate` with `source venv/bin/activate`.

### Prerequisites

- **Python 3.10+** installed ([python.org](https://www.python.org/downloads/))
- **Git** (optional, for cloning)

### 1. Navigate to the project directory

```bash
cd C:\Users\0010ZL744\Downloads\ticket_triage_system\ticket_triage_system
```

### 2. Create and activate a virtual environment

```powershell
python -m venv venv
venv\Scripts\activate
```

> You should see `(venv)` appear at the beginning of your terminal prompt.

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

> ⏳ This may take **10–20 minutes** on a typical internet connection as it downloads large packages including **PyTorch (~160 MB)** and **Intel MKL (~228 MB)**.  
> If `gensim` fails to build from source (requires Visual C++ Build Tools), try installing a pre-compiled binary wheel instead:
> ```powershell
> pip install gensim --only-binary :all:
> ```

### 4. Download NLP models (one-time setup)

```powershell
python -m spacy download en_core_web_sm
python -m nltk.downloader punkt punkt_tab stopwords wordnet omw-1.4
```

### 5. Verify installation

```powershell
python -c "import fastapi, uvicorn, spacy, nltk, sentence_transformers, faiss, torch, networkx, gensim; print('All packages installed successfully')"
```

---

## Running the Project

### Option A — Web GUI & FastAPI Server (Recommended)

Start the server:

```powershell
uvicorn app.main:app --reload --port 8000
```

Open your browser and navigate to:

| Interface | URL | Description |
|-----------|-----|-------------|
| **Support Team GUI Dashboard** | [http://localhost:8000/](http://localhost:8000/) | Full interactive Web UI for Single Ticket Triage & Batch CSV Processing |
| **Swagger UI (Interactive API)** | [http://localhost:8000/docs](http://localhost:8000/docs) | Test REST endpoints directly |
| **ReDoc** | [http://localhost:8000/redoc](http://localhost:8000/redoc) | Detailed OpenAPI documentation |

#### 🖥️ GUI Features for Support Teams:
- **Single Ticket Triage**: Enter ticket number, title, and issue details (or use quick-test presets) to get instant category/priority predictions, matching confidence, dominant topics, grounded AI resolution suggestions, top similar historical tickets, and step-by-step reasoning trace.
- **Batch CSV Processing**: Upload CSV files containing multiple tickets (`ticket_number`, `title`, `issue_details`), process them all in parallel/bulk, view aggregated metrics, filter by category/priority, expand individual triage details, and export all recommendations back to CSV with 1 click.
- **Knowledge Base Explorer**: Search through all indexed historical tickets and ingest newly resolved tickets directly into the live FAISS vector store and Knowledge Graph.

The Swagger UI lets you test all endpoints directly from the browser with a "Try it out" button.

#### Stopping the Server

Press **`Ctrl + C`** in the terminal where the server is running. You should see:

```
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-07-27 11:43:11,162 | INFO | app.main | Shutting down: persisting index and graph state...
2026-07-27 11:43:11,168 | INFO | app.core.vector_store | Saved FAISS index (20 vectors) to ...\storage\tickets.index
2026-07-27 11:43:11,177 | INFO | app.core.knowledge_graph | Saved knowledge graph (20 nodes) to ...\storage\knowledge_graph.gpickle
INFO:     Application shutdown complete.
```

> The FAISS index and knowledge graph are automatically persisted to the `storage/` directory on shutdown, so the next startup will be faster.

#### Quick API Test

Open a **new terminal** (while the server is running) and run:

```powershell
python -c "
import urllib.request, json

# Health check
r = urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')
print('Health:', json.loads(r.read()))

# Classify a ticket
body = json.dumps({'title': 'Can\\'t log in', 'description': 'Invalid credentials after password reset.'}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/api/v1/tickets/classify', data=body, headers={'Content-Type': 'application/json'})
r = urllib.request.urlopen(req)
print('Classify:', json.dumps(json.loads(r.read()), indent=2))
"
```

### Option B — CLI Demo (no web server needed)

```powershell
python scripts/demo.py
```

This runs a standalone smoke-test of the entire RAG pipeline from the command line without starting the HTTP server.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `'pip' is not recognized` | Make sure Python is added to your PATH, or use `python -m pip` instead of `pip` |
| `Unable to find vcvarsall.bat` / `Microsoft Visual C++ 14.0` required | Try `pip install gensim --only-binary :all:` to use a pre-compiled wheel |
| `No module named 'fastapi'` | Ensure the virtual environment is activated (`venv\Scripts\activate`) |
| `nltk.data.find` error | The startup code automatically downloads missing NLTK data; or manually run `python -m nltk.downloader punkt punkt_tab stopwords wordnet omw-1.4` |
| `Address already in use` (port 8000) | Change the port: `uvicorn app.main:app --reload --port 8001` |
| Slow first startup | The Sentence Transformer model needs to download once (~90 MB). Subsequent starts are faster. |
| HuggingFace symlink warning on Windows | This is harmless. To fix, enable **Developer Mode** in Windows Settings. |

## API Reference

### `GET /api/v1/health`
Returns pipeline readiness and current index sizes.

### `POST /api/v1/tickets/classify`
```json
{
  "title": "Can't log in after resetting my password",
  "description": "I reset my password but the site still says invalid credentials."
}
```
→ Returns predicted category, priority, confidences, and dominant topics.

### `POST /api/v1/tickets/recommend`
Same request body as above. Returns full RAG output: classification,
similar historical tickets (with similarity scores), knowledge-graph
related ticket IDs, a synthesized recommended resolution, a confidence
score, and a human-readable reasoning trace.

### `POST /api/v1/tickets/ingest`
```json
{
  "title": "New ticket title",
  "description": "New ticket description",
  "category": "Billing",
  "priority": "Medium",
  "resolution": "How it was resolved",
  "tags": ["billing", "refund"]
}
```
Adds a new (typically resolved) ticket to the live FAISS index and
knowledge graph so future queries benefit from it.

### `GET /api/v1/tickets/similar/{ticket_id}`
Returns the nearest historical neighbors for an existing ticket by ID.

### `GET /api/v1/knowledge-graph/related/{ticket_id}`
Returns graph-neighborhood related tickets and a degree-centrality score
for the given ticket ID.

## Design notes

- **Why FAISS `IndexFlatIP` over normalized vectors?** It's exact cosine
  similarity search, no approximation error, and fast enough for
  ticket-history corpora up to the low millions. Swap in `IndexIVFFlat` or
  HNSW if you outgrow that.
- **Why LSI via Gensim in addition to embeddings?** LSI/TF-IDF gives cheap,
  interpretable topic labels ("dominant topics") for explainability in the
  UI/reasoning trace, complementing the semantic-but-opaque dense embeddings.
- **Why a knowledge graph on top of vector search?** Vector similarity
  alone can miss tickets that are contextually related but phrased very
  differently (e.g. same category + shared tags but low text overlap). The
  graph captures those relationships explicitly and lets you reason about
  ticket clusters, not just nearest neighbors.
- **Why extractive generation instead of calling an LLM?** Keeps the
  service self-contained and deterministic for this reference
  implementation. `TicketRAGPipeline.generate_with_llm_prompt(...)`
  shows exactly how to swap in an LLM call for abstractive synthesis
  without changing any other component.
