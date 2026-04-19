#!/usr/bin/env python3
"""Provision all AWS resources for the Prior Authorization Bot."""

import boto3
from datetime import datetime, timezone

REGION = "us-east-1"
ACCOUNT_ID = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]

S3_BUCKETS = [
    f"pa-audio-uploads-{ACCOUNT_ID}",
    f"pa-blank-forms-{ACCOUNT_ID}",
    f"pa-textract-output-{ACCOUNT_ID}",
    f"pa-completed-forms-{ACCOUNT_ID}",
]

DYNAMODB_TABLES = {
    "pa_requests": {
        "KeySchema": [{"AttributeName": "pa_request_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "pa_request_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
        "StreamSpecification": {"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
    },
    "pa_memories": {
        "KeySchema": [
            {"AttributeName": "memory_type", "KeyType": "HASH"},
            {"AttributeName": "memory_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "memory_type", "AttributeType": "S"},
            {"AttributeName": "memory_id", "AttributeType": "S"},
            {"AttributeName": "provider", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
            {"AttributeName": "treatment", "AttributeType": "S"},
            {"AttributeName": "provider_treatment", "AttributeType": "S"},
            {"AttributeName": "success_count", "AttributeType": "N"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "gsi-provider-created",
                "KeySchema": [
                    {"AttributeName": "provider", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "gsi-treatment-created",
                "KeySchema": [
                    {"AttributeName": "treatment", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "gsi-provider-treatment-success",
                "KeySchema": [
                    {"AttributeName": "provider_treatment", "KeyType": "HASH"},
                    {"AttributeName": "success_count", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "pa_scrape_cache": {
        "KeySchema": [{"AttributeName": "cache_key", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "cache_key", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    "pa_patients": {
        "KeySchema": [{"AttributeName": "patient_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "patient_id", "AttributeType": "S"},
            {"AttributeName": "primary_physician_id", "AttributeType": "S"},
            {"AttributeName": "last_name", "AttributeType": "S"},
            {"AttributeName": "first_name", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "by_physician",
                "KeySchema": [
                    {"AttributeName": "primary_physician_id", "KeyType": "HASH"},
                    {"AttributeName": "last_name", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "by_name",
                "KeySchema": [
                    {"AttributeName": "last_name", "KeyType": "HASH"},
                    {"AttributeName": "first_name", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "pa_physicians": {
        "KeySchema": [{"AttributeName": "physician_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "physician_id", "AttributeType": "S"},
            {"AttributeName": "last_name", "AttributeType": "S"},
            {"AttributeName": "first_name", "AttributeType": "S"},
            {"AttributeName": "npi", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "by_name",
                "KeySchema": [
                    {"AttributeName": "last_name", "KeyType": "HASH"},
                    {"AttributeName": "first_name", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "by_npi",
                "KeySchema": [
                    {"AttributeName": "npi", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
}

def create_s3_buckets():
    print("\n--- S3 Buckets ---")
    s3 = boto3.client("s3", region_name=REGION)
    existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}

    for bucket in S3_BUCKETS:
        if bucket in existing:
            print(f"  {bucket}: already exists")
        else:
            # No LocationConstraint for us-east-1
            s3.create_bucket(Bucket=bucket)
            print(f"  {bucket}: created")


def create_dynamodb_tables():
    print("\n--- DynamoDB Tables ---")
    dynamodb = boto3.client("dynamodb", region_name=REGION)
    existing = dynamodb.list_tables()["TableNames"]

    for table_name, config in DYNAMODB_TABLES.items():
        if table_name in existing:
            print(f"  {table_name}: already exists")
        else:
            params = {"TableName": table_name, **config}
            dynamodb.create_table(**params)
            print(f"  {table_name}: creating...", end="", flush=True)
            waiter = dynamodb.get_waiter("table_exists")
            waiter.wait(TableName=table_name, WaiterConfig={"Delay": 3, "MaxAttempts": 40})
            print(" active")

    if "pa_scrape_cache" not in existing:
        dynamodb.update_time_to_live(
            TableName="pa_scrape_cache",
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
        )
        print("  pa_scrape_cache: TTL enabled on 'ttl' attribute")
    else:
        ttl_info = dynamodb.describe_time_to_live(TableName="pa_scrape_cache")
        status = ttl_info["TimeToLiveDescription"]["TimeToLiveStatus"]
        if status in ("ENABLED", "ENABLING"):
            print("  pa_scrape_cache: TTL already enabled")
        else:
            dynamodb.update_time_to_live(
                TableName="pa_scrape_cache",
                TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
            )
            print("  pa_scrape_cache: TTL enabled on 'ttl' attribute")


def setup_cloudwatch():
    print("\n--- CloudWatch ---")
    cw = boto3.client("cloudwatch", region_name=REGION)
    cw.put_metric_data(
        Namespace="PriorAuthBot",
        MetricData=[
            {
                "MetricName": "setup_complete",
                "Value": 1,
                "Unit": "Count",
                "Timestamp": datetime.now(timezone.utc),
            }
        ],
    )
    print("  PriorAuthBot namespace initialized with setup_complete metric")


def main():
    print("=== Prior Auth Bot AWS Setup ===")
    create_s3_buckets()
    create_dynamodb_tables()
    setup_cloudwatch()
    print("\n=== Setup Complete ===")


if __name__ == "__main__":
    main()
