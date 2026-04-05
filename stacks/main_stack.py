import os
import aws_cdk as cdk
from aws_cdk import aws_lambda as _lambda, aws_iam as iam, aws_logs as logs
from constructs import Construct

from stacks.cognito import CognitoConstruct
from stacks.appsync import AppSyncConstruct
from stacks.appconfig import AppConfigConstruct
from stacks.guardrails import GuardrailsConstruct
from stacks.knowledge_base import KnowledgeBaseConstruct
from stacks.dynamodb import DynamoDBConstruct
from stacks.audit_storage import AuditStorageConstruct
from stacks.step_functions import StepFunctionsConstruct
from stacks.sagemaker import SageMakerConstruct

LAMBDA_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas")


class CustomerServiceAIStack(cdk.Stack):
    """Main stack for the Customer Service AI Assistant."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cdk.Tags.of(self).add("Project", "CustomerServiceAI")
        cdk.Tags.of(self).add("Environment", "dev")

        # --- Foundation constructs ---
        cognito = CognitoConstruct(self, "Cognito")
        app_config = AppConfigConstruct(self, "AppConfig")
        guardrails = GuardrailsConstruct(self, "Guardrails")
        knowledge_base = KnowledgeBaseConstruct(self, "KnowledgeBase")
        dynamo = DynamoDBConstruct(self, "DynamoDB")
        audit_storage = AuditStorageConstruct(self, "AuditStorage")
        sagemaker = SageMakerConstruct(self, "SageMaker")

        # --- Shared Lambda layer for powertools ---
        powertools_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "PowertoolsLayer",
            f"arn:aws:lambda:{self.region}:017000801446:layer:AWSLambdaPowertoolsPythonV2:79",
        )

        lambda_defaults = dict(
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            layers=[powertools_layer],
            log_retention=logs.RetentionDays.ONE_MONTH,
        )

        # --- Lambda functions ---
        model_router_fn = _lambda.Function(
            self,
            "ModelRouterFn",
            function_name="cs-ai-model-router",
            handler="handler.handler",
            code=_lambda.Code.from_asset(os.path.join(LAMBDA_DIR, "model_router")),
            environment={
                "APPCONFIG_APP": app_config.app_id,
                "APPCONFIG_ENV": app_config.env_id,
                "APPCONFIG_PROFILE": app_config.profile_name,
                "GUARDRAIL_ID": guardrails.guardrail_id,
                "GUARDRAIL_VERSION": guardrails.version,
                "KNOWLEDGE_BASE_ID": knowledge_base.knowledge_base_id,
            },
            **lambda_defaults,
        )
        model_router_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"])
        )
        model_router_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
                resources=["*"],
            )
        )
        model_router_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["appconfig:GetLatestConfiguration", "appconfig:StartConfigurationSession"],
                resources=["*"],
            )
        )
        model_router_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["bedrock:ApplyGuardrail"], resources=["*"])
        )

        circuit_breaker_fn = _lambda.Function(
            self,
            "CircuitBreakerFn",
            function_name="cs-ai-circuit-breaker",
            handler="handler.handler",
            code=_lambda.Code.from_asset(os.path.join(LAMBDA_DIR, "circuit_breaker")),
            environment={"CIRCUIT_BREAKER_TABLE": dynamo.circuit_breaker_table.table_name},
            **lambda_defaults,
        )
        dynamo.circuit_breaker_table.grant_read_write_data(circuit_breaker_fn)

        fallback_fn = _lambda.Function(
            self,
            "FallbackFn",
            function_name="cs-ai-fallback",
            handler="handler.handler",
            code=_lambda.Code.from_asset(os.path.join(LAMBDA_DIR, "fallback")),
            environment={"RESPONSE_CACHE_TABLE": dynamo.response_cache_table.table_name},
            **lambda_defaults,
        )
        dynamo.response_cache_table.grant_read_write_data(fallback_fn)

        audit_logger_fn = _lambda.Function(
            self,
            "AuditLoggerFn",
            function_name="cs-ai-audit-logger",
            handler="handler.handler",
            code=_lambda.Code.from_asset(os.path.join(LAMBDA_DIR, "audit_logger")),
            environment={"AUDIT_BUCKET": audit_storage.audit_bucket.bucket_name},
            **lambda_defaults,
        )
        audit_storage.audit_bucket.grant_write(audit_logger_fn)

        model_tester_fn = _lambda.Function(
            self,
            "ModelTesterFn",
            function_name="cs-ai-model-tester",
            handler="handler.handler",
            code=_lambda.Code.from_asset(os.path.join(LAMBDA_DIR, "model_tester")),
            environment={},
            timeout=cdk.Duration.minutes(5),
            **{k: v for k, v in lambda_defaults.items() if k != "timeout"},
        )
        model_tester_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"])
        )
        model_tester_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["sagemaker:InvokeEndpoint"], resources=["*"])
        )

        # --- Step Functions orchestrator ---
        step_functions = StepFunctionsConstruct(
            self,
            "StepFunctions",
            circuit_breaker_fn=circuit_breaker_fn,
            model_router_fn=model_router_fn,
            fallback_fn=fallback_fn,
            audit_logger_fn=audit_logger_fn,
        )

        # --- AppSync API ---
        appsync = AppSyncConstruct(
            self,
            "AppSync",
            user_pool=cognito.user_pool,
            model_router_fn=model_router_fn,
        )

        # --- Outputs ---
        cdk.CfnOutput(self, "StateMachineArn", value=step_functions.state_machine.state_machine_arn)
        cdk.CfnOutput(self, "DocsBucketName", value=knowledge_base.docs_bucket.bucket_name)
        cdk.CfnOutput(self, "AuditBucketName", value=audit_storage.audit_bucket.bucket_name)
        cdk.CfnOutput(self, "TrainingBucketName", value=sagemaker.training_bucket.bucket_name)
