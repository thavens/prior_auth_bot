"""Embedding Utility Handler.

Simple utility Lambda that generates a 1024-dimensional embedding vector
for a given text string using Amazon Titan Embed V2 via Bedrock.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

bedrock = BedrockClient()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Generate an embedding vector for the provided text.

    Event keys:
        text -- the input string to embed

    Returns:
        embedding  -- list of floats (1024 dimensions)
        dimensions -- integer (1024)
    """

    text: str = event["text"]

    logger.info("Generating embedding for text of length %d", len(text))
    embedding = bedrock.generate_embedding(text)

    return {
        "embedding": embedding,
        "dimensions": 1024,
    }
