# src/utils/chroma_loader.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# Downloads the zipped ChromaDB collection from S3 and rebuilds it locally.
# This is called once at app startup -- the collection is never recreated
# here, only reconnected to (NB02 already built and embedded it).

import os
import uuid
import zipfile
import logging

import boto3
import chromadb

from src.utils.config import settings

logger = logging.getLogger("support_agent.chroma")


def load_chroma_collection():
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )

    import tempfile

    temp_dir = tempfile.gettempdir()
    zip_local_path = os.path.join(temp_dir, f"chroma_db_{uuid.uuid4().hex[:8]}.zip")
    logger.info(f"Downloading Chroma collection from s3://{settings.S3_BUCKET}/{settings.CHROMA_S3_KEY}")
    s3.download_file(settings.S3_BUCKET, settings.CHROMA_S3_KEY, zip_local_path)

    # NOTE: We extract into a fresh, uniquely-named folder instead of
    # deleting and reusing CHROMA_LOCAL_PATH. On Windows, especially with
    # `uvicorn --reload`, a previous process/watcher can still hold an open
    # file handle on chroma.sqlite3 in that folder, which makes
    # shutil.rmtree() fail with WinError 32. A fresh folder avoids the
    # conflict entirely -- nothing needs to be deleted before we can proceed.
    extract_base = settings.CHROMA_LOCAL_PATH
    if extract_base.startswith("/tmp"):
        extract_base = os.path.join(temp_dir, os.path.basename(extract_base))
    extract_path = f"{extract_base}_{uuid.uuid4().hex[:8]}"
    os.makedirs(extract_path, exist_ok=True)

    with zipfile.ZipFile(zip_local_path, "r") as zf:
        zf.extractall(extract_path)

    try:
        os.remove(zip_local_path)
    except Exception:
        pass

    chroma_client = chromadb.PersistentClient(path=extract_path)
    collection = chroma_client.get_collection(name=settings.CHROMA_COLLECTION)

    count = collection.count()
    if count == 0:
        raise RuntimeError(
            "Chroma collection is empty after downloading from S3. "
            "Run NB02 first to build and upload the knowledge base."
        )

    logger.info(f"Chroma collection '{settings.CHROMA_COLLECTION}' loaded: {count} chunks")
    return collection
