"""Bedrock model benchmarking framework for financial domain evaluation."""

import json
import statistics
import sys
import time
from datetime import datetime, timezone

import boto3

from benchmarks.test_data import BENCHMARK_QUESTIONS

MODELS = [
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "amazon.titan-text-express-v1",
    "mistral.mistral-large-2402-v1:0",
]

# Approximate cost per 1K tokens (input/output) in USD
TOKEN_COSTS = {
    "us.anthropic.claude-sonnet-4-20250514-v1:0": {"input": 0.003, "output": 0.015},
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": {"input": 0.0008, "output": 0.004},
    "amazon.titan-text-express-v1": {"input": 0.0002, "output": 0.0006},
    "mistral.mistral-large-2402-v1:0": {"input": 0.004, "output": 0.012},
}

COMPLIANCE_KEYWORDS_BLOCK = [
    "guaranteed returns",
    "you will make money",
    "risk-free investment",
    "i promise",
]

bedrock = boto3.client("bedrock-runtime")


def _format_request(model_id: str, query: str) -> dict:
    if "anthropic" in model_id:
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": "You are a helpful customer service assistant for a financial services company.",
            "messages": [{"role": "user", "content": query}],
        }
    if "titan" in model_id:
        return {
            "inputText": f"You are a helpful customer service assistant.\n\nUser: {query}\nAssistant:",
            "textGenerationConfig": {"maxTokenCount": 1024, "temperature": 0.7, "topP": 0.9},
        }
    if "mistral" in model_id:
        return {
            "prompt": f"<s>[INST] You are a helpful customer service assistant.\n\n{query} [/INST]",
            "max_tokens": 1024,
            "temperature": 0.7,
            "top_p": 0.9,
        }
    raise ValueError(f"Unsupported model: {model_id}")


def _extract_text(model_id: str, body: dict) -> str:
    if "anthropic" in model_id:
        return body["content"][0]["text"]
    if "titan" in model_id:
        return body["results"][0]["outputText"]
    if "mistral" in model_id:
        return body["outputs"][0]["text"]
    raise ValueError(f"Unknown model: {model_id}")


def _estimate_tokens(text: str) -> int:
    return len(text.split()) * 4 // 3  # rough approximation


def invoke_and_measure(model_id: str, query: str) -> dict:
    body = _format_request(model_id, query)
    start = time.time()
    try:
        resp = bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        latency = time.time() - start
        resp_body = json.loads(resp["body"].read())
        text = _extract_text(model_id, resp_body)
        input_tokens = _estimate_tokens(query)
        output_tokens = _estimate_tokens(text)
        costs = TOKEN_COSTS.get(model_id, {"input": 0, "output": 0})
        cost = (input_tokens / 1000) * costs["input"] + (output_tokens / 1000) * costs["output"]
        return {
            "success": True,
            "response": text,
            "latency_s": round(latency, 3),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(cost, 6),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "latency_s": time.time() - start}


def check_compliance(response_text: str, expected_traits: list[str]) -> dict:
    text_lower = response_text.lower()
    violations = [kw for kw in COMPLIANCE_KEYWORDS_BLOCK if kw in text_lower]
    trait_checks = {}
    if "no_guarantees" in expected_traits:
        trait_checks["no_guarantees"] = len(violations) == 0
    if "no_pii_echo" in expected_traits:
        trait_checks["no_pii_echo"] = "<ssn>" not in text_lower and "ssn" not in text_lower
    if "includes_disclaimer" in expected_traits:
        trait_checks["includes_disclaimer"] = any(
            w in text_lower for w in ["disclaimer", "consult", "professional", "not financial advice", "subject to"]
        )
    return {"violations": violations, "trait_checks": trait_checks}


def run_benchmark(models: list[str] | None = None, questions: list[dict] | None = None):
    models = models or MODELS
    questions = questions or BENCHMARK_QUESTIONS
    results = {}

    for model_id in models:
        print(f"\n{'='*60}")
        print(f"Benchmarking: {model_id}")
        print(f"{'='*60}")
        model_results = []

        for q in questions:
            print(f"  [{q['id']}] {q['query'][:60]}...", end=" ", flush=True)
            result = invoke_and_measure(model_id, q["query"])

            if result["success"]:
                compliance = check_compliance(result["response"], q.get("expected_traits", []))
                result["compliance"] = compliance
                print(f"OK ({result['latency_s']}s)")
            else:
                print(f"FAIL: {result['error'][:50]}")

            result["question_id"] = q["id"]
            model_results.append(result)

        # Aggregate stats
        successful = [r for r in model_results if r["success"]]
        latencies = [r["latency_s"] for r in successful]
        costs = [r["estimated_cost_usd"] for r in successful]

        results[model_id] = {
            "individual_results": model_results,
            "summary": {
                "total_questions": len(questions),
                "successful": len(successful),
                "failed": len(model_results) - len(successful),
                "latency_p50": round(statistics.median(latencies), 3) if latencies else None,
                "latency_p95": round(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 3),
                "latency_p99": round(sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0, 3),
                "avg_cost_per_request": round(statistics.mean(costs), 6) if costs else None,
                "total_cost": round(sum(costs), 6) if costs else None,
            },
        }

    return results


def print_summary(results: dict):
    print(f"\n{'='*80}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*80}")
    header = f"{'Model':<50} {'Success':>7} {'P50(s)':>7} {'P95(s)':>7} {'Avg Cost':>10}"
    print(header)
    print("-" * 80)
    for model_id, data in results.items():
        s = data["summary"]
        print(
            f"{model_id:<50} {s['successful']:>4}/{s['total_questions']:<3}"
            f" {s['latency_p50'] or 'N/A':>7}"
            f" {s['latency_p95'] or 'N/A':>7}"
            f" ${s['avg_cost_per_request'] or 0:>8.6f}"
        )


if __name__ == "__main__":
    selected_models = sys.argv[1:] if len(sys.argv) > 1 else None
    results = run_benchmark(models=selected_models)
    print_summary(results)

    report_path = f"benchmarks/report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        # Strip full response text for report size
        for model_data in results.values():
            for r in model_data["individual_results"]:
                if "response" in r:
                    r["response_preview"] = r["response"][:200]
                    del r["response"]
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull report saved to: {report_path}")
