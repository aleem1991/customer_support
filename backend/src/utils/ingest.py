# src/utils/ingest.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# This is what runs when the "Load Documents from S3" button is clicked
# in the Streamlit UI. It downloads the policy .txt files from S3, chunks
# them, embeds them with OpenAI, and stores the result in ChromaDB --
# then zips the Chroma folder back up to S3 so future app restarts can
# just reconnect instead of re-embedding everything from scratch.

import os
import uuid
import zipfile
import logging

import boto3
import chromadb
from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.utils.config import settings
from src.tools import database_tools

logger = logging.getLogger("support_agent.ingest")

client = OpenAI(api_key=settings.OPENAI_API_KEY)
EMBED_MODEL = "text-embedding-3-large"


def run_ingestion() -> dict:
    """Full pipeline: S3 .txt files -> chunks -> embeddings -> ChromaDB -> zip back to S3.
    Returns a summary dict the API can return to the frontend."""

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )

    # Step 1 -- download all .txt policy docs from S3
    local_dir = "/tmp/knowledge_base"
    os.makedirs(local_dir, exist_ok=True)

    resp = s3.list_objects_v2(Bucket=settings.S3_BUCKET, Prefix="knowledge-base/")
    keys = [o["Key"] for o in resp.get("Contents", []) if o["Key"].endswith(".txt")]

    if not keys:
        raise RuntimeError("No .txt files found under knowledge-base/ in S3 bucket.")

    for key in keys:
        fname = key.split("/")[-1]
        s3.download_file(settings.S3_BUCKET, key, f"{local_dir}/{fname}")

    logger.info(f"Downloaded {len(keys)} policy documents from S3")

    # Step 2 -- chunk each document
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400, chunk_overlap=50, separators=["\n\n", "\n", ". ", " "]
    )

    all_chunks = []
    for fname in os.listdir(local_dir):
        if not fname.endswith(".txt"):
            continue
        with open(f"{local_dir}/{fname}") as f:
            text = f.read()
        category = (
            fname.replace("_policy.txt", "")
            .replace("_management.txt", "")
            .replace(".txt", "")
        )
        for chunk in splitter.split_text(text):
            all_chunks.append({"content": chunk, "source_doc": fname, "category": category})

    logger.info(f"Created {len(all_chunks)} chunks from {len(keys)} documents")

    # Step 3 -- embed all chunks in batches
    embeddings = []
    batch_size = 10
    for i in range(0, len(all_chunks), batch_size):
        batch = [c["content"] for c in all_chunks[i:i + batch_size]]
        resp = client.embeddings.create(input=batch, model=EMBED_MODEL)
        embeddings.extend([e.embedding for e in resp.data])

    logger.info(f"Generated {len(embeddings)} embeddings")

    # Step 4 -- rebuild the ChromaDB collection from scratch
    # NOTE: We use a fresh, uniquely-named temp directory instead of deleting
    # the existing CHROMA_LOCAL_PATH in place. On Windows, the running app
    # may still hold an open file handle on chroma.sqlite3 from startup,
    # which makes shutil.rmtree() fail with WinError 32. Building in a new
    # directory and swapping the in-memory reference avoids that entirely.
    fresh_path = f"{settings.CHROMA_LOCAL_PATH}_{uuid.uuid4().hex[:8]}"
    os.makedirs(fresh_path, exist_ok=True)

    chroma_client = chromadb.PersistentClient(path=fresh_path)
    try:
        chroma_client.delete_collection(settings.CHROMA_COLLECTION)
    except Exception:
        pass
    collection = chroma_client.create_collection(name=settings.CHROMA_COLLECTION)

    collection.add(
        ids=[f"chunk_{i}" for i in range(len(all_chunks))],
        embeddings=embeddings,
        documents=[c["content"] for c in all_chunks],
        metadatas=[{"category": c["category"], "source_doc": c["source_doc"]} for c in all_chunks],
    )

    # Step 5 -- zip the collection and upload back to S3
    zip_path = f"/tmp/chroma_db_{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(fresh_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, fresh_path)
                zf.write(full_path, rel_path)

    s3.upload_file(zip_path, settings.S3_BUCKET, settings.CHROMA_S3_KEY)
    logger.info(f"Uploaded rebuilt Chroma collection to s3://{settings.S3_BUCKET}/{settings.CHROMA_S3_KEY}")

    # Clean up the temp zip file (safe to delete, nothing has it open)
    try:
        os.remove(zip_path)
    except Exception:
        pass

    # Step 6 -- point the running app's tools at the freshly rebuilt collection
    database_tools.set_chroma_collection(collection)

    return {
        "documents_processed": len(keys),
        "chunks_created": len(all_chunks),
        "embeddings_generated": len(embeddings),
        "collection_name": settings.CHROMA_COLLECTION,
        "status": "complete",
    }
