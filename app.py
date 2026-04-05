#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.main_stack import CustomerServiceAIStack

app = cdk.App()

env_us_east_1 = cdk.Environment(
    account=app.node.try_get_context("account"),
    region="us-east-1",
)

CustomerServiceAIStack(app, "CustomerServiceAI-Primary", env=env_us_east_1)

app.synth()
