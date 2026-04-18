"""OpenSearch Serverless client for vector search on forms and memories."""

from __future__ import annotations

import logging
from typing import Any, Optional

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from shared.config import cfg

logger = logging.getLogger(__name__)


class OpenSearchClient:
    """Manages KNN vector searches and indexing against OpenSearch Serverless."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        self._endpoint = endpoint or cfg.OPENSEARCH_ENDPOINT
        self._region = region or cfg.AWS_REGION
        self._forms_index = cfg.FORMS_INDEX
        self._memories_index = cfg.MEMORIES_INDEX

        credentials = boto3.Session().get_credentials()
        aws_auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            self._region,
            "aoss",  # OpenSearch Serverless service name
            session_token=credentials.token,
        )

        self._client = OpenSearch(
            hosts=[{"host": self._endpoint, "port": 443}],
            http_auth=aws_auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Form search
    # ------------------------------------------------------------------

    def search_forms(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Perform a KNN search on the blank-forms index.

        Returns up to ``top_k`` form documents ordered by similarity.
        """

        body = {
            "size": top_k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_embedding,
                        "k": top_k,
                    }
                }
            },
        }

        try:
            response = self._client.search(index=self._forms_index, body=body)
            return [
                {**hit["_source"], "_score": hit["_score"]}
                for hit in response["hits"]["hits"]
            ]
        except Exception:
            logger.exception("Form search failed on index %s", self._forms_index)
            raise

    # ------------------------------------------------------------------
    # Memory search
    # ------------------------------------------------------------------

    def search_memories(
        self,
        query_embedding: list[float],
        memory_type: Optional[str] = None,
        document_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        prescription_code: Optional[str] = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """KNN search on the memories index with optional field-level filters.

        Filters narrow the candidate set *before* the KNN distance calculation,
        ensuring both relevance and specificity.
        """

        filter_clauses: list[dict[str, Any]] = []
        if memory_type is not None:
            filter_clauses.append({"term": {"memory_type": memory_type}})
        if document_id is not None:
            filter_clauses.append({"term": {"document_id": document_id}})
        if provider_id is not None:
            filter_clauses.append({"term": {"provider_id": provider_id}})
        if prescription_code is not None:
            filter_clauses.append({"term": {"prescription_code": prescription_code}})

        knn_clause: dict[str, Any] = {
            "vector": query_embedding,
            "k": top_k,
        }
        if filter_clauses:
            knn_clause["filter"] = {"bool": {"must": filter_clauses}}

        body: dict[str, Any] = {
            "size": top_k,
            "query": {
                "knn": {
                    "embedding": knn_clause,
                }
            },
        }

        try:
            response = self._client.search(index=self._memories_index, body=body)
            return [
                {**hit["_source"], "_score": hit["_score"]}
                for hit in response["hits"]["hits"]
            ]
        except Exception:
            logger.exception("Memory search failed on index %s", self._memories_index)
            raise

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_memory(
        self,
        memory_id: str,
        content: str,
        memory_type: str,
        embedding: list[float],
        document_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        prescription_code: Optional[str] = None,
        success_rate: float = 0.0,
    ) -> None:
        """Index (or update) a memory document."""

        doc: dict[str, Any] = {
            "memory_id": memory_id,
            "content": content,
            "memory_type": memory_type,
            "embedding": embedding,
            "success_rate": success_rate,
        }
        if document_id is not None:
            doc["document_id"] = document_id
        if provider_id is not None:
            doc["provider_id"] = provider_id
        if prescription_code is not None:
            doc["prescription_code"] = prescription_code

        try:
            self._client.index(
                index=self._memories_index,
                id=memory_id,
                body=doc,
            )
        except Exception:
            logger.exception("Failed to index memory %s", memory_id)
            raise

    def index_form(
        self,
        form_id: str,
        title: str,
        description: str,
        fields_summary: str,
        s3_key: str,
        embedding: list[float],
    ) -> None:
        """Index (or update) a blank form document."""

        doc: dict[str, Any] = {
            "form_id": form_id,
            "title": title,
            "description": description,
            "fields_summary": fields_summary,
            "s3_key": s3_key,
            "embedding": embedding,
        }

        try:
            self._client.index(
                index=self._forms_index,
                id=form_id,
                body=doc,
            )
        except Exception:
            logger.exception("Failed to index form %s", form_id)
            raise
