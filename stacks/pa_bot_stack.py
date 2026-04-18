"""Consolidated CDK stack for the Prior Authorization Bot.

Combines all resources (storage, search, messaging, compute, pipeline,
monitoring) into a single stack to eliminate cross-stack circular
dependencies.
"""

import json

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudwatch as cw,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_opensearchserverless as aoss,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_ses as ses,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct


class PABotStack(Stack):
    """Single stack containing every resource for the Prior Auth Bot."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # -----------------------------------------------------------------
        # Context values
        # -----------------------------------------------------------------
        bedrock_model_id = self.node.try_get_context("bedrock_model_id")
        bedrock_embed_model_id = self.node.try_get_context("bedrock_embed_model_id")
        ses_to_email = self.node.try_get_context("ses_to_email")

        # ================================================================= #
        #  A. STORAGE  (S3 bucket, DynamoDB tables)                         #
        # ================================================================= #

        # ---- S3 Bucket ----
        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ---- DynamoDB - Web-scrape cache ----
        cache_table = dynamodb.Table(
            self,
            "WebScrapeCache",
            table_name="pa-web-scrape-cache",
            partition_key=dynamodb.Attribute(
                name="provider_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="treatment_code", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="expires_at",
        )

        # ---- DynamoDB - Memories ----
        memories_table = dynamodb.Table(
            self,
            "Memories",
            table_name="pa-memories",
            partition_key=dynamodb.Attribute(
                name="memory_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="memory_type", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        memories_table.add_global_secondary_index(
            index_name="ByDocument",
            partition_key=dynamodb.Attribute(
                name="document_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.NUMBER
            ),
        )

        memories_table.add_global_secondary_index(
            index_name="ByProvider",
            partition_key=dynamodb.Attribute(
                name="provider_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.NUMBER
            ),
        )

        memories_table.add_global_secondary_index(
            index_name="ByPrescription",
            partition_key=dynamodb.Attribute(
                name="prescription_code", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.NUMBER
            ),
        )

        # ---- DynamoDB - PA Tracking ----
        tracking_table = dynamodb.Table(
            self,
            "Tracking",
            table_name="pa-tracking",
            partition_key=dynamodb.Attribute(
                name="pa_request_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ================================================================= #
        #  B. SEARCH  (OpenSearch Serverless)                               #
        # ================================================================= #

        collection_name = "pa-bot-vectors"

        # ---- Encryption policy - AWS-owned key ----
        encryption_policy = aoss.CfnSecurityPolicy(
            self,
            "EncryptionPolicy",
            name=f"{collection_name}-enc",
            type="encryption",
            policy=json.dumps(
                {
                    "Rules": [
                        {
                            "ResourceType": "collection",
                            "Resource": [f"collection/{collection_name}"],
                        }
                    ],
                    "AWSOwnedKey": True,
                }
            ),
        )

        # ---- Network policy - public access (hackathon) ----
        network_policy = aoss.CfnSecurityPolicy(
            self,
            "NetworkPolicy",
            name=f"{collection_name}-net",
            type="network",
            policy=json.dumps(
                [
                    {
                        "Rules": [
                            {
                                "ResourceType": "collection",
                                "Resource": [f"collection/{collection_name}"],
                            },
                            {
                                "ResourceType": "dashboard",
                                "Resource": [f"collection/{collection_name}"],
                            },
                        ],
                        "AllowFromPublic": True,
                    }
                ]
            ),
        )

        # ---- Collection ----
        collection = aoss.CfnCollection(
            self,
            "VectorCollection",
            name=collection_name,
            type="VECTORSEARCH",
        )
        collection.add_dependency(encryption_policy)
        collection.add_dependency(network_policy)

        # ---- Data access policy ----
        principals = [f"arn:aws:iam::{cdk.Aws.ACCOUNT_ID}:root"]

        aoss.CfnAccessPolicy(
            self,
            "DataAccessPolicy",
            name=f"{collection_name}-access",
            type="data",
            policy=json.dumps(
                [
                    {
                        "Rules": [
                            {
                                "ResourceType": "collection",
                                "Resource": [f"collection/{collection_name}"],
                                "Permission": [
                                    "aoss:CreateCollectionItems",
                                    "aoss:UpdateCollectionItems",
                                    "aoss:DescribeCollectionItems",
                                ],
                            },
                            {
                                "ResourceType": "index",
                                "Resource": [f"index/{collection_name}/*"],
                                "Permission": [
                                    "aoss:CreateIndex",
                                    "aoss:UpdateIndex",
                                    "aoss:DescribeIndex",
                                    "aoss:ReadDocument",
                                    "aoss:WriteDocument",
                                ],
                            },
                        ],
                        "Principal": principals,
                    }
                ]
            ),
        )

        opensearch_endpoint = collection.attr_collection_endpoint

        # ================================================================= #
        #  C. MESSAGING  (SES, SNS)                                         #
        # ================================================================= #

        # ---- SES Email Identity ----
        ses.CfnEmailIdentity(
            self,
            "PABotEmailIdentity",
            email_identity="michael.lavery.2017@gmail.com",
        )

        # ---- SNS Notification Topic ----
        notifications_topic = sns.Topic(
            self,
            "PABotNotificationsTopic",
            topic_name="pa-bot-notifications",
        )

        notifications_topic.add_subscription(
            subscriptions.EmailSubscription("michael.lavery.2017@gmail.com")
        )

        # ================================================================= #
        #  D. COMPUTE  (Lambda layer, all 10 Lambda functions, grants)      #
        # ================================================================= #

        # ---- Shared Lambda Layer ----
        shared_layer = _lambda.LayerVersion(
            self,
            "SharedLayer",
            code=_lambda.Code.from_asset("lambdas/shared"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Shared utilities for Prior Auth Bot lambdas",
        )

        # ---- Common IAM policy statements ----
        bedrock_policy = iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"],
        )

        aoss_policy = iam.PolicyStatement(
            actions=["aoss:APIAccessAll"],
            resources=["*"],
        )

        # ---- 1. transcribe_handler (256 MB, 30 s) ----
        transcribe_fn = _lambda.Function(
            self,
            "TranscribeHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/transcribe_handler"),
            layers=[shared_layer],
            memory_size=256,
            timeout=Duration.seconds(30),
            environment={
                "DATA_BUCKET": data_bucket.bucket_name,
                "TRANSCRIPTS_PREFIX": "transcripts",
            },
        )

        data_bucket.grant_read_write(transcribe_fn)

        transcribe_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "transcribe:StartMedicalTranscriptionJob",
                    "transcribe:StartTranscriptionJob",
                    "transcribe:GetTranscriptionJob",
                ],
                resources=["*"],
            )
        )

        # ---- 2. extract_entities_handler (512 MB, 60 s) ----
        extract_entities_fn = _lambda.Function(
            self,
            "ExtractEntitiesHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/extract_entities_handler"),
            layers=[shared_layer],
            memory_size=512,
            timeout=Duration.seconds(60),
            environment={
                "DATA_BUCKET": data_bucket.bucket_name,
            },
        )

        data_bucket.grant_read(extract_entities_fn)

        extract_entities_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "comprehendmedical:InferRxNorm",
                    "comprehendmedical:InferSNOMEDCT",
                    "comprehendmedical:DetectEntitiesV2",
                ],
                resources=["*"],
            )
        )

        # ---- 3. pa_check_handler (512 MB, 120 s) ----
        pa_check_fn = _lambda.Function(
            self,
            "PACheckHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/pa_check_handler"),
            layers=[shared_layer],
            memory_size=512,
            timeout=Duration.seconds(120),
            environment={
                "DATA_BUCKET": data_bucket.bucket_name,
                "CACHE_TABLE": cache_table.table_name,
                "BEDROCK_MODEL_ID": bedrock_model_id,
            },
        )

        data_bucket.grant_read(pa_check_fn)
        cache_table.grant_read_write_data(pa_check_fn)
        pa_check_fn.add_to_role_policy(bedrock_policy)

        # ---- 4. form_selection_handler (512 MB, 60 s) ----
        form_selection_fn = _lambda.Function(
            self,
            "FormSelectionHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/form_selection_handler"),
            layers=[shared_layer],
            memory_size=512,
            timeout=Duration.seconds(60),
            environment={
                "OPENSEARCH_ENDPOINT": opensearch_endpoint,
                "FORMS_INDEX": "blank-forms",
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "BEDROCK_EMBED_MODEL_ID": bedrock_embed_model_id,
            },
        )

        form_selection_fn.add_to_role_policy(bedrock_policy)
        form_selection_fn.add_to_role_policy(aoss_policy)

        # ---- 5. memory_search_handler (512 MB, 60 s) ----
        memory_search_fn = _lambda.Function(
            self,
            "MemorySearchHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/memory_search_handler"),
            layers=[shared_layer],
            memory_size=512,
            timeout=Duration.seconds(60),
            environment={
                "OPENSEARCH_ENDPOINT": opensearch_endpoint,
                "MEMORIES_INDEX": "memories",
                "MEMORIES_TABLE": memories_table.table_name,
                "BEDROCK_EMBED_MODEL_ID": bedrock_embed_model_id,
            },
        )

        memory_search_fn.add_to_role_policy(bedrock_policy)
        memory_search_fn.add_to_role_policy(aoss_policy)
        memories_table.grant_read_data(memory_search_fn)

        # ---- 6. document_population_handler (1024 MB, 300 s) ----
        document_population_fn = _lambda.Function(
            self,
            "DocumentPopulationHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/document_population_handler"),
            layers=[shared_layer],
            memory_size=1024,
            timeout=Duration.seconds(300),
            environment={
                "DATA_BUCKET": data_bucket.bucket_name,
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "TRACKING_TABLE": tracking_table.table_name,
            },
        )

        data_bucket.grant_read_write(document_population_fn)
        tracking_table.grant_write_data(document_population_fn)
        document_population_fn.add_to_role_policy(bedrock_policy)

        # ---- 7. document_courier_handler (256 MB, 60 s) ----
        document_courier_fn = _lambda.Function(
            self,
            "DocumentCourierHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/document_courier_handler"),
            layers=[shared_layer],
            memory_size=256,
            timeout=Duration.seconds(60),
            environment={
                "DATA_BUCKET": data_bucket.bucket_name,
                "SES_FROM_EMAIL": ses_to_email,
                "SES_TO_EMAIL": ses_to_email,
                "TRACKING_TABLE": tracking_table.table_name,
                "SNS_TOPIC_ARN": notifications_topic.topic_arn,
            },
        )

        data_bucket.grant_read(document_courier_fn)
        tracking_table.grant_read_write_data(document_courier_fn)
        notifications_topic.grant_publish(document_courier_fn)

        document_courier_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendRawEmail", "ses:SendEmail"],
                resources=["*"],
            )
        )

        # ---- 8. response_handler (512 MB, 120 s) ----
        response_fn = _lambda.Function(
            self,
            "ResponseHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/response_handler"),
            layers=[shared_layer],
            memory_size=512,
            timeout=Duration.seconds(120),
            environment={
                "TRACKING_TABLE": tracking_table.table_name,
                "MEMORIES_TABLE": memories_table.table_name,
                "OPENSEARCH_ENDPOINT": opensearch_endpoint,
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "BEDROCK_EMBED_MODEL_ID": bedrock_embed_model_id,
            },
        )

        tracking_table.grant_read_write_data(response_fn)
        memories_table.grant_read_write_data(response_fn)
        response_fn.add_to_role_policy(bedrock_policy)
        response_fn.add_to_role_policy(aoss_policy)

        # ---- 9. self_improvement_handler (1024 MB, 300 s) ----
        self_improvement_fn = _lambda.Function(
            self,
            "SelfImprovementHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/self_improvement_handler"),
            layers=[shared_layer],
            memory_size=1024,
            timeout=Duration.seconds(300),
            environment={
                "DATA_BUCKET": data_bucket.bucket_name,
                "TRACKING_TABLE": tracking_table.table_name,
                "MEMORIES_TABLE": memories_table.table_name,
                "OPENSEARCH_ENDPOINT": opensearch_endpoint,
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "BEDROCK_EMBED_MODEL_ID": bedrock_embed_model_id,
            },
        )

        data_bucket.grant_read_write(self_improvement_fn)
        tracking_table.grant_full_access(self_improvement_fn)
        memories_table.grant_full_access(self_improvement_fn)
        self_improvement_fn.add_to_role_policy(bedrock_policy)
        self_improvement_fn.add_to_role_policy(aoss_policy)

        # ---- 10. embedding_handler (256 MB, 30 s) ----
        embedding_fn = _lambda.Function(
            self,
            "EmbeddingHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas/embedding_handler"),
            layers=[shared_layer],
            memory_size=256,
            timeout=Duration.seconds(30),
            environment={
                "BEDROCK_EMBED_MODEL_ID": bedrock_embed_model_id,
            },
        )

        embedding_fn.add_to_role_policy(bedrock_policy)

        # ================================================================= #
        #  E. S3 EVENT NOTIFICATIONS  (after Lambdas - no circular dep)     #
        # ================================================================= #

        for suffix in [".mp3", ".wav", ".flac"]:
            data_bucket.add_event_notification(
                s3.EventType.OBJECT_CREATED,
                s3n.LambdaDestination(transcribe_fn),
                s3.NotificationKeyFilter(prefix="recordings/", suffix=suffix),
            )

        # ================================================================= #
        #  F. PIPELINE  (Step Functions state machine)                      #
        # ================================================================= #

        # ---- Step 1 - Extract entities from the transcription ----
        extract_entities = tasks.LambdaInvoke(
            self,
            "ExtractEntities",
            lambda_function=extract_entities_fn,
            output_path="$.Payload",
        )

        # ---- Step 2 - Determine which treatments require prior auth ----
        determine_pa = tasks.LambdaInvoke(
            self,
            "DeterminePA",
            lambda_function=pa_check_fn,
            output_path="$.Payload",
        )

        # ---- Step 3 - Map over each treatment that needs PA ----

        # 3a  Select the correct form
        select_form = tasks.LambdaInvoke(
            self,
            "SelectForm",
            lambda_function=form_selection_fn,
            output_path="$.Payload",
        )

        # 3b  Search memory for similar past cases
        search_memories = tasks.LambdaInvoke(
            self,
            "SearchMemories",
            lambda_function=memory_search_fn,
            output_path="$.Payload",
        )

        # 3c  Populate the PA document
        populate_document = tasks.LambdaInvoke(
            self,
            "PopulateDocument",
            lambda_function=document_population_fn,
            output_path="$.Payload",
        )

        # 3d  Send the document to the payer
        send_document = tasks.LambdaInvoke(
            self,
            "SendDocument",
            lambda_function=document_courier_fn,
            output_path="$.Payload",
        )

        # 3e  Process the payer response
        process_response = tasks.LambdaInvoke(
            self,
            "ProcessResponse",
            lambda_function=response_fn,
            output_path="$.Payload",
        )

        # 3f-approved  Save learnings when approved
        save_learnings = tasks.LambdaInvoke(
            self,
            "SaveLearnings",
            lambda_function=response_fn,
            payload=sfn.TaskInput.from_object(
                {
                    "save_mode": True,
                    "input.$": "$",
                }
            ),
            output_path="$.Payload",
        )

        # 3f-rejected  Run self-improvement loop
        self_improve = tasks.LambdaInvoke(
            self,
            "SelfImprove",
            lambda_function=self_improvement_fn,
            output_path="$.Payload",
        )

        # Fail state for exhausted retries
        exhausted_retries = sfn.Fail(
            self,
            "ExhaustedRetries",
            cause="Maximum retry attempts exhausted",
            error="RETRIES_EXHAUSTED",
        )

        # Treatment-done terminal inside the map
        treatment_done = sfn.Succeed(self, "TreatmentDone")

        # 3f  Choice - check the outcome
        check_outcome = (
            sfn.Choice(self, "CheckOutcome")
            .when(
                sfn.Condition.string_equals("$.outcome", "APPROVED"),
                save_learnings.next(treatment_done),
            )
            .otherwise(self_improve)
        )

        # 3g  Choice - should we retry after self-improvement?
        check_retry = (
            sfn.Choice(self, "CheckRetry")
            .when(
                sfn.Condition.boolean_equals("$.should_retry", True),
                populate_document,
            )
            .otherwise(exhausted_retries)
        )

        # Wire the per-treatment chain
        per_treatment_chain = (
            select_form
            .next(search_memories)
            .next(populate_document)
            .next(send_document)
            .next(process_response)
            .next(check_outcome)
        )
        self_improve.next(check_retry)

        # Map state iterating over treatments that need PA
        map_over_treatments = sfn.Map(
            self,
            "MapOverTreatments",
            items_path=sfn.JsonPath.string_at("$.pa_required_treatments"),
            max_concurrency=1,
        )
        map_over_treatments.item_processor(per_treatment_chain)

        # ---- Step 4 - Final succeed state ----
        all_complete = sfn.Succeed(self, "AllComplete")

        # ---- Assemble the top-level chain ----
        definition = (
            extract_entities
            .next(determine_pa)
            .next(map_over_treatments)
            .next(all_complete)
        )

        # CloudWatch log group for state machine
        pipeline_log_group = logs.LogGroup(
            self,
            "PipelineLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # State machine
        state_machine = sfn.StateMachine(
            self,
            "PAWorkflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(24),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=pipeline_log_group,
                level=sfn.LogLevel.ALL,
            ),
        )

        # ---- Pipeline permissions ----
        all_lambdas = [
            extract_entities_fn,
            pa_check_fn,
            form_selection_fn,
            memory_search_fn,
            document_population_fn,
            document_courier_fn,
            response_fn,
            self_improvement_fn,
        ]
        for fn in all_lambdas:
            fn.grant_invoke(state_machine)

        # Allow transcribe_fn to start this state machine
        state_machine.grant(transcribe_fn, "states:StartExecution")

        # Set STATE_MACHINE_ARN env var on transcribe_fn and self_improvement_fn
        transcribe_fn.add_environment(
            "STATE_MACHINE_ARN", state_machine.state_machine_arn
        )
        # ================================================================= #
        #  G. MONITORING  (CloudWatch dashboard, alarms)                    #
        # ================================================================= #

        # ---- Lambda function map for metrics ----
        lambda_functions = {
            "transcribe": transcribe_fn,
            "extract_entities": extract_entities_fn,
            "pa_check": pa_check_fn,
            "form_selection": form_selection_fn,
            "memory_search": memory_search_fn,
            "document_population": document_population_fn,
            "document_courier": document_courier_fn,
            "response": response_fn,
            "self_improvement": self_improvement_fn,
            "embedding": embedding_fn,
        }

        # ---- Step Functions metrics ----
        sfn_executions_started = cw.Metric(
            namespace="AWS/States",
            metric_name="ExecutionsStarted",
            dimensions_map={
                "StateMachineArn": state_machine.state_machine_arn,
            },
            statistic="Sum",
            period=Duration.minutes(5),
        )

        sfn_executions_succeeded = cw.Metric(
            namespace="AWS/States",
            metric_name="ExecutionsSucceeded",
            dimensions_map={
                "StateMachineArn": state_machine.state_machine_arn,
            },
            statistic="Sum",
            period=Duration.minutes(5),
        )

        sfn_executions_failed = cw.Metric(
            namespace="AWS/States",
            metric_name="ExecutionsFailed",
            dimensions_map={
                "StateMachineArn": state_machine.state_machine_arn,
            },
            statistic="Sum",
            period=Duration.minutes(5),
        )

        sfn_widget = cw.GraphWidget(
            title="Step Functions Executions",
            left=[
                sfn_executions_started,
                sfn_executions_succeeded,
                sfn_executions_failed,
            ],
            width=24,
        )

        # ---- Lambda invocation / error metrics ----
        invocation_metrics = []
        error_metrics = []

        for name, fn in lambda_functions.items():
            invocation_metrics.append(
                cw.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Invocations",
                    dimensions_map={"FunctionName": fn.function_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label=f"{name} invocations",
                )
            )
            error_metrics.append(
                cw.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Errors",
                    dimensions_map={"FunctionName": fn.function_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label=f"{name} errors",
                )
            )

        lambda_invocations_widget = cw.GraphWidget(
            title="Lambda Invocations",
            left=invocation_metrics,
            width=24,
        )

        lambda_errors_widget = cw.GraphWidget(
            title="Lambda Errors",
            left=error_metrics,
            width=24,
        )

        # ---- Lambda duration for key functions ----
        key_duration_fns = {
            "document_population": document_population_fn,
            "self_improvement": self_improvement_fn,
        }

        duration_metrics = []
        for name, fn in key_duration_fns.items():
            duration_metrics.append(
                cw.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Duration",
                    dimensions_map={"FunctionName": fn.function_name},
                    statistic="Average",
                    period=Duration.minutes(5),
                    label=f"{name} duration",
                )
            )

        lambda_duration_widget = cw.GraphWidget(
            title="Lambda Duration (Key Functions)",
            left=duration_metrics,
            width=24,
        )

        # ---- Dashboard ----
        cw.Dashboard(
            self,
            "PABotDashboard",
            dashboard_name="PABotDashboard",
            widgets=[
                [sfn_widget],
                [lambda_invocations_widget],
                [lambda_errors_widget],
                [lambda_duration_widget],
            ],
        )

        # ---- Alarms - Step Functions execution failures ----
        cw.Alarm(
            self,
            "SfnExecutionFailuresAlarm",
            metric=sfn_executions_failed,
            threshold=0,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=1,
            alarm_description="Step Functions execution failures detected",
        )

        # ---- Alarms - Lambda errors (one per function) ----
        for name, fn in lambda_functions.items():
            error_metric = cw.Metric(
                namespace="AWS/Lambda",
                metric_name="Errors",
                dimensions_map={"FunctionName": fn.function_name},
                statistic="Sum",
                period=Duration.minutes(5),
            )

            cw.Alarm(
                self,
                f"LambdaErrors-{name}",
                metric=error_metric,
                threshold=0,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                evaluation_periods=1,
                alarm_description=f"Lambda errors detected for {name}",
            )
