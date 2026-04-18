#!/usr/bin/env python3
"""Seed OpenSearch Serverless with blank-form metadata and bootstrap memories.

Data sources (in priority order):
  1. S3 bucket (blank-forms/ prefix) -- used if the stack is deployed
  2. Local sample_data/blank_forms/  -- fallback for local development

Memories are always loaded from sample_data/seed_memories.json.

The script:
  - Creates the 'blank-forms' and 'memories' indices with knn_vector mappings
  - Generates embeddings via Amazon Bedrock Titan Embed v2 (dimension 1024)
  - Indexes each document / memory with its embedding
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

try:
    from opensearchpy import OpenSearch, RequestsHttpConnection
    from requests_aws4auth import AWS4Auth
except ImportError:
    print("[ERROR] Missing dependencies. Install with:")
    print("  pip install opensearch-py requests-aws4auth")
    sys.exit(1)

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_MEMORIES_PATH = PROJECT_ROOT / "sample_data" / "seed_memories.json"
LOCAL_BLANK_FORMS_DIR = PROJECT_ROOT / "sample_data" / "blank_forms"

FORMS_INDEX = "blank-forms"
MEMORIES_INDEX = "memories"
EMBEDDING_DIMENSION = 1024
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
REGION = "us-east-1"

# ------------------------------------------------------------------ #
# AWS clients
# ------------------------------------------------------------------ #
session = boto3.Session(region_name=REGION)
credentials = session.get_credentials().get_frozen_credentials()
bedrock_runtime = session.client("bedrock-runtime")
s3_client = session.client("s3")
cf_client = session.client("cloudformation")


def get_opensearch_endpoint() -> str:
    """Retrieve the OpenSearch Serverless endpoint from CloudFormation outputs."""
    try:
        response = cf_client.describe_stacks(StackName="SearchStack")
        outputs = response["Stacks"][0].get("Outputs", [])
        for output in outputs:
            if "opensearch" in output["OutputKey"].lower() or "endpoint" in output["OutputKey"].lower() or "collection" in output["OutputKey"].lower():
                return output["OutputValue"]
    except (ClientError, IndexError, KeyError):
        pass

    # Fallback: try to find the collection endpoint via AOSS API
    try:
        aoss_client = session.client("opensearchserverless")
        collections = aoss_client.list_collections()
        for collection in collections.get("collectionSummaries", []):
            if collection["name"] == "pa-bot-vectors":
                detail = aoss_client.batch_get_collection(ids=[collection["id"]])
                endpoint = detail["collectionDetails"][0].get("collectionEndpoint", "")
                if endpoint:
                    return endpoint
    except (ClientError, IndexError, KeyError):
        pass

    print("[ERROR] Could not determine OpenSearch endpoint.")
    print("  Make sure the SearchStack is deployed: cdk deploy SearchStack")
    sys.exit(1)


def build_opensearch_client(endpoint: str) -> OpenSearch:
    """Build an OpenSearch client with AWS Sig v4 auth for Serverless."""
    # Strip https:// prefix if present for the host
    host = endpoint.replace("https://", "").rstrip("/")

    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        REGION,
        "aoss",
        session_token=credentials.token,
    )

    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30,
    )


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector using Amazon Bedrock Titan Embed v2."""
    response = bedrock_runtime.invoke_model(
        modelId=EMBED_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text}),
    )
    body = json.loads(response["body"].read())
    return body["embedding"]


# ------------------------------------------------------------------ #
# Index creation
# ------------------------------------------------------------------ #

def create_index_if_not_exists(client: OpenSearch, index_name: str, mapping: dict) -> None:
    """Create an OpenSearch index with the given mapping if it does not exist."""
    try:
        if client.indices.exists(index=index_name):
            print(f"  Index '{index_name}' already exists. Deleting and re-creating...")
            client.indices.delete(index=index_name)
            time.sleep(2)
    except Exception:
        pass  # Index may not exist yet

    print(f"  Creating index '{index_name}'...")
    client.indices.create(index=index_name, body=mapping)
    print(f"  Index '{index_name}' created.")


FORMS_INDEX_MAPPING = {
    "settings": {
        "index": {
            "knn": True,
        }
    },
    "mappings": {
        "properties": {
            "form_id": {"type": "keyword"},
            "title": {"type": "text"},
            "description": {"type": "text"},
            "s3_key": {"type": "keyword"},
            "content_text": {"type": "text"},
            "embedding": {
                "type": "knn_vector",
                "dimension": EMBEDDING_DIMENSION,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                },
            },
        }
    },
}

MEMORIES_INDEX_MAPPING = {
    "settings": {
        "index": {
            "knn": True,
        }
    },
    "mappings": {
        "properties": {
            "memory_id": {"type": "keyword"},
            "memory_type": {"type": "keyword"},
            "content": {"type": "text"},
            "document_id": {"type": "keyword"},
            "provider_id": {"type": "keyword"},
            "prescription_code": {"type": "keyword"},
            "success_count": {"type": "integer"},
            "failure_count": {"type": "integer"},
            "success_rate": {"type": "float"},
            "embedding": {
                "type": "knn_vector",
                "dimension": EMBEDDING_DIMENSION,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                },
            },
        }
    },
}


# ------------------------------------------------------------------ #
# Data loading
# ------------------------------------------------------------------ #

def get_s3_bucket_name() -> str | None:
    """Try to find the data bucket name from CloudFormation."""
    try:
        response = cf_client.describe_stacks(StackName="StorageStack")
        outputs = response["Stacks"][0].get("Outputs", [])
        for output in outputs:
            if "databucket" in output["OutputKey"].lower() or "bucket" in output["OutputKey"].lower():
                return output["OutputValue"]
    except (ClientError, IndexError, KeyError):
        pass
    return None


def load_blank_forms_from_s3(bucket: str) -> list[dict]:
    """List blank forms in S3 and build metadata for indexing."""
    forms = []
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="blank-forms/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                filename = os.path.basename(key)
                form_id = os.path.splitext(filename)[0]
                forms.append({
                    "form_id": form_id,
                    "title": form_id.replace("_", " ").replace("-", " ").title(),
                    "description": f"Blank PA form: {filename}",
                    "s3_key": key,
                    "content_text": f"Prior authorization form {form_id}",
                })
    except ClientError as exc:
        print(f"  [WARN] Could not list S3 blank forms: {exc}")
    return forms


def load_blank_forms_from_local() -> list[dict]:
    """Load blank form metadata from the local sample_data directory."""
    forms = []
    if not LOCAL_BLANK_FORMS_DIR.exists():
        return forms
    for path in sorted(LOCAL_BLANK_FORMS_DIR.iterdir()):
        if path.is_file() and not path.name.startswith("."):
            form_id = path.stem
            forms.append({
                "form_id": form_id,
                "title": form_id.replace("_", " ").replace("-", " ").title(),
                "description": f"Blank PA form: {path.name}",
                "s3_key": f"blank-forms/{path.name}",
                "content_text": f"Prior authorization form {form_id}",
            })
    return forms


def load_seed_memories() -> list[dict]:
    """Load seed memories from the JSON file."""
    if not SEED_MEMORIES_PATH.exists():
        print(f"  [WARN] Seed memories file not found: {SEED_MEMORIES_PATH}")
        return []
    with open(SEED_MEMORIES_PATH) as f:
        return json.load(f)


# ------------------------------------------------------------------ #
# Indexing
# ------------------------------------------------------------------ #

def index_forms(client: OpenSearch, forms: list[dict]) -> int:
    """Generate embeddings and index blank forms into OpenSearch."""
    indexed = 0
    for form in forms:
        embed_text = f"{form['title']} {form['description']} {form['content_text']}"
        print(f"  Generating embedding for form '{form['form_id']}'...")
        embedding = generate_embedding(embed_text)

        doc = {
            "form_id": form["form_id"],
            "title": form["title"],
            "description": form["description"],
            "s3_key": form["s3_key"],
            "content_text": form["content_text"],
            "embedding": embedding,
        }

        client.index(index=FORMS_INDEX, id=form["form_id"], body=doc)
        indexed += 1
        print(f"  Indexed form: {form['form_id']}")

    return indexed


def index_memories(client: OpenSearch, memories: list[dict]) -> int:
    """Generate embeddings and index seed memories into OpenSearch."""
    indexed = 0
    for memory in memories:
        content = memory["content"]
        memory_id = memory["memory_id"]

        print(f"  Generating embedding for memory '{memory_id}'...")
        embedding = generate_embedding(content)

        success_count = memory.get("success_count", 0)
        failure_count = memory.get("failure_count", 0)
        total = success_count + failure_count
        success_rate = success_count / total if total > 0 else 0.5

        doc = {
            "memory_id": memory_id,
            "memory_type": memory["memory_type"],
            "content": content,
            "document_id": memory.get("document_id"),
            "provider_id": memory.get("provider_id"),
            "prescription_code": memory.get("prescription_code"),
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_rate,
            "embedding": embedding,
        }

        client.index(index=MEMORIES_INDEX, id=memory_id, body=doc)
        indexed += 1
        print(f"  Indexed memory: {memory_id} (type={memory['memory_type']})")

    return indexed


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main() -> None:
    print("=" * 60)
    print("Seeding OpenSearch Serverless indices")
    print("=" * 60)
    print()

    # 1. Get OpenSearch endpoint
    print("[1/5] Retrieving OpenSearch endpoint...")
    endpoint = get_opensearch_endpoint()
    print(f"  Endpoint: {endpoint}")
    print()

    # 2. Build client
    print("[2/5] Connecting to OpenSearch...")
    client = build_opensearch_client(endpoint)
    print("  Connected.")
    print()

    # 3. Create indices
    print("[3/5] Creating indices...")
    create_index_if_not_exists(client, FORMS_INDEX, FORMS_INDEX_MAPPING)
    create_index_if_not_exists(client, MEMORIES_INDEX, MEMORIES_INDEX_MAPPING)
    print()

    # 4. Index blank forms
    print("[4/5] Indexing blank forms...")
    bucket = get_s3_bucket_name()
    forms = []
    if bucket:
        print(f"  Loading from S3 bucket: {bucket}")
        forms = load_blank_forms_from_s3(bucket)
    if not forms:
        print("  Falling back to local sample_data/blank_forms/...")
        forms = load_blank_forms_from_local()
    if forms:
        num_forms = index_forms(client, forms)
        print(f"  Indexed {num_forms} form(s).")
    else:
        print("  No blank forms found to index. Add forms to sample_data/blank_forms/ and re-run.")
    print()

    # 5. Index memories
    print("[5/5] Indexing seed memories...")
    memories = load_seed_memories()
    if memories:
        num_memories = index_memories(client, memories)
        print(f"  Indexed {num_memories} memory/memories.")
    else:
        print("  No seed memories found.")
    print()

    print("=" * 60)
    print("Seeding complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
