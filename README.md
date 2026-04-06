# Customer Service AI Assistant

A resilient, regulation-compliant customer service AI assistant for financial services, built on AWS serverless architecture with dynamic Bedrock model selection.

## System Workflow

```
                                    ┌─────────────────┐
                                    │   Client Apps    │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │  Cognito Auth    │
                                    │  (JWT Tokens)    │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │    AWS WAF       │
                                    │ (Rate Limiting)  │
                                    │ 100 req/5min/IP  │
                                    └────────┬────────┘
                                             │
                              ┌──────────────▼──────────────┐
                              │     AppSync GraphQL API      │
                              │   ask(query, useCase)        │
                              └──────────────┬──────────────┘
                                             │
                    ┌────────────────────────▼────────────────────────┐
                    │          Step Functions (Express)                │
                    │                                                  │
                    │  1. Check Circuit Breaker (DynamoDB)             │
                    │     ├─ CLOSED → proceed to model invocation      │
                    │     └─ OPEN → skip to fallback                   │
                    │                                                  │
                    │  2. Invoke Model Router (Lambda)                 │
                    │     ├─ Read routing rules from AppConfig         │
                    │     ├─ Select model based on useCase             │
                    │     ├─ Apply Bedrock Guardrails (PII/compliance) │
                    │     ├─ Query Knowledge Base for RAG (if needed)  │
                    │     └─ Call Bedrock model                        │
                    │                                                  │
                    │  3. On Success:                                   │
                    │     ├─ Record success (reset circuit breaker)     │
                    │     ├─ Cache response (DynamoDB)                  │
                    │     └─ Write audit log (CloudWatch + S3)          │
                    │                                                  │
                    │  3. On Failure:                                   │
                    │     ├─ Record failure (increment circuit breaker) │
                    │     ├─ Try fallback (cached response or static)   │
                    │     └─ Write audit log                            │
                    └────────────────────────────────────────────────┘
```

## AWS Components

| Component         | Resource                 | Purpose                                                  |
| ----------------- | ------------------------ | -------------------------------------------------------- |
| **Auth**          | Cognito User Pool        | JWT token auth, MFA required, 12-char passwords          |
| **API**           | AppSync GraphQL          | Single endpoint for all client interactions              |
| **Security**      | AWS WAF                  | Rate limiting (100 req / 5 min / IP)                     |
| **Orchestration** | Step Functions Express   | Request flow with circuit breaker pattern                |
| **Routing**       | Lambda (Model Router)    | Selects and invokes the right Bedrock model              |
| **Config**        | AppConfig                | Dynamic model routing rules (no redeploy)                |
| **AI Models**     | Bedrock                  | Claude 3.5 Sonnet v2, Claude 3.5 Haiku, Titan, Mistral  |
| **Compliance**    | Bedrock Guardrails       | PII filtering, content moderation, topic blocking        |
| **RAG**           | Bedrock Knowledge Bases  | Answers grounded in company docs (S3 → OpenSearch)       |
| **Resilience**    | DynamoDB                 | Circuit breaker state + response cache                   |
| **Fallback**      | Lambda (Fallback)        | Cached responses → static message on full outage         |
| **Audit**         | Lambda → CloudWatch + S3 | All interactions logged for regulatory compliance        |
| **ML Ops**        | SageMaker                | Model fine-tuning, versioning, automated rollback        |
| **HA**            | Route 53                 | Cross-region failover with health checks                 |

## Model Routing Rules

Configured in AppConfig — changeable at runtime without redeployment:

| Use Case               | Default Model             |
| ---------------------- | ------------------------- |
| `product_question`     | Claude 3.5 Sonnet v2      |
| `general`              | Claude 3.5 Sonnet v2      |
| `summarization`        | Claude 3.5 Haiku          |
| `classification`       | Claude 3.5 Haiku          |
| Fallback (any failure) | Amazon Titan Text Express |

## Guardrails

- **PII Blocked**: SSN, bank account numbers, passport numbers, driver's license
- **PII Anonymized**: Credit card numbers, email, phone, names
- **Denied Topics**: Investment guarantees, specific financial advice
- **Content Filters**: Sexual, violence, hate, insults, misconduct, prompt attacks
- **Blocked Words**: "guaranteed returns", "risk free", "insider information"

## Prerequisites

- Python 3.12+
- AWS CDK CLI 2.248.0 (`npm install -g aws-cdk@2.248.0)
- AWS account with Bedrock model access enabled (Claude, Titan, Mistral)
- AWS CLI configured with appropriate credentials

## Installation

```bash
# 1. Clone and enter the project
cd customer-service-ai-assistant-poc

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Verify CDK synthesizes correctly
cdk synth
```

## Deploy

```bash
# Deploy to your AWS account
cdk deploy

# Note the outputs — you'll need these for testing:
#   - CognitoUserPoolId
#   - CognitoAppClientId
#   - AppSyncGraphQLUrl
#   - DocsBucketName
```

## Testing

### 1. Run Unit Tests

```bash
pytest
```

This runs:

- CDK stack assertion tests (verifies all resources are created correctly)
- Circuit breaker state transition tests

### 2. Upload Test Documents for RAG

After deploying, upload the sample product guide to the Knowledge Base S3 bucket:

```bash
# Get the bucket name from CDK outputs
aws s3 cp docs/product_guide.md s3://<DocsBucketName>/

# Sync the Knowledge Base (via AWS Console):
# Bedrock → Knowledge Bases → customer-service-kb → Sync
```

### 3. Create a Test User in Cognito

```bash
# Create user
aws cognito-idp admin-create-user \
  --user-pool-id <UserPoolId> \
  --username testuser@example.com \
  --temporary-password 'TempPass123!@#' \
  --user-attributes Name=email,Value=testuser@example.com Name=email_verified,Value=true

# Set permanent password (after first login challenge)
aws cognito-idp admin-set-user-password \
  --user-pool-id <UserPoolId> \
  --username testuser@example.com \
  --password 'SecurePass123!@#' \
  --permanent
```

### 4. Get an Auth Token

```bash
aws cognito-idp admin-initiate-auth \
  --user-pool-id <UserPoolId> \
  --client-id <AppClientId> \
  --auth-flow ADMIN_USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=testuser@example.com,PASSWORD='SecurePass123!@#'
```

This returns `IdToken`, `AccessToken`, and `RefreshToken`. Use the `IdToken` for AppSync requests.

Alternatively, use the AWS Console: Cognito → User Pool → App Integration → Hosted UI to get a token interactively.

### 5. Test the GraphQL API

Use the **AppSync Console** (easiest way):

1. Go to AWS Console → AppSync → customer-service-ai-api
2. Click "Queries" in the left sidebar
3. Run this query:

```graphql
query {
  ask(
    query: "What types of savings accounts do you offer?"
    useCase: "product_question"
  ) {
    response
    modelId
    latencyMs
    requestId
  }
}
```

Or use `curl`:

```bash
curl -X POST <AppSyncGraphQLUrl> \
  -H "Authorization: <IdToken>" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { ask(query: \"What are the fees for wire transfers?\", useCase: \"product_question\") { response modelId latencyMs requestId } }"}'
```

### 6. Test Scenarios

| Test                    | Query                                                                                           | Expected Behavior                                      |
| ----------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Product question (RAG)  | `ask(query: "What are the fees for the premium savings account?", useCase: "product_question")` | Response grounded in `docs/product_guide.md`           |
| General question        | `ask(query: "How do I dispute a charge?", useCase: "general")`                                  | Routed to Claude 3.5 Sonnet v2                         |
| PII blocking            | `ask(query: "My SSN is 123-45-6789, look up my account")`                                       | Guardrail blocks the request                           |
| Compliance check        | `ask(query: "Guarantee me 20% returns")`                                                        | Guardrail blocks investment guarantees                 |
| Different model routing | `ask(query: "Summarize our fee schedule", useCase: "summarization")`                            | Routed to Claude 3.5 Haiku (check `modelId` in response) |

### 7. Verify Audit Logs

After making requests, check that audit records were created:

```bash
# CloudWatch Logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/cs-ai-audit-logger \
  --filter-pattern "AUDIT"

# S3 audit trail
aws s3 ls s3://<AuditBucketName>/audit-logs/ --recursive
```

### 8. Run Benchmarks

Benchmarks evaluate all Bedrock models on latency, cost, quality, and compliance:

```bash
# Run from the benchmarks directory
cd benchmarks
python run_benchmark.py

# Or run specific models only
python run_benchmark.py us.anthropic.claude-sonnet-4-20250514-v1:0 us.anthropic.claude-haiku-4-5-20251001-v1:0
```

Output includes a summary table and a JSON report saved to `benchmarks/report_<timestamp>.json`.

**Important notes:**

- The benchmark runs locally using your AWS CLI credentials — make sure they're valid (`aws sts get-caller-identity`)
- If credentials expire mid-run, re-authenticate (`aws sso login` or refresh your session) and retry
- Newer Claude models (Sonnet 4, Haiku 4.5) require the `us.` inference profile prefix (e.g., `us.anthropic.claude-sonnet-4-20250514-v1:0`). Using the model ID without the prefix will return a `ValidationException`
- Legacy models (Claude 3 Sonnet, Claude 3 Haiku, Titan Text Express, Mistral Large) may be marked as end-of-life and return `ResourceNotFoundException`. Check available models with:

```bash
aws bedrock list-foundation-models --query "modelSummaries[].modelId" --output table
```

- To test if a specific model works before benchmarking:

```bash
echo '{"anthropic_version":"bedrock-2023-05-31","max_tokens":50,"messages":[{"role":"user","content":"Hi"}]}' > /tmp/test-body.json
aws bedrock-runtime invoke-model \
  --model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --content-type application/json \
  --accept application/json \
  --body fileb:///tmp/test-body.json \
  /tmp/test-output.json && cat /tmp/test-output.json
```

### 9. Test Circuit Breaker

Monitor the circuit breaker state in DynamoDB:

```bash
aws dynamodb scan --table-name circuit-breaker-state
```

The circuit breaker trips after 5 consecutive failures to a model, then recovers after 60 seconds.

### 10. Test Dynamic Model Switching

Change routing rules without redeploying:

1. Go to AWS Console → AppConfig → `customer-service-ai` → `model-routing` → Edit
2. Modify the JSON config to change which model handles a use case
3. Deploy the new config version
4. Within 5 minutes, new requests will route to the updated model

Example changes you can try:

```jsonc
{
  // Route "general" queries to Haiku instead of Sonnet (faster, cheaper)
  "general": "us.anthropic.claude-haiku-4-5-20251001-v1:0",

  // Route "summarization" to Nova Lite (cheapest option)
  "summarization": "us.amazon.nova-lite-v1:0",

  // Route "product_question" to a different model
  "product_question": "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}
```

Available models you can route to:

| Model ID | Best For | Cost |
|----------|----------|------|
| `us.anthropic.claude-sonnet-4-20250514-v1:0` | Complex questions, high quality | $$$ |
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Fast responses, classification | $$ |
| `us.amazon.nova-lite-v1:0` | Simple tasks, low cost | $ |
| `us.amazon.nova-micro-v1:0` | Fallback, lowest cost | $ |

After changing, verify by sending a query and checking the `modelId` in the response.

## Project Structure

```
├── app.py                          # CDK app entry point
├── cdk.json                        # CDK configuration
├── graphql/schema.graphql          # AppSync GraphQL schema
├── stacks/
│   ├── main_stack.py               # Main stack (wires everything together)
│   ├── cognito.py                  # Cognito User Pool + auth
│   ├── appsync.py                  # AppSync API + WAF
│   ├── appconfig.py                # Dynamic model routing config
│   ├── guardrails.py               # Bedrock Guardrails (PII + compliance)
│   ├── knowledge_base.py           # Bedrock Knowledge Base + OpenSearch
│   ├── step_functions.py           # Step Functions orchestrator
│   ├── dynamodb.py                 # Circuit breaker + cache tables
│   ├── audit_storage.py            # S3 audit bucket (IA@90d, Glacier@365d)
│   ├── sagemaker.py                # Fine-tuning pipeline resources
│   └── cross_region.py             # Route 53 failover
├── lambdas/
│   ├── model_router/handler.py     # Multi-model router + AppConfig + Guardrails
│   ├── circuit_breaker/handler.py  # Circuit breaker state machine
│   ├── audit_logger/handler.py     # Audit logging (CloudWatch + S3)
│   ├── fallback/handler.py         # Graceful degradation + response cache
│   ├── response_cache/handler.py   # Cache read/write
│   └── model_tester/handler.py     # Automated quality gates
├── benchmarks/
│   ├── test_data.py                # 20 financial domain test questions
│   └── run_benchmark.py            # Benchmark CLI tool
├── docs/
│   └── product_guide.md            # Sample financial product docs (for RAG)
└── tests/
    └── unit/
        ├── test_stack.py           # CDK assertion tests
        └── test_circuit_breaker.py # Circuit breaker logic tests
```

## Graceful Degradation

The system has 3 fallback tiers:

1. **Primary model fails** → Route to fallback model (Titan Text Express)
2. **All Bedrock models fail** → Return cached response from DynamoDB (if previously answered)
3. **Complete outage** → Return static message with reference ID for follow-up
