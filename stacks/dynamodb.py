import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct


class DynamoDBConstruct(Construct):
    """DynamoDB tables for circuit breaker state and response cache."""

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        self.circuit_breaker_table = dynamodb.Table(
            self,
            "CircuitBreakerTable",
            table_name="circuit-breaker-state",
            partition_key=dynamodb.Attribute(name="model_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        self.response_cache_table = dynamodb.Table(
            self,
            "ResponseCacheTable",
            table_name="response-cache",
            partition_key=dynamodb.Attribute(name="cache_key", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )
