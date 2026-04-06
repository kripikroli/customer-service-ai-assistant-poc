import json
import os
import time
import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="model-router")

bedrock_runtime = boto3.client("bedrock-runtime")
bedrock_agent = boto3.client("bedrock-agent-runtime")
appconfig_client = boto3.client("appconfigdata")

KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "")


def retrieve_context(query: str) -> str:
    """Retrieve relevant context from Knowledge Base."""
    if not KNOWLEDGE_BASE_ID:
        return ""
    try:
        resp = bedrock_agent.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": 3}
            },
        )
        chunks = [r["content"]["text"] for r in resp.get("retrievalResults", [])]
        if chunks:
            context = "\n\n---\n\n".join(chunks)
            logger.info("Retrieved KB context", num_chunks=len(chunks))
            return context
    except Exception:
        logger.exception("Knowledge Base retrieval failed")
    return ""

# AppConfig session management
_appconfig_token = None
_cached_config = None
_config_fetched_at = 0
CONFIG_MAX_AGE = 300  # seconds


def get_routing_config() -> dict:
    """Fetch model routing config from AppConfig using the data plane API."""
    global _appconfig_token, _cached_config, _config_fetched_at

    now = time.time()
    if _cached_config and (now - _config_fetched_at) < CONFIG_MAX_AGE:
        return _cached_config

    if _appconfig_token is None:
        session = appconfig_client.start_configuration_session(
            ApplicationIdentifier=os.environ.get("APPCONFIG_APP", "customer-service-ai"),
            EnvironmentIdentifier=os.environ.get("APPCONFIG_ENV", "production"),
            ConfigurationProfileIdentifier=os.environ.get("APPCONFIG_PROFILE", "model-routing"),
        )
        _appconfig_token = session["InitialConfigurationToken"]

    resp = appconfig_client.get_latest_configuration(ConfigurationToken=_appconfig_token)
    _appconfig_token = resp["NextPollConfigurationToken"]

    content = resp["Configuration"].read()
    if content:
        _cached_config = json.loads(content)
        _config_fetched_at = now
        logger.info("AppConfig refreshed", config=_cached_config)

    if _cached_config is None:
        _cached_config = {"default_model": "us.anthropic.claude-sonnet-4-20250514-v1:0"}

    return _cached_config

# Model-specific request formatters
SUPPORTED_MODELS = {
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.amazon.nova-lite-v1:0",
    "us.amazon.nova-micro-v1:0",
}


def _format_claude(query: str, context: str = "") -> dict:
    messages = [{"role": "user", "content": query}]
    system = "You are a helpful customer service assistant for a financial services company."
    if context:
        system += f"\n\nRelevant context:\n{context}"
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": system,
        "messages": messages,
    }


def _format_nova(query: str, context: str = "") -> dict:
    system = "You are a helpful customer service assistant for a financial services company."
    if context:
        system += f"\n\nRelevant context:\n{context}"
    return {
        "messages": [{"role": "user", "content": [{"text": query}]}],
        "system": [{"text": system}],
        "inferenceConfig": {"maxTokens": 1024, "temperature": 0.7, "topP": 0.9},
    }


def _get_formatter(model_id: str):
    if "anthropic" in model_id:
        return _format_claude
    if "nova" in model_id:
        return _format_nova
    raise ValueError(f"Unsupported model: {model_id}")


def _extract_response(model_id: str, body: dict) -> str:
    if "anthropic" in model_id:
        return body["content"][0]["text"]
    if "nova" in model_id:
        return body["output"]["message"]["content"][0]["text"]
    raise ValueError(f"Unknown model: {model_id}")


def select_model(use_case: str, config: dict) -> str:
    """Select model based on use case and AppConfig rules."""
    overrides = config.get("use_case_overrides", {})
    return overrides.get(use_case, config.get("default_model", "us.anthropic.claude-sonnet-4-20250514-v1:0"))


def invoke_model(
    model_id: str,
    query: str,
    context: str = "",
    guardrail_id: str | None = None,
    guardrail_version: str | None = None,
) -> dict:
    """Invoke a Bedrock model with a consistent interface."""
    formatter = _get_formatter(model_id)
    body = formatter(query, context)

    invoke_kwargs = {
        "modelId": model_id,
        "contentType": "application/json",
        "accept": "application/json",
        "body": json.dumps(body),
    }
    if guardrail_id and guardrail_version:
        invoke_kwargs["guardrailIdentifier"] = guardrail_id
        invoke_kwargs["guardrailVersion"] = guardrail_version

    start = time.time()
    response = bedrock_runtime.invoke_model(**invoke_kwargs)
    latency_ms = int((time.time() - start) * 1000)

    response_body = json.loads(response["body"].read())
    text = _extract_response(model_id, response_body)

    return {
        "response": text,
        "model_id": model_id,
        "latency_ms": latency_ms,
    }


@logger.inject_lambda_context
def handler(event, context):
    """Lambda handler — invoked by Step Functions or AppSync resolver."""
    # AppSync resolver wraps args in event["arguments"]
    args = event.get("arguments", event)
    query = args.get("query", "")
    use_case = args.get("useCase", "general")
    doc_context = args.get("context", "")

    # Retrieve RAG context for product questions
    if use_case == "product_question" and not doc_context:
        doc_context = retrieve_context(query)
    guardrail_id = os.environ.get("GUARDRAIL_ID")
    guardrail_version = os.environ.get("GUARDRAIL_VERSION")

    # Get routing config and select model
    try:
        config = get_routing_config()
    except Exception:
        logger.exception("Failed to fetch AppConfig, using defaults")
        config = {"default_model": "us.anthropic.claude-sonnet-4-20250514-v1:0"}

    model_id = args.get("modelId") or select_model(use_case, config)
    logger.info("Routing request", model_id=model_id, use_case=use_case)
    result = invoke_model(
        model_id=model_id,
        query=query,
        context=doc_context,
        guardrail_id=guardrail_id,
        guardrail_version=guardrail_version,
    )
    result["requestId"] = context.aws_request_id
    result["useCase"] = use_case
    # Remap for GraphQL schema
    result["modelId"] = result.pop("model_id")
    result["latencyMs"] = result.pop("latency_ms")
    return result
