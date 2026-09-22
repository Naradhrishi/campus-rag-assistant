import os
import shutil
import tempfile
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
import rag_engine as rag
from contextlib import asynccontextmanager

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set.")

groq_client = Groq(api_key=GROQ_API_KEY)

@asynccontextmanager
async def lifespan(app):
    print("=== Lifespan: checking university docs ===")
    try:
        col = rag.get_collection(rag.UNIVERSITY_COLLECTION)
        count = col.count()
        print(f"University collection count: {count}")
        if count == 0:
            print("Empty -> ingesting from university_docs/")
            import ingest_university_docs
            ingest_university_docs.ingest()
            print(f"After ingest count: {col.count()}")
    except Exception as e:
        print(f"Lifespan ingest failed: {e}")
    yield

app = FastAPI(title="Campus RAG Assistant", lifespan=lifespan)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
SYSTEM_PROMPTS = {
    "personal": "You are a helpful, friendly study assistant. Answer using ONLY the provided document excerpts.",
    "university": "You are the official university regulations assistant. Answer strictly based ONLY on the provided regulation excerpts.",
}

class AskRequest(BaseModel):
    query: str
    mode: str
    session_id: str | None = None

def _collection_for(mode: str) -> str:
    if mode == "personal": return rag.PERSONAL_COLLECTION
    if mode == "university": return rag.UNIVERSITY_COLLECTION
    raise HTTPException(status_code=400, detail="mode must be 'personal' or 'university'")

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/files")
def files(mode: str = Query(default="personal"), session_id: str | None = Query(default=None)):
    collection_name = _collection_for(mode)
    if mode == "personal":
        if not session_id:
            return {"files": []}
        names = rag.list_files(collection_name, session_id=session_id)
    else:
        # university - no session filter, show only preloaded regs
        names = rag.list_files(collection_name)
    return {"files": names}


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    mode: str = Form(default="personal") # allow frontend to send mode
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type:.{ext}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            n_chunks = rag.add_document(
                collection_name=_collection_for(mode),
                file_path=str(tmp_path),
                filename=file.filename,
                session_id=session_id if mode == "personal" else None,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e: # catches the meta tensor error to show real message
            raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    return {"message": f"'{file.filename}' embedded ({n_chunks} chunks)."}

@app.post("/ask")
def ask(req: AskRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")
    collection_name = _collection_for(req.mode)
    session_id = req.session_id if req.mode == "personal" else None
    if req.mode == "personal" and not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    chunks = rag.query_collection(collection_name, req.query, session_id=session_id)
    if not chunks:
        return {"answer": "No relevant documents found. Upload documents first.", "sources": []}
    context = "\n\n---\n\n".join(f"[Source: {c['filename']}]\n{c['text']}" for c in chunks)
    sources = sorted({c["filename"] for c in chunks})
    messages = [
        {"role": "system", "content": SYSTEM_PROMPTS[req.mode]},
        {"role": "user", "content": f"Document excerpts:\n{context}\n\nQuestion: {req.query}"},
    ]
    try:
        completion = groq_client.chat.completions.create(model=GROQ_MODEL, messages=messages, temperature=0.3, max_tokens=800)
        answer = completion.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e}")
    return {"answer": answer, "sources": sources}

# This is delete all endpoint
@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    rag.delete_session_documents(session_id)
    return {"message": "Session documents cleared."}


# This is single file delete endpoint
@app.delete("/files")
def delete_files(
    mode: str = Query(default="personal"),
    session_id: str | None = Query(default=None),
    filename: str | None = Query(default=None)
):
    try:
        collection_name = _collection_for(mode)
        collection = rag.get_collection(collection_name)

        if mode == "personal":
            if not session_id:
                raise HTTPException(status_code=400, detail="session_id required")
            if filename:
                # delete single file for this session
                collection.delete(where={"$and": [{"filename": {"$eq": filename}}, {"session_id": {"$eq": session_id}}]})
                # fallback for older chroma where $and not supported
                # collection.delete(where={"filename": filename}) then filter, but above is safer
                # simpler fallback:
                # all_docs = collection.get(where={"session_id": session_id})
                # ids = [id for id, meta in zip(all_docs['ids'], all_docs['metadatas']) if meta.get('filename')==filename]
                # if ids: collection.delete(ids=ids)
            else:
                # delete all for this session
                collection.delete(where={"session_id": session_id})
        else:
            # university mode - admin
            if filename:
                collection.delete(where={"filename": filename})
            else:
                # delete all university docs
                # get all ids
                data = collection.get()
                if data['ids']:
                    collection.delete(ids=data['ids'])

        return {"message": f"Deleted {filename if filename else 'all files'}", "files": []}

    except Exception as e:
        print(f"Delete error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



app.frontend("/", directory="dist", fallback="index.html")
