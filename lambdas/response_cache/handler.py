"""Response cache Lambda — stores and retrieves cached responses."""

import os
from lambdas.fallback.handler import get_cached_response, store_cached_response
from aws_lambda_powertools import Logger

logger = Logger(service="response-cache")


def handler(event, context):
    """Thin wrapper — delegates to fallback cache logic."""
    action = event.get("action", "get")
    query = event.get("query", "")

    if action == "store":
        store_cached_response(
            query=query,
            response=event.get("response", ""),
            model_id=event.get("modelId", ""),
            ttl_hours=event.get("ttlHours", 24),
        )
        return {"status": "stored"}

    cached = get_cached_response(query)
    return cached or {"status": "miss"}
