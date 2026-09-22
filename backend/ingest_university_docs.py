"""
One-time (or whenever regulations change) admin script.

Drop your university regulation files (.pdf / .docx / .txt) into the
`university_docs/` folder next to this script, then run:

    python ingest_university_docs.py

This embeds them into the shared "university_regulations" Chroma collection
that every user's "University Regulations" mode queries. Re-running it is
safe for new files, but if you replace a file you should delete the old
one from the collection first (or just delete the chroma_store/ folder and
re-run against all files).
"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import rag_engine as rag

DOCS_DIR = Path(__file__).parent / "university_docs"


def main():
    files = [
        f for f in DOCS_DIR.iterdir()
        if f.is_file() and f.suffix.lower().lstrip(".") in {"pdf", "docx", "txt"}
    ]

    if not files:
        print(f"No .pdf/.docx/.txt files found in {DOCS_DIR}/")
        print("Add your regulation documents there and re-run this script.")
        return

    existing = set(rag.list_files(rag.UNIVERSITY_COLLECTION))

    for f in files:
        if f.name in existing:
            print(f"Skipping '{f.name}' — already ingested.")
            continue
        try:
            n_chunks = rag.add_document(
                collection_name=rag.UNIVERSITY_COLLECTION,
                file_path=str(f),
                filename=f.name,
            )
            print(f"Ingested '{f.name}' ({n_chunks} chunks).")
        except Exception as e:
            print(f"Failed to ingest '{f.name}': {e}")

    print("Done.")


if __name__ == "__main__":
    main()
