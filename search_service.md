# Search Service

Provides search capabilities used by the [Agent Pipeline](agent_pipeline.md) for two purposes:

1. **Form Search** — Search for and choose the relevant blank forms to populate for a prior authorization application. Used by Agent Pipeline Step 3.
2. **Memory Search** — Search for and choose from relevant memories that would most likely help in the process of filling out the prior authorization form. Used by Agent Pipeline Step 4. See [Memory Feature](memory_feature.md) for the memory data structure.

## Requirements

- Results from web scraping must be cached so the system doesn't re-scrape every search.
- Search must support ranking by relevance to the current prior authorization context (treatment, provider, patient).
