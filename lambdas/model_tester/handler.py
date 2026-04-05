"""Automated model testing Lambda — runs quality gates against new model endpoints."""

import json
import os
import time

import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="model-tester")

bedrock = boto3.client("bedrock-runtime")
sagemaker = boto3.client("sagemaker-runtime")
appconfig = boto3.client("appconfig")

TEST_QUESTIONS = [
    {"query": "What types of savings accounts do you offer?", "min_length": 50},
    {"query": "How do I dispute a credit card charge?", "min_length": 50},
    {"query": "What are the fees for wire transfers?", "min_length": 30},
]

QUALITY_THRESHOLD = 0.8
LATENCY_P95_THRESHOLD_S = 3.0


def test_bedrock_model(model_id: str) -> dict:
    latencies = []
    passed = 0

    for tq in TEST_QUESTIONS:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": tq["query"]}],
        }
        start = time.time()
        try:
            resp = bedrock.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            latency = time.time() - start
            latencies.append(latency)
            resp_body = json.loads(resp["body"].read())
            text = resp_body.get("content", [{}])[0].get("text", "")
            if len(text) >= tq["min_length"]:
                passed += 1
        except Exception as e:
            logger.error("Test failed", model_id=model_id, error=str(e))
            latencies.append(time.time() - start)

    quality_score = passed / len(TEST_QUESTIONS)
    latency_p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 999

    return {
        "quality_score": quality_score,
        "latency_p95": round(latency_p95, 3),
        "passed": quality_score >= QUALITY_THRESHOLD and latency_p95 <= LATENCY_P95_THRESHOLD_S,
        "details": {
            "tests_passed": passed,
            "total_tests": len(TEST_QUESTIONS),
            "latencies": [round(l, 3) for l in latencies],
        },
    }


def test_sagemaker_endpoint(endpoint_name: str) -> dict:
    latencies = []
    passed = 0

    for tq in TEST_QUESTIONS:
        payload = json.dumps({"inputs": tq["query"], "parameters": {"max_new_tokens": 512}})
        start = time.time()
        try:
            resp = sagemaker.invoke_endpoint(
                EndpointName=endpoint_name,
                ContentType="application/json",
                Body=payload,
            )
            latency = time.time() - start
            latencies.append(latency)
            result = json.loads(resp["Body"].read())
            text = result[0].get("generated_text", "") if isinstance(result, list) else str(result)
            if len(text) >= tq["min_length"]:
                passed += 1
        except Exception as e:
            logger.error("Test failed", endpoint=endpoint_name, error=str(e))
            latencies.append(time.time() - start)

    quality_score = passed / len(TEST_QUESTIONS)
    latency_p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 999

    return {
        "quality_score": quality_score,
        "latency_p95": round(latency_p95, 3),
        "passed": quality_score >= QUALITY_THRESHOLD and latency_p95 <= LATENCY_P95_THRESHOLD_S,
    }


@logger.inject_lambda_context
def handler(event, context):
    """Test a model and return pass/fail result."""
    model_type = event.get("modelType", "bedrock")
    model_id = event.get("modelId", "")
    endpoint_name = event.get("endpointName", "")

    if model_type == "bedrock":
        result = test_bedrock_model(model_id)
    elif model_type == "sagemaker":
        result = test_sagemaker_endpoint(endpoint_name)
    else:
        return {"error": f"Unknown model type: {model_type}"}

    logger.info("Test result", model_id=model_id or endpoint_name, result=result)
    return result
