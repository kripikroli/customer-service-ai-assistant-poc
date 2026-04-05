import json
import os
import time
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.feature_flags import AppConfigStore, FeatureFlags

logger = Logger(service="model-router")

bedrock_runtime = boto3.client("bedrock-runtime")

# AppConfig integration
appconfig_store = AppConfigStore(
    environment=os.environ.get("APPCONFIG_ENV", "production"),
    application=os.environ.get("APPCONFIG_APP", "customer-service-ai"),
    name=os.environ.get("APPCONFIG_PROFILE", "model-routing"),
    max_age=300,
)

# Model-specific request formatters
SUPPORTED_MODELS = {
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "amazon.titan-text-express-v1",
    "mistral.mistral-large-2402-v1:0",
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


def _format_titan(query: str, context: str = "") -> dict:
    prompt = "You are a helpful customer service assistant for a financial services company.\n\n"
    if context:
        prompt += f"Context:\n{context}\n\n"
    prompt += f"User: {query}\nAssistant:"
    return {
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 1024,
            "temperature": 0.7,
            "topP": 0.9,
        },
    }


def _format_mistral(query: str, context: str = "") -> dict:
    system = "You are a helpful customer service assistant for a financial services company."
    if context:
        system += f"\n\nRelevant context:\n{context}"
    return {
        "prompt": f"<s>[INST] {system}\n\n{query} [/INST]",
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.9,
    }


def _get_formatter(model_id: str):
    if "anthropic" in model_id:
        return _format_claude
    if "titan" in model_id:
        return _format_titan
    if "mistral" in model_id:
        return _format_mistral
    raise ValueError(f"Unsupported model: {model_id}")


def _extract_response(model_id: str, body: dict) -> str:
    if "anthropic" in model_id:
        return body["content"][0]["text"]
    if "titan" in model_id:
        return body["results"][0]["outputText"]
    if "mistral" in model_id:
        return body["outputs"][0]["text"]
    raise ValueError(f"Unknown model: {model_id}")


def get_routing_config() -> dict:
    """Fetch model routing config from AppConfig."""
    raw = appconfig_store.get_raw_configuration()
    return json.loads(raw.get("features", raw) if isinstance(raw, dict) else raw)


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
