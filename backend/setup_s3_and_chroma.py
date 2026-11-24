# backend/setup_s3_and_chroma.py
# Automates NB01 (Section 13-14) and NB02 to create and upload
# the 6 policy documents and the ChromaDB vector store directly to AWS S3.

import os
import shutil
import time
import zipfile
import boto3
from openai import OpenAI, AzureOpenAI
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.utils.config import settings

def main():
    print("=" * 60)
    print("🚀 Support Agent: S3 Knowledge Base & ChromaDB Setup")
    print("=" * 60)

    # 1. Initialize Clients
    print("\n[1/6] Connecting to AWS S3 and Azure OpenAI...")
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    
    # Use Azure OpenAI (Microsoft AI Foundry)
    azure_endpoint = getattr(settings, "AZURE_OPENAI_ENDPOINT", "https://enzi-resource.services.ai.azure.com/")
    api_version = getattr(settings, "OPENAI_API_VERSION", "2024-06-01")
    
    openai_client = AzureOpenAI(
        azure_endpoint=azure_endpoint,
        api_key=settings.OPENAI_API_KEY,
        api_version=api_version,
    )
    print(f"Connected to Azure OpenAI endpoint: {azure_endpoint}")

    # 2. Check / Create S3 Bucket
    bucket_name = settings.S3_BUCKET
    region = settings.AWS_REGION
    print(f"\n[2/6] Checking S3 bucket '{bucket_name}' in region '{region}'...")
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"✅ S3 bucket '{bucket_name}' exists and is accessible!")
    except Exception as e:
        print(f"Bucket '{bucket_name}' does not exist or not accessible yet. Attempting to create...")
        try:
            if region == "us-east-1":
                s3.create_bucket(Bucket=bucket_name)
            else:
                s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": region},
                )
            print(f"✅ Successfully created S3 bucket: {bucket_name}")
        except Exception as create_err:
            print(f"❌ Failed to create bucket '{bucket_name}': {create_err}")
            return

    # 3. Create the 6 Policy Documents
    print("\n[3/6] Generating 6 company policy documents...")
    policies = {
        "refund_policy.txt": (
            "REFUND POLICY v3.2\n\n"
            "1. ELIGIBILITY\n"
            "   Refund requests within 30 days of purchase.\n"
            "   Product unused in original packaging.\n"
            "   Digital products within 7 days if not downloaded.\n\n"
            "2. DUPLICATE BILLING\n"
            "   Same amount, same card, same day = duplicate charge.\n"
            "   Eligible for immediate full refund without documentation.\n"
            "   Processing time 3 to 5 business days.\n\n"
            "3. SLA BREACH COMPENSATION\n"
            "   Dispute unresolved beyond 7 days: escalate to senior team.\n"
            "   Dispute unresolved beyond 10 days: 1-month credit as goodwill.\n\n"
            "4. AUTOMATED REFUND LIMITS\n"
            "   Up to Rs.5000: processed automatically.\n"
            "   Above Rs.5000: senior agent review within 24 hours.\n"
        ),
        "billing_policy.txt": (
            "BILLING POLICY v2.1\n\n"
            "1. BILLING CYCLE\n"
            "   Monthly: billed same date each month.\n"
            "   Annual: billed on anniversary date.\n"
            "   Pro-rated billing on plan changes mid-cycle.\n\n"
            "2. PAYMENT METHODS\n"
            "   Accepted: Visa, Mastercard, RuPay, UPI, net banking.\n"
            "   EMI available on orders above Rs.3000.\n\n"
            "3. PAYMENT FAILURE\n"
            "   3 automatic retries over 24 hours.\n"
            "   Account suspended after 3 failed attempts.\n"
            "   Data preserved 30 days. Restored on successful payment.\n"
        ),
        "shipping_policy.txt": (
            "SHIPPING POLICY v1.8\n\n"
            "1. DELIVERY TIMELINES\n"
            "   Metro cities: 2 business days.\n"
            "   Tier 2 cities: 3 to 4 business days.\n"
            "   Tier 3 and rural: 5 to 7 business days.\n\n"
            "2. NON-DELIVERY CLAIM\n"
            "   Raise within 7 days of expected delivery date.\n"
            "   Investigation within 24 hours if shows delivered.\n"
            "   Confirmed non-delivery: replacement or full refund.\n\n"
            "3. DAMAGED GOODS\n"
            "   Report damage within 48 hours with photos.\n"
            "   Replacement within 2 business days of approval.\n"
        ),
        "product_warranty.txt": (
            "WARRANTY POLICY v2.4\n\n"
            "1. WARRANTY PERIODS\n"
            "   Electronics phones and laptops: 1 year.\n"
            "   Accessories cables and chargers: 6 months.\n"
            "   Home appliances: 2 years.\n\n"
            "2. COVERED\n"
            "   Manufacturing defects and hardware failures.\n"
            "   Battery failure below 80 percent capacity.\n\n"
            "3. NOT COVERED\n"
            "   Physical damage, water damage, cracks.\n"
            "   Damage from misuse or unauthorized repair.\n"
            "   Normal wear and tear.\n\n"
            "4. CLAIM PROCESS\n"
            "   Submit via portal with serial number and purchase proof.\n"
            "   Repair or replacement within 7 business days.\n"
        ),
        "account_management.txt": (
            "ACCOUNT MANAGEMENT POLICY v1.5\n\n"
            "1. PLAN CHANGES\n"
            "   Upgrade: effective immediately, billed pro-rated.\n"
            "   Downgrade: effective next billing cycle.\n\n"
            "2. CANCELLATION\n"
            "   Processed within 24 hours.\n"
            "   Data retained 90 days for export.\n"
            "   No cancellation fee for monthly plans.\n"
            "   Annual plan: refund for unused complete months only.\n\n"
            "3. ACCOUNT SUSPENSION\n"
            "   Suspended for non-payment after 3 failed billing attempts.\n"
            "   Reactivate by settling balance and contacting support.\n"
        ),
        "escalation_policy.txt": (
            "ESCALATION POLICY v2.0\n\n"
            "1. RESPONSE SLAs\n"
            "   Critical priority: first response within 15 minutes.\n"
            "   High priority: first response within 1 hour.\n"
            "   Medium priority: first response within 4 hours.\n\n"
            "2. ESCALATION TRIGGERS\n"
            "   Customer requests human agent: escalate immediately.\n"
            "   Very negative sentiment 3 consecutive messages: auto-escalate.\n"
            "   Legal or consumer court threat: senior manager immediately.\n\n"
            "3. RETENTION OFFERS\n"
            "   Triggered automatically when churn score above 0.7.\n"
            "   Basic customer: 1 month free subscription.\n"
            "   Premium customer: 1 month free plus upgrade for 3 months.\n"
            "   Enterprise: dedicated account manager call within 24 hours.\n"
        ),
    }

    local_kb_dir = "knowledge_base"
    os.makedirs(local_kb_dir, exist_ok=True)
    for fname, content in policies.items():
        local_path = os.path.join(local_kb_dir, fname)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)
        s3_key = f"knowledge-base/{fname}"
        s3.upload_file(local_path, bucket_name, s3_key)
        print(f"  Uploaded to S3: s3://{bucket_name}/{s3_key}")

    # 4. Chunk Documents
    print("\n[4/6] Chunking documents with RecursiveCharacterTextSplitter...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        separators=["\n\n", "\n", ". ", " "],
    )

    all_chunks = []
    chunk_counter = 0
    for fname, text in sorted(policies.items()):
        category = fname.replace("_policy.txt", "").replace("_management.txt", "").replace(".txt", "")
        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            chunk_counter += 1
            all_chunks.append({
                "chunk_id": f"chunk_{chunk_counter:04d}",
                "content": chunk,
                "source_doc": fname,
                "category": category,
                "chunk_num": i + 1,
            })
    print(f"  Created {len(all_chunks)} chunks across {len(policies)} documents.")

    # 5. Generate Embeddings & Store in ChromaDB
    print("\n[5/6] Embedding chunks with Azure OpenAI 'text-embedding-3-large'...")
    batch_size = 10
    embeddings = []
    for i in range(0, len(all_chunks), batch_size):
        batch = [c["content"] for c in all_chunks[i:i + batch_size]]
        resp = openai_client.embeddings.create(input=batch, model="text-embedding-3-large")
        embeddings.extend([e.embedding for e in resp.data])
        print(f"  Embedded chunks {i + 1} to {min(i + batch_size, len(all_chunks))} of {len(all_chunks)}")
        time.sleep(0.2)

    chroma_dir = "./chroma_db_build"
    if os.path.exists(chroma_dir):
        shutil.rmtree(chroma_dir, ignore_errors=True)

    chroma_client = chromadb.PersistentClient(path=chroma_dir)
    collection = chroma_client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    collection.add(
        ids=[c["chunk_id"] for c in all_chunks],
        embeddings=embeddings,
        documents=[c["content"] for c in all_chunks],
        metadatas=[{"category": c["category"], "source_doc": c["source_doc"]} for c in all_chunks],
    )
    print(f"✅ ChromaDB collection '{settings.CHROMA_COLLECTION}' created with {collection.count()} chunks.")

    # 6. Zip and Upload to S3
    print(f"\n[6/6] Zipping ChromaDB and uploading to s3://{bucket_name}/{settings.CHROMA_S3_KEY}...")
    zip_basename = "chroma_db"
    zip_path = shutil.make_archive(zip_basename, "zip", chroma_dir)

    s3.upload_file(zip_path, bucket_name, settings.CHROMA_S3_KEY)
    print(f"✅ Successfully uploaded: s3://{bucket_name}/{settings.CHROMA_S3_KEY}")

    # Cleanup temporary local build folder and zip
    try:
        shutil.rmtree(chroma_dir, ignore_errors=True)
        if os.path.exists(zip_path):
            os.remove(zip_path)
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("🎉 Knowledge Base & ChromaDB setup is 100% COMPLETE!")
    print(f"   Bucket:       s3://{bucket_name}")
    print(f"   Policies:     s3://{bucket_name}/knowledge-base/ (6 files)")
    print(f"   ChromaDB Zip: s3://{bucket_name}/{settings.CHROMA_S3_KEY}")
    print("=" * 60)

if __name__ == "__main__":
    main()
