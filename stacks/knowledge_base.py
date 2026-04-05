import os
import shutil
import subprocess
import aws_cdk as cdk
from aws_cdk import (
    aws_s3 as s3,
    aws_iam as iam,
    aws_bedrock as bedrock,
    aws_opensearchserverless as oss,
    aws_lambda as _lambda,
    aws_logs as logs,
)
from constructs import Construct

LAMBDA_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas")


def _bundle_index_creator() -> str:
    """Bundle index_creator Lambda with pip dependencies into a temp dir."""
    source = os.path.join(LAMBDA_DIR, "index_creator")
    bundle_dir = os.path.join(source, ".bundle")
    if os.path.exists(bundle_dir):
        shutil.rmtree(bundle_dir)
    os.makedirs(bundle_dir)
    subprocess.check_call([
        "pip", "install", "-r", os.path.join(source, "requirements.txt"),
        "-t", bundle_dir, "--quiet",
    ])
    for f in os.listdir(source):
        src = os.path.join(source, f)
        if os.path.isfile(src):
            shutil.copy2(src, bundle_dir)
    return bundle_dir


class KnowledgeBaseConstruct(Construct):
    """Bedrock Knowledge Base with S3 data source and OpenSearch Serverless vector store."""

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        self.docs_bucket = s3.Bucket(
            self,
            "DocsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            versioned=True,
        )

        collection_name = "cs-ai-kb-vectors"
        index_name = "kb-index"

        # --- OpenSearch Serverless policies ---
        encryption_policy = oss.CfnSecurityPolicy(
            self,
            "EncryptionPolicy",
            name=f"{collection_name}-enc",
            type="encryption",
            policy=f'{{"Rules":[{{"ResourceType":"collection","Resource":["collection/{collection_name}"]}}],"AWSOwnedKey":true}}',
        )

        network_policy = oss.CfnSecurityPolicy(
            self,
            "NetworkPolicy",
            name=f"{collection_name}-net",
            type="network",
            policy=f'[{{"Rules":[{{"ResourceType":"collection","Resource":["collection/{collection_name}"]}},{{"ResourceType":"dashboard","Resource":["collection/{collection_name}"]}}],"AllowFromPublic":true}}]',
        )

        self.collection = oss.CfnCollection(
            self, "VectorCollection", name=collection_name, type="VECTORSEARCH"
        )
        self.collection.add_dependency(encryption_policy)
        self.collection.add_dependency(network_policy)

        # --- IAM role for Knowledge Base ---
        kb_role = iam.Role(
            self, "KBRole", assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com")
        )
        kb_role.add_to_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"]))
        kb_role.add_to_policy(
            iam.PolicyStatement(actions=["aoss:APIAccessAll"], resources=[self.collection.attr_arn])
        )
        self.docs_bucket.grant_read(kb_role)

        # --- Lambda role for index creator ---
        index_creator_role = iam.Role(
            self,
            "IndexCreatorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ],
        )
        index_creator_role.add_to_policy(
            iam.PolicyStatement(actions=["aoss:APIAccessAll"], resources=[self.collection.attr_arn])
        )

        # --- Data access policy (KB role + index creator role) ---
        oss.CfnAccessPolicy(
            self,
            "DataAccessPolicy",
            name=f"{collection_name}-access",
            type="data",
            policy=cdk.Fn.sub(
                '[{"Rules":[{"ResourceType":"index","Resource":["index/'
                + collection_name
                + '/*"],"Permission":["aoss:CreateIndex","aoss:DeleteIndex","aoss:UpdateIndex","aoss:DescribeIndex","aoss:ReadDocument","aoss:WriteDocument"]},{"ResourceType":"collection","Resource":["collection/'
                + collection_name
                + '"],"Permission":["aoss:CreateCollectionItems","aoss:DeleteCollectionItems","aoss:UpdateCollectionItems","aoss:DescribeCollectionItems"]}],"Principal":["${kb_role_arn}","${lambda_role_arn}"]}]',
                {"kb_role_arn": kb_role.role_arn, "lambda_role_arn": index_creator_role.role_arn},
            ),
        )

        # --- Custom resource: create vector index (bundled locally) ---
        bundle_path = _bundle_index_creator()

        index_creator_fn = _lambda.Function(
            self,
            "IndexCreatorFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            role=index_creator_role,
            timeout=cdk.Duration.minutes(5),
            memory_size=256,
            code=_lambda.Code.from_asset(bundle_path),
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        index_resource = cdk.CustomResource(
            self,
            "VectorIndex",
            service_token=index_creator_fn.function_arn,
            properties={
                "CollectionEndpoint": self.collection.attr_collection_endpoint,
                "IndexName": index_name,
                "Region": cdk.Aws.REGION,
            },
        )
        index_resource.node.add_dependency(self.collection)

        # --- Bedrock Knowledge Base ---
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name="customer-service-kb",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.titan-embed-text-v2:0",
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=self.collection.attr_arn,
                    vector_index_name=index_name,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        vector_field="vector",
                        text_field="text",
                        metadata_field="metadata",
                    ),
                ),
            ),
        )
        self.knowledge_base.node.add_dependency(index_resource)

        # --- S3 data source ---
        self.data_source = bedrock.CfnDataSource(
            self,
            "S3DataSource",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            name="company-docs",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=self.docs_bucket.bucket_arn,
                ),
            ),
        )

        self.knowledge_base_id = self.knowledge_base.attr_knowledge_base_id
