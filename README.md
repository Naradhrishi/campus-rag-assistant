# Campus RAG Assistant

One app, two modes, same UI:

- **My Documents** — students upload their own PDF/DOCX/TXT files and ask questions about them (private per browser/session).
- **University Regulations** — a shared, admin-preloaded knowledge base (e.g. the official regulations handbook) that every user can query, no upload needed.

Both modes use the same retrieval pipeline and the same Groq-powered LLM for answering; they just point at different document collections.

## How it works

- **Embeddings**: local `sentence-transformers` model (`all-MiniLM-L6-v2`) — free, runs on your machine, no API cost, downloaded once from HuggingFace on first run.
- **Vector store**: `chromadb`, persisted to disk in `backend/chroma_store/`.
- **LLM**: Groq's chat completion API (`llama-3.3-70b-versatile` by default — check https://console.groq.com/docs/models for the current list, Groq renames/retires models fairly often).
- **Personal vs. university separation**: personal docs are tagged with a `session_id` (a random ID generated once in the browser and stored in `localStorage`) so uploads stay private to that browser. University docs live in one shared collection with no session tag.

## 1. Backend setup

This project uses **[uv](https://docs.astral.sh/uv/)** instead of pip/venv. `uv` is a single small executable — no separate Python install needed, it manages Python versions itself.

**Install uv** (one-time, if you don't have it):

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Set up the project:**

```bash
cd backend
uv sync
```

That's it — `uv sync` reads `pyproject.toml` + `.python-version` (pinned to 3.12 here), automatically **downloads Python 3.12 if you don't already have it** (your system Python, e.g. 3.14, is untouched), creates a `.venv`, and installs all dependencies. This sidesteps the issue where `torch`/`onnxruntime` (used by `sentence-transformers`/`chromadb`) don't yet ship prebuilt wheels for very new Python versions like 3.14.

```bash
cp .env.example .env
# then edit .env and paste your GROQ_API_KEY (get one free at https://console.groq.com)
```

> Prefer plain pip? `requirements.txt` is still included — `python -m venv .venv` (with a 3.11/3.12 interpreter) then `pip install -r requirements.txt` works the same way. `uv` is just faster and handles the Python version for you.

### Load the university regulations (one-time, or whenever they change)

Drop your regulation files into `backend/university_docs/` (PDF, DOCX, or TXT — you can add several), then:

```bash
uv run ingest_university_docs.py
```

This embeds them into the shared collection that "University Regulations" mode queries. Re-run it any time you add new files.

### Run the API

```bash
uv run uvicorn main:app --reload --port 8000
```

(`uv run` automatically uses the `.venv` uv created — no need to manually activate it. If you'd rather activate it the normal way: `.venv\Scripts\activate` on Windows, then just `uvicorn main:app --reload --port 8000`.)

The API is now live at `http://localhost:8000`. Visit `http://localhost:8000/health` to sanity-check it's up.

## 2. Frontend setup

The frontend is static (no build step). Easiest option:

```bash
cd frontend
python -m http.server 5500
```

Then open `http://localhost:5500` in your browser.

> If you serve the frontend from a different host/port than `localhost:5500` in production, update the `API` constant at the top of `script.js` to point at your deployed backend URL.

## 3. Using it

- **My Documents** tab: click the upload icon, pick a PDF/DOCX/TXT, wait for the "embedded successfully" message, then ask questions about it in the chat box.
- **University Regulations** tab: no upload needed — just ask a question. It answers only from whatever was ingested via `ingest_university_docs.py`.
- Switching tabs keeps each mode's chat history separate, and the interface is responsive — on phones, the documents panel becomes a slide-out drawer (tap the ☰ icon in the header).

## Notes / next steps you might want

- **Auth**: right now "sessions" are just a random ID in `localStorage` — good enough for a class project, not real user accounts. Add real auth if multiple people will share one browser or you want persistence across devices.
- **File size limits**: none enforced yet — add a max upload size check in `/upload` if needed.
- **Deleting personal docs**: there's a `DELETE /session/{session_id}` endpoint to wipe a user's uploads; you could wire a "Clear my documents" button to it.
- **Production CORS**: `main.py` currently allows all origins (`allow_origins=["*"]`) for easy local dev — restrict this to your actual frontend domain before deploying.
