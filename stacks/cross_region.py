import aws_cdk as cdk
from aws_cdk import aws_route53 as route53, aws_route53_targets as targets
from constructs import Construct


class CrossRegionConstruct(Construct):
    """Route 53 health checks and failover routing for cross-region HA."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        primary_appsync_url: str,
        hosted_zone_id: str | None = None,
        domain_name: str | None = None,
    ) -> None:
        super().__init__(scope, construct_id)

        # Health check on primary AppSync endpoint
        self.health_check = route53.CfnHealthCheck(
            self,
            "PrimaryHealthCheck",
            health_check_config=route53.CfnHealthCheck.HealthCheckConfigProperty(
                type="HTTPS",
                fully_qualified_domain_name=primary_appsync_url.replace("https://", "").split("/")[0],
                resource_path="/graphql",
                request_interval=30,
                failure_threshold=3,
                enable_sni=True,
            ),
        )

        # Failover records require a hosted zone — only create if provided
        if hosted_zone_id and domain_name:
            zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "Zone",
                hosted_zone_id=hosted_zone_id,
                zone_name=domain_name,
            )

            route53.CfnRecordSet(
                self,
                "PrimaryRecord",
                hosted_zone_id=hosted_zone_id,
                name=f"api.{domain_name}",
                type="CNAME",
                ttl="60",
                set_identifier="primary",
                failover="PRIMARY",
                health_check_id=self.health_check.ref,
                resource_records=[primary_appsync_url.replace("https://", "").split("/")[0]],
            )
