import aws_cdk as cdk
from aws_cdk import (
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as _lambda,
)
from constructs import Construct


class StepFunctionsConstruct(Construct):
    """Step Functions Express state machine with circuit breaker orchestration."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        circuit_breaker_fn: _lambda.Function,
        model_router_fn: _lambda.Function,
        fallback_fn: _lambda.Function,
        audit_logger_fn: _lambda.Function,
    ) -> None:
        super().__init__(scope, construct_id)

        def _audit_task(id_suffix: str) -> tasks.LambdaInvoke:
            return tasks.LambdaInvoke(
                self,
                f"AuditLog{id_suffix}",
                lambda_function=audit_logger_fn,
                payload=sfn.TaskInput.from_object(
                    {
                        "requestId": sfn.JsonPath.string_at("$.modelResult.requestId"),
                        "query": sfn.JsonPath.string_at("$.query"),
                        "useCase": sfn.JsonPath.string_at("$.useCase"),
                        "modelId": sfn.JsonPath.string_at("$.modelResult.modelId"),
                        "response": sfn.JsonPath.string_at("$.modelResult.response"),
                        "latencyMs": sfn.JsonPath.string_at("$.modelResult.latencyMs"),
                        "userIdentity": sfn.JsonPath.string_at("$.userIdentity"),
                        "success": True,
                    }
                ),
                result_path="$.auditResult",
            )

        def _fallback_task(id_suffix: str) -> tasks.LambdaInvoke:
            return tasks.LambdaInvoke(
                self,
                f"InvokeFallback{id_suffix}",
                lambda_function=fallback_fn,
                payload=sfn.TaskInput.from_object(
                    {"query": sfn.JsonPath.string_at("$.query"), "action": "fallback"}
                ),
                result_path="$.modelResult",
                result_selector={
                    "response.$": "$.Payload.response",
                    "modelId.$": "$.Payload.modelId",
                    "latencyMs.$": "$.Payload.latencyMs",
                    "requestId.$": "$.Payload.requestId",
                },
            )

        def _format_output(id_suffix: str) -> sfn.Pass:
            return sfn.Pass(
                self,
                f"FormatOutput{id_suffix}",
                parameters={
                    "response.$": "$.modelResult.response",
                    "modelId.$": "$.modelResult.modelId",
                    "latencyMs.$": "$.modelResult.latencyMs",
                    "requestId.$": "$.modelResult.requestId",
                },
            )

        # Step 1: Check circuit breaker
        check_circuit = tasks.LambdaInvoke(
            self,
            "CheckCircuitBreaker",
            lambda_function=circuit_breaker_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "action": "check",
                    "modelId": sfn.JsonPath.string_at("$.modelId"),
                    "circuitBreakerConfig": sfn.JsonPath.string_at("$.circuitBreakerConfig"),
                }
            ),
            result_path="$.circuitCheck",
            result_selector={"allowed.$": "$.Payload.allowed", "state.$": "$.Payload.state"},
        )

        # Step 2: Invoke primary model
        invoke_model = tasks.LambdaInvoke(
            self,
            "InvokeModel",
            lambda_function=model_router_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "query": sfn.JsonPath.string_at("$.query"),
                    "useCase": sfn.JsonPath.string_at("$.useCase"),
                    "modelId": sfn.JsonPath.string_at("$.modelId"),
                    "context": sfn.JsonPath.string_at("$.context"),
                }
            ),
            result_path="$.modelResult",
            result_selector={
                "response.$": "$.Payload.response",
                "modelId.$": "$.Payload.modelId",
                "latencyMs.$": "$.Payload.latencyMs",
                "requestId.$": "$.Payload.requestId",
            },
        ).add_catch(
            handler=sfn.Pass(self, "ModelFailedMarker", result=sfn.Result.from_object({"failed": True})),
            result_path="$.modelError",
        )

        # Success path: record success → cache → audit → output
        record_success = tasks.LambdaInvoke(
            self,
            "RecordSuccess",
            lambda_function=circuit_breaker_fn,
            payload=sfn.TaskInput.from_object(
                {"action": "record_success", "modelId": sfn.JsonPath.string_at("$.modelId")}
            ),
            result_path="$.circuitUpdate",
        )

        cache_response = tasks.LambdaInvoke(
            self,
            "CacheResponse",
            lambda_function=fallback_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "action": "cache_store",
                    "query": sfn.JsonPath.string_at("$.query"),
                    "response": sfn.JsonPath.string_at("$.modelResult.response"),
                    "modelId": sfn.JsonPath.string_at("$.modelResult.modelId"),
                }
            ),
            result_path="$.cacheResult",
        )

        success_path = record_success.next(cache_response).next(_audit_task("Success")).next(_format_output("Success"))

        # Failure path: record failure → fallback → audit → output
        record_failure = tasks.LambdaInvoke(
            self,
            "RecordFailure",
            lambda_function=circuit_breaker_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "action": "record_failure",
                    "modelId": sfn.JsonPath.string_at("$.modelId"),
                    "circuitBreakerConfig": sfn.JsonPath.string_at("$.circuitBreakerConfig"),
                }
            ),
            result_path="$.circuitUpdate",
        )

        failure_path = record_failure.next(_fallback_task("Failure")).next(_audit_task("Failure")).next(_format_output("Failure"))

        # Check if model invocation had an error
        check_model_error = sfn.Choice(self, "ModelSucceeded?")
        check_model_error.when(sfn.Condition.is_present("$.modelError"), failure_path)
        check_model_error.otherwise(success_path)

        invoke_model.next(check_model_error)

        # Circuit open path: fallback → audit → output
        circuit_open_path = _fallback_task("CircuitOpen").next(_audit_task("CircuitOpen")).next(_format_output("CircuitOpen"))

        # Circuit breaker routing
        circuit_choice = sfn.Choice(self, "CircuitAllowed?")
        circuit_choice.when(sfn.Condition.boolean_equals("$.circuitCheck.allowed", True), invoke_model)
        circuit_choice.otherwise(circuit_open_path)

        definition = check_circuit.next(circuit_choice)

        self.state_machine = sfn.StateMachine(
            self,
            "Orchestrator",
            state_machine_name="customer-service-ai-orchestrator",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            state_machine_type=sfn.StateMachineType.EXPRESS,
            timeout=cdk.Duration.seconds(30),
            tracing_enabled=True,
        )
