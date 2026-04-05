import aws_cdk as cdk
from aws_cdk import aws_s3 as s3, aws_iam as iam, aws_sagemaker as sagemaker
from constructs import Construct


class SageMakerConstruct(Construct):
    """SageMaker resources for model fine-tuning and deployment."""

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        # S3 bucket for training data and model artifacts
        self.training_bucket = s3.Bucket(
            self,
            "TrainingBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # SageMaker execution role
        self.execution_role = iam.Role(
            self,
            "SageMakerRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFullAccess"),
            ],
        )
        self.training_bucket.grant_read_write(self.execution_role)

        # Model package group for versioning
        self.model_package_group = sagemaker.CfnModelPackageGroup(
            self,
            "ModelPackageGroup",
            model_package_group_name="customer-service-ai-models",
            model_package_group_description="Fine-tuned models for customer service AI assistant",
        )
