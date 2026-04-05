import json
import aws_cdk as cdk
from aws_cdk import aws_appconfig as appconfig
from constructs import Construct

DEFAULT_CONFIG = {
    "default_model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "fallback_model": "us.amazon.nova-micro-v1:0",
    "use_case_overrides": {
        "summarization": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "product_question": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "classification": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "general": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    },
    "circuit_breaker": {
        "failure_threshold": 5,
        "recovery_timeout_seconds": 60,
        "half_open_max_requests": 3,
    },
}


class AppConfigConstruct(Construct):
    """AppConfig for dynamic model selection rules."""

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        self.application = appconfig.CfnApplication(
            self, "App", name="customer-service-ai"
        )

        self.environment = appconfig.CfnEnvironment(
            self,
            "Env",
            application_id=self.application.ref,
            name="production",
        )

        self.config_profile = appconfig.CfnConfigurationProfile(
            self,
            "Profile",
            application_id=self.application.ref,
            name="model-routing",
            location_uri="hosted",
        )

        self.hosted_config = appconfig.CfnHostedConfigurationVersion(
            self,
            "HostedConfig",
            application_id=self.application.ref,
            configuration_profile_id=self.config_profile.ref,
            content=json.dumps(DEFAULT_CONFIG),
            content_type="application/json",
        )

        # Instant deployment strategy (for dev; use gradual for prod)
        self.deployment_strategy = appconfig.CfnDeploymentStrategy(
            self,
            "DeployStrategy",
            name="Instant",
            deployment_duration_in_minutes=0,
            growth_factor=100,
            replicate_to="NONE",
            final_bake_time_in_minutes=0,
        )

        self.deployment = appconfig.CfnDeployment(
            self,
            "Deployment",
            application_id=self.application.ref,
            environment_id=self.environment.ref,
            configuration_profile_id=self.config_profile.ref,
            configuration_version=self.hosted_config.ref,
            deployment_strategy_id=self.deployment_strategy.ref,
        )

        self.app_id = self.application.ref
        self.env_id = self.environment.ref
        self.profile_name = "model-routing"
