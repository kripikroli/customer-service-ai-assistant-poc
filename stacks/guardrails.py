import aws_cdk as cdk
from aws_cdk import aws_bedrock as bedrock
from constructs import Construct


class GuardrailsConstruct(Construct):
    """Bedrock Guardrails for financial services compliance and PII filtering."""

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        self.guardrail = bedrock.CfnGuardrail(
            self,
            "FinancialGuardrail",
            name="financial-services-guardrail",
            blocked_input_messaging="Your request contains content that cannot be processed. Please remove any sensitive information and try again.",
            blocked_outputs_messaging="The response was filtered due to compliance policies. Please rephrase your question.",
            description="Guardrail for financial services customer support — blocks PII, investment guarantees, and harmful content.",
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="SEXUAL", input_strength="HIGH", output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="VIOLENCE", input_strength="HIGH", output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="HATE", input_strength="HIGH", output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="INSULTS", input_strength="HIGH", output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="MISCONDUCT", input_strength="HIGH", output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="PROMPT_ATTACK", input_strength="HIGH", output_strength="NONE"
                    ),
                ],
            ),
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
                topics_config=[
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name="InvestmentGuarantees",
                        definition="Guaranteeing specific investment returns, promising risk-free investments, or making definitive predictions about market performance.",
                        type="DENY",
                        examples=[
                            "I guarantee you will make 20% returns.",
                            "This investment is completely risk-free.",
                            "The stock market will definitely go up next month.",
                        ],
                    ),
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name="SpecificFinancialAdvice",
                        definition="Providing specific personalized financial advice such as recommending particular stocks, bonds, or investment strategies for an individual.",
                        type="DENY",
                        examples=[
                            "You should buy ACME stock right now.",
                            "Put all your money into bonds.",
                            "I recommend you invest 80% in equities.",
                        ],
                    ),
                ],
            ),
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=[
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="US_SOCIAL_SECURITY_NUMBER", action="BLOCK"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="CREDIT_DEBIT_CARD_NUMBER", action="ANONYMIZE"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="EMAIL", action="ANONYMIZE"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="PHONE", action="ANONYMIZE"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="NAME", action="ANONYMIZE"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="US_BANK_ACCOUNT_NUMBER", action="BLOCK"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="US_PASSPORT_NUMBER", action="BLOCK"),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(type="DRIVER_ID", action="BLOCK"),
                ],
            ),
            word_policy_config=bedrock.CfnGuardrail.WordPolicyConfigProperty(
                words_config=[
                    bedrock.CfnGuardrail.WordConfigProperty(text="guaranteed returns"),
                    bedrock.CfnGuardrail.WordConfigProperty(text="risk free"),
                    bedrock.CfnGuardrail.WordConfigProperty(text="insider information"),
                    bedrock.CfnGuardrail.WordConfigProperty(text="insider trading"),
                ],
            ),
        )

        self.guardrail_version = bedrock.CfnGuardrailVersion(
            self,
            "GuardrailVersion",
            guardrail_identifier=self.guardrail.attr_guardrail_id,
        )

        self.guardrail_id = self.guardrail.attr_guardrail_id
        self.version = self.guardrail_version.attr_version
