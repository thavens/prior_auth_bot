#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.pa_bot_stack import PABotStack

app = cdk.App()
PABotStack(app, "PABotStack", env=cdk.Environment(region="us-east-1"))
app.synth()
