"""Fallback handler with response caching for graceful degradation."""

import hashlib
import os
import time
import uuid

import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="fallback")

dynamodb = boto3.resource("dynamodb")
cache_table = dynamodb.Table(os.environ.get("RESPONSE_CACHE_TABLE", "response-cache"))

STATIC_FALLBACK = (
    "We're currently experiencing high demand and are unable to process your request in real time. "
    "Please try again shortly, or contact us at our support line for immediate assistance. "
    "Reference ID: {ref_id}"
)


def _cache_key(query: str) -> str:
    normalized = query.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def get_cached_response(query: str) -> dict | None:
    key = _cache_key(query)
    resp = cache_table.get_item(Key={"cache_key": key})
    item = resp.get("Item")
    if item and int(item.get("ttl", 0)) > int(time.time()):
        return {
            "response": item["response"],
            "modelId": item.get("model_id", "cache"),
            "latencyMs": 0,
            "cached": True,
        }
    return None


def store_cached_response(query: str, response: str, model_id: str, ttl_hours: int = 24):
    cache_table.put_item(
        Item={
            "cache_key": _cache_key(query),
            "query": query[:500],
            "response": response,
            "model_id": model_id,
            "ttl": int(time.time()) + (ttl_hours * 3600),
        }
    )


@logger.inject_lambda_context
def handler(event, context):
    """Fallback handler — try cache first, then static response."""
    query = event.get("query", "")
    action = event.get("action", "fallback")

    if action == "cache_store":
        store_cached_response(
            query=query,
            response=event.get("response", ""),
            model_id=event.get("modelId", ""),
        )
        return {"status": "cached"}

    # Try cached response
    cached = get_cached_response(query)
    if cached:
        logger.info("Returning cached response")
        cached["requestId"] = context.aws_request_id
        return cached

    # Static fallback
    ref_id = str(uuid.uuid4())[:8].upper()
    logger.warning("All models unavailable, returning static fallback", ref_id=ref_id)
    return {
        "response": STATIC_FALLBACK.format(ref_id=ref_id),
        "modelId": "fallback",
        "latencyMs": 0,
        "requestId": context.aws_request_id,
    }
