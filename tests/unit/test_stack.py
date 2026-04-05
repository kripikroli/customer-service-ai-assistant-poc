import aws_cdk as cdk
from aws_cdk.assertions import Template

from stacks.main_stack import CustomerServiceAIStack


def test_stack_creates_cognito_user_pool():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::Cognito::UserPool", 1)


def test_stack_creates_appsync_api():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::AppSync::GraphQLApi", 1)


def test_stack_creates_waf_web_acl():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::WAFv2::WebACL", 1)


def test_stack_creates_lambda_functions():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    # model_router, circuit_breaker, fallback, audit_logger, model_tester = 5
    # + index_creator + 2 custom resource framework lambdas = 8
    template.resource_count_is("AWS::Lambda::Function", 8)


def test_stack_creates_dynamodb_tables():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::DynamoDB::Table", 2)


def test_stack_creates_step_functions_state_machine():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)


def test_stack_creates_bedrock_guardrail():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::Bedrock::Guardrail", 1)


def test_stack_creates_bedrock_knowledge_base():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::Bedrock::KnowledgeBase", 1)


def test_stack_creates_appconfig_resources():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::AppConfig::Application", 1)
    template.resource_count_is("AWS::AppConfig::Environment", 1)
    template.resource_count_is("AWS::AppConfig::ConfigurationProfile", 1)


def test_cognito_password_policy():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {
            "Policies": {
                "PasswordPolicy": {
                    "MinimumLength": 12,
                    "RequireLowercase": True,
                    "RequireUppercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": True,
                }
            }
        },
    )


def test_waf_rate_limit_rule():
    app = cdk.App()
    stack = CustomerServiceAIStack(app, "TestStack")
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::WAFv2::WebACL",
        {
            "Rules": [
                {
                    "Name": "RateLimitRule",
                    "Statement": {
                        "RateBasedStatement": {
                            "Limit": 100,
                            "AggregateKeyType": "IP",
                        }
                    },
                }
            ]
        },
    )
