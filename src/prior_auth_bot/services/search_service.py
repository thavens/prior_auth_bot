from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from prior_auth_bot.models import Memory, MemoryRetrievalResult
from prior_auth_bot.services.memory_feature import MemoryFeatureService

if TYPE_CHECKING:
    from prior_auth_bot.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

PROVIDER_URLS = {
    "medi-cal": "https://medi-calrx.dhcs.ca.gov/provider/prior-authorization",
}

PROVIDER_CDL_URLS = {
    "medi-cal": "https://medi-calrx.dhcs.ca.gov/cms/medicalrx/static-assets/documents/provider/forms-and-information/cdl/Medi-Cal_Rx_Contract_Drugs_List_FINAL.pdf",
}

_ERROR_PAGE_RE = re.compile(
    r"(not\s*found|403\s*forbidden|500\s*internal|error|unavailable)",
    re.IGNORECASE,
)


def _looks_like_error_page(content: str) -> bool:
    trimmed = content.strip()[:500].lower()
    if not (trimmed.startswith("<!doctype") or trimmed.startswith("<html")):
        return False
    return bool(_ERROR_PAGE_RE.search(trimmed))


class SearchService:
    def __init__(self, s3_client, dynamodb_resource, memory_service: MemoryFeatureService,
                 blank_forms_bucket: str, cache_table_name: str,
                 embedding_service: EmbeddingService | None = None):
        self.s3 = s3_client
        self.cache_table = dynamodb_resource.Table(cache_table_name)
        self.memory_service = memory_service
        self.blank_forms_bucket = blank_forms_bucket
        self.embedding_service = embedding_service

    def search_forms(self, provider_name: str) -> list[dict]:
        prefix = f"{provider_name}/"
        response = self.s3.list_objects_v2(Bucket=self.blank_forms_bucket, Prefix=prefix)
        results = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".pdf"):
                continue
            form_name = key[len(prefix):-4]
            results.append({
                "s3_key": key,
                "form_name": form_name,
                "provider_name": provider_name,
                "last_modified": obj["LastModified"].isoformat(),
                "size_bytes": obj["Size"],
            })
        return results

    def search_memories(self, provider: str, treatment: str, limit: int = 10) -> MemoryRetrievalResult:
        seen: dict[str, Memory] = {}

        for memory in self.memory_service.query_by_provider_treatment(provider, treatment, limit=limit):
            memory.relevance_score = 1.0
            seen[memory.memory_id] = memory

        for memory in self.memory_service.query_by_provider(provider, limit=limit):
            if memory.memory_id not in seen:
                memory.relevance_score = 0.7
                seen[memory.memory_id] = memory

        for memory in self.memory_service.query_by_treatment(treatment, limit=limit):
            if memory.memory_id not in seen:
                memory.relevance_score = 0.5
                seen[memory.memory_id] = memory

        # Hybrid reranking: combine key-based scores with semantic similarity
        if self.embedding_service:
            query_text = f"{provider} {treatment}"
            query_embedding = self.embedding_service.embed(query_text)
            if query_embedding:
                all_embedded = self.memory_service.scan_all_with_embeddings()
                embedded_map = {m.memory_id: m for m in all_embedded if m.embedding}

                # Rerank key-based results with cosine similarity
                for memory_id, memory in seen.items():
                    if memory_id in embedded_map:
                        cos_sim = self.embedding_service.cosine_similarity(
                            query_embedding, embedded_map[memory_id].embedding
                        )
                        memory.relevance_score = 0.4 * memory.relevance_score + 0.6 * cos_sim

                # Include embedding-only matches not found in key-based lookup
                for memory_id, emb_memory in embedded_map.items():
                    if memory_id not in seen:
                        cos_sim = self.embedding_service.cosine_similarity(
                            query_embedding, emb_memory.embedding
                        )
                        if cos_sim > 0.3:
                            emb_memory.relevance_score = 0.6 * cos_sim
                            seen[memory_id] = emb_memory

        sorted_memories = sorted(seen.values(), key=lambda m: m.relevance_score, reverse=True)[:limit]
        return MemoryRetrievalResult(memories=sorted_memories)

    def search_memories_semantic(self, query: str, limit: int = 10) -> MemoryRetrievalResult:
        """Pure semantic search for free-text queries (e.g. rejection pattern matching)."""
        if not self.embedding_service:
            return MemoryRetrievalResult(memories=[])
        query_embedding = self.embedding_service.embed(query)
        if not query_embedding:
            return MemoryRetrievalResult(memories=[])
        all_memories = self.memory_service.scan_all_with_embeddings()
        candidates = [(m.memory_id, m.embedding) for m in all_memories if m.embedding]
        ranked = self.embedding_service.semantic_search(query_embedding, candidates, top_k=limit)
        memory_map = {m.memory_id: m for m in all_memories}
        results = []
        for memory_id, score in ranked:
            if memory_id in memory_map:
                m = memory_map[memory_id]
                m.relevance_score = score
                results.append(m)
        return MemoryRetrievalResult(memories=results)

    def scrape_with_cache(self, cache_key: str, url: str, ttl_seconds: int = 86400) -> str:
        response = self.cache_table.get_item(Key={"cache_key": cache_key})
        item = response.get("Item")
        if item and item.get("ttl", 0) > int(time.time()):
            cached = item["scraped_content"]
            if _looks_like_error_page(cached):
                logger.warning("Poisoned cache entry detected for %s, deleting", cache_key)
                self.cache_table.delete_item(Key={"cache_key": cache_key})
            else:
                return cached

        try:
            resp = httpx.get(url, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("HTTP error scraping %s: %s", url, exc)
            return ""

        content = resp.text
        if _looks_like_error_page(content):
            logger.warning("Error page returned from %s, not caching", url)
            return ""

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        self.cache_table.put_item(Item={
            "cache_key": cache_key,
            "url": url,
            "scraped_content": content,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "ttl": int(time.time()) + ttl_seconds,
            "content_hash": f"sha256:{content_hash}",
        })
        return content

    def _fetch_cdl_with_cache(self, provider: str) -> str:
        cdl_url = PROVIDER_CDL_URLS.get(provider)
        if not cdl_url:
            return ""
        cache_key = f"{provider}:cdl"
        response = self.cache_table.get_item(Key={"cache_key": cache_key})
        item = response.get("Item")
        if item and item.get("ttl", 0) > int(time.time()):
            return item["scraped_content"]

        try:
            resp = httpx.get(cdl_url, timeout=60)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch CDL from %s: %s", cdl_url, exc)
            return ""

        try:
            import fitz
            pdf_bytes = resp.content
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            doc.close()
            content = "\n".join(text_parts)
        except Exception as exc:
            logger.warning("Failed to parse CDL PDF: %s", exc)
            return ""

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        self.cache_table.put_item(Item={
            "cache_key": cache_key,
            "url": cdl_url,
            "scraped_content": content[:50000],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "ttl": int(time.time()) + 86400 * 7,
            "content_hash": f"sha256:{content_hash}",
        })
        return content[:50000]

    def check_pa_requirements(self, provider: str, treatment: str) -> str:
        result = ""
        url = PROVIDER_URLS.get(provider)
        if url:
            cache_key = f"{provider}:pa_requirements:{treatment}"
            result = self.scrape_with_cache(cache_key, url)

        cdl_content = self._fetch_cdl_with_cache(provider)
        if cdl_content:
            treatment_lower = treatment.lower()
            cdl_lines = cdl_content.splitlines()
            relevant_lines = [
                line for line in cdl_lines
                if treatment_lower in line.lower()
            ]
            if relevant_lines:
                cdl_excerpt = "\n".join(relevant_lines[:20])
                result += f"\n\nCONTRACT DRUGS LIST ENTRIES FOR '{treatment}':\n{cdl_excerpt}"

        return result
