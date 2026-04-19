# Search Service

Provides search capabilities used by the [Agent Pipeline](agent_pipeline.md) for two purposes:

1. **Form Search** — Search for and choose the relevant blank forms to populate for a prior authorization application. Used by Agent Pipeline Step 3.
2. **Memory Search** — Search for and choose from relevant memories that would most likely help in the process of filling out the prior authorization form. Used by Agent Pipeline Step 4. See [Memory Feature](memory_feature.md) for the memory data structure.

## Requirements

- Results from web scraping must be cached so the system doesn't re-scrape every search.
- Search must support ranking by relevance to the current prior authorization context (treatment, provider, patient).

## AWS Ownership

This spec owns:
- **DynamoDB: `pa_scrape_cache`** — TTL-based cache for web scraping results. Prevents redundant scraping on repeated searches.

This spec reads from:
- **DynamoDB: `pa_memories`** (owned by [Memory Feature](memory_feature.md)) — For memory search queries.
- **S3: `pa-blank-forms`** (owned by [Document Download](document_download.md)) — For form search queries.

## Scrape Cache Schema (DynamoDB `pa_scrape_cache`)

```json
{
  "cache_key": "medi-cal:pa_requirements:adalimumab",
  "url": "https://medi-calrx.dhcs.ca.gov/provider/forms/",
  "scraped_content": "...extracted text from the page...",
  "scraped_at": "2026-04-18T12:00:00Z",
  "ttl": 1713532800,
  "content_hash": "sha256:abc123..."
}
```

- PK: `cache_key`
- TTL attribute: `ttl` (epoch seconds, auto-expires stale entries)
