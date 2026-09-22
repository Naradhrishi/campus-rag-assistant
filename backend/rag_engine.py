"""
Core RAG logic shared by both modes:
  - "personal"   -> per-session, user-uploaded documents (student assistant)
  - "university" -> one shared, admin-ingested collection (regulations bot)

Everything lives in a single Chroma collection per mode. Personal documents
are filtered by a session_id stored in each chunk's metadata so different
users/browsers never see each other's uploads.
"""

import os
import uuid
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from docx import Document as DocxDocument
from chromadb.config import Settings

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_store")

PERSONAL_COLLECTION = "personal_documents"
UNIVERSITY_COLLECTION = "university_regulations"

CHUNK_SIZE = 900       # characters per chunk
CHUNK_OVERLAP = 150    # character overlap between chunks
TOP_K = 4              # how many chunks to retrieve per query

# --------------------------------------------------------------------------
# Singletons (loaded once per process)
# --------------------------------------------------------------------------

_client = None
_embedder = None


def get_client():
    global _client
    if _client is None:
        Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
            _embedder = ONNXMiniLM_L6_V2()
        except:
            import chromadb.utils.embedding_functions as ef
            _embedder = ef.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2",
                device="cpu"
            )
    return _embedder


def get_collection(name: str):
    return get_client().get_or_create_collection(
        name=name, embedding_function=get_embedder()
    )


# --------------------------------------------------------------------------
# Text extraction
# --------------------------------------------------------------------------

def extract_text(file_path: str, filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]

    if ext == "pdf":
        reader = PdfReader(file_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n".join(pages)

    if ext == "docx":
        doc = DocxDocument(file_path)
        return "\n".join(p.text for p in doc.paragraphs)

    if ext == "txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    raise ValueError(f"Unsupported file type: .{ext}")


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    text = " ".join(text.split())  # normalize whitespace
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------

def add_document(
    collection_name: str,
    file_path: str,
    filename: str,
    session_id: str | None = None,
):
    """Extract, chunk, embed and store a document. Returns number of chunks added."""
    text = extract_text(file_path, filename)
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("No extractable text found in this file.")

    collection = get_collection(collection_name)

    doc_id = str(uuid.uuid4())[:8]
    ids = [f"{doc_id}-{i}" for i in range(len(chunks))]
    metadatas = []
    for i in range(len(chunks)):
        meta = {"filename": filename, "chunk_index": i}
        if session_id:
            meta["session_id"] = session_id
        metadatas.append(meta)

    collection.add(documents=chunks, metadatas=metadatas, ids=ids)
    return len(chunks)


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------

def query_collection(collection_name: str, query: str, session_id: str | None = None, top_k: int = TOP_K):
    collection = get_collection(collection_name)
    where = {"session_id": session_id} if session_id else None

    # count after filter, not total collection
    if where:
        count = len(collection.get(where=where).get("ids", []))
    else:
        count = collection.count()

    if count == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, count),
        where=where,
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    return [{"text": d, "filename": m.get("filename", "unknown")} for d, m in zip(docs, metas)]


def list_files(collection_name: str, session_id: str | None = None):
    collection = get_collection(collection_name)
    where = {"session_id": session_id} if session_id else None
    result = collection.get(where=where) if where else collection.get()
    filenames = sorted({m.get("filename") for m in result.get("metadatas", []) if m.get("filename")})
    return filenames


def delete_session_documents(session_id: str):
    """Optional cleanup helper — wipe a personal session's uploads."""
    collection = get_collection(PERSONAL_COLLECTION)
    collection.delete(where={"session_id": session_id})

    
