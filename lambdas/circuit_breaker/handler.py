"""Circuit breaker state management backed by DynamoDB."""

import os
import time
import boto3
from aws_lambda_powertools import Logger
from boto3.dynamodb.conditions import Attr

logger = Logger(service="circuit-breaker")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ.get("CIRCUIT_BREAKER_TABLE", "circuit-breaker-state"))

# States
CLOSED = "CLOSED"
OPEN = "OPEN"
HALF_OPEN = "HALF_OPEN"


def get_state(model_id: str) -> dict:
    """Get circuit breaker state for a model."""
    resp = table.get_item(Key={"model_id": model_id})
    if "Item" not in resp:
        return {"model_id": model_id, "state": CLOSED, "failure_count": 0}
    return resp["Item"]


def record_success(model_id: str):
    """Reset circuit breaker on success."""
    table.put_item(
        Item={
            "model_id": model_id,
            "state": CLOSED,
            "failure_count": 0,
            "last_success_time": int(time.time()),
        }
    )


def record_failure(model_id: str, threshold: int = 5) -> str:
    """Record a failure. Returns new state."""
    state = get_state(model_id)
    new_count = int(state.get("failure_count", 0)) + 1
    new_state = OPEN if new_count >= threshold else state.get("state", CLOSED)

    table.put_item(
        Item={
            "model_id": model_id,
            "state": new_state,
            "failure_count": new_count,
            "last_failure_time": int(time.time()),
        }
    )
    return new_state


def should_allow_request(model_id: str, recovery_timeout: int = 60) -> bool:
    """Check if a request should be allowed through."""
    state = get_state(model_id)
    circuit_state = state.get("state", CLOSED)

    if circuit_state == CLOSED:
        return True

    if circuit_state == OPEN:
        last_failure = int(state.get("last_failure_time", 0))
        if time.time() - last_failure > recovery_timeout:
            # Transition to half-open
            table.update_item(
                Key={"model_id": model_id},
                UpdateExpression="SET #s = :s",
                ExpressionAttributeNames={"#s": "state"},
                ExpressionAttributeValues={":s": HALF_OPEN},
            )
            return True
        return False

    # HALF_OPEN — allow limited requests
    return True


@logger.inject_lambda_context
def handler(event, context):
    """Lambda handler for circuit breaker checks."""
    action = event.get("action", "check")
    model_id = event.get("modelId")
    config = event.get("circuitBreakerConfig", {})
    threshold = config.get("failure_threshold", 5)
    recovery_timeout = config.get("recovery_timeout_seconds", 60)

    if action == "check":
        allowed = should_allow_request(model_id, recovery_timeout)
        state = get_state(model_id)
        return {
            "allowed": allowed,
            "state": state.get("state", CLOSED),
            "failureCount": int(state.get("failure_count", 0)),
        }
    elif action == "record_success":
        record_success(model_id)
        return {"state": CLOSED}
    elif action == "record_failure":
        new_state = record_failure(model_id, threshold)
        return {"state": new_state}

    return {"error": f"Unknown action: {action}"}
