import os
import aws_cdk as cdk
from aws_cdk import (
    aws_appsync as appsync,
    aws_wafv2 as wafv2,
    aws_lambda as _lambda,
    aws_iam as iam,
)
from constructs import Construct


class AppSyncConstruct(Construct):
    """AppSync GraphQL API with Cognito auth, WAF rate limiting, and Lambda resolver."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        user_pool,
        model_router_fn: _lambda.Function,
    ) -> None:
        super().__init__(scope, construct_id)

        schema_path = os.path.join(os.path.dirname(__file__), "..", "graphql", "schema.graphql")

        self.api = appsync.GraphqlApi(
            self,
            "Api",
            name="customer-service-ai-api",
            definition=appsync.Definition.from_file(schema_path),
            authorization_config=appsync.AuthorizationConfig(
                default_authorization=appsync.AuthorizationMode(
                    authorization_type=appsync.AuthorizationType.USER_POOL,
                    user_pool_config=appsync.UserPoolConfig(
                        user_pool=user_pool,
                    ),
                ),
            ),
            log_config=appsync.LogConfig(
                field_log_level=appsync.FieldLogLevel.ERROR,
            ),
            xray_enabled=True,
        )

        # Lambda data source and resolver
        ds = self.api.add_lambda_data_source("ModelRouterDS", model_router_fn)
        ds.create_resolver("AskResolver", type_name="Query", field_name="ask")

        # WAF WebACL with rate limiting
        rate_rule = wafv2.CfnWebACL.RuleProperty(
            name="RateLimitRule",
            priority=1,
            action=wafv2.CfnWebACL.RuleActionProperty(block={}),
            statement=wafv2.CfnWebACL.StatementProperty(
                rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                    limit=100,
                    aggregate_key_type="IP",
                ),
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name="RateLimitRule",
            ),
        )

        self.web_acl = wafv2.CfnWebACL(
            self,
            "WebACL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            scope="REGIONAL",
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name="CustomerServiceAI-WAF",
            ),
            rules=[rate_rule],
        )

        wafv2.CfnWebACLAssociation(
            self,
            "WebACLAssociation",
            resource_arn=self.api.arn,
            web_acl_arn=self.web_acl.attr_arn,
        )

        cdk.CfnOutput(self, "GraphQLUrl", value=self.api.graphql_url)
