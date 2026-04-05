import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class CognitoConstruct(Construct):
    """Cognito User Pool with financial-services-grade security."""

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="customer-service-ai-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=cdk.Duration.days(1),
            ),
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=True, otp=True),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            advanced_security_mode=cognito.AdvancedSecurityMode.ENFORCED,
        )

        self.app_client = self.user_pool.add_client(
            "AppClient",
            user_pool_client_name="customer-service-ai-client",
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=False,
                admin_user_password=True,
            ),
            access_token_validity=cdk.Duration.hours(1),
            id_token_validity=cdk.Duration.hours(1),
            refresh_token_validity=cdk.Duration.days(1),
            prevent_user_existence_errors=True,
        )

        cdk.CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        cdk.CfnOutput(self, "AppClientId", value=self.app_client.user_pool_client_id)
