"""Audit logger for regulatory compliance — logs all interactions to CloudWatch and S3."""

import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="audit-logger")

s3 = boto3.client("s3")
AUDIT_BUCKET = os.environ.get("AUDIT_BUCKET", "")


def build_audit_record(event: dict) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "audit_id": str(uuid.uuid4()),
        "timestamp": now.isoformat(),
        "date_partition": now.strftime("%Y/%m/%d"),
        "request_id": event.get("requestId", ""),
        "user_identity": event.get("userIdentity", "anonymous"),
        "query": event.get("query", ""),
        "use_case": event.get("useCase", ""),
        "model_id": event.get("modelId", ""),
        "response_preview": event.get("response", "")[:500],
        "latency_ms": event.get("latencyMs", 0),
        "guardrail_action": event.get("guardrailAction", "none"),
        "circuit_breaker_state": event.get("circuitBreakerState", "CLOSED"),
        "success": event.get("success", True),
        "error": event.get("error"),
    }


@logger.inject_lambda_context
def handler(event, context):
    """Log audit record to CloudWatch (structured) and S3 (long-term)."""
    record = build_audit_record(event)

    # Structured log to CloudWatch
    logger.info("AUDIT", extra=record)

    # Persist to S3 for long-term retention
    if AUDIT_BUCKET:
        key = f"audit-logs/{record['date_partition']}/{record['audit_id']}.json"
        s3.put_object(
            Bucket=AUDIT_BUCKET,
            Key=key,
            Body=json.dumps(record),
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
        )

    return {"status": "logged", "auditId": record["audit_id"]}
