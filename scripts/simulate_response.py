#!/usr/bin/env python3
"""Simulate an insurance provider response (APPROVED or REJECTED) for a PA request.

This invokes the response_handler Lambda with a synthetic response payload,
useful for end-to-end testing without waiting for a real payer response.

Usage:
    python3 scripts/simulate_response.py --pa-request-id PA-001 --outcome APPROVED
    python3 scripts/simulate_response.py --pa-request-id PA-001 --outcome REJECTED --reasons "Missing lab values for A1C"
"""

from __future__ import annotations

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
TRACKING_TABLE = "pa-tracking"


def get_lambda_function_name() -> str:
    """Find the response handler Lambda function name from CloudFormation."""
    cf = boto3.client("cloudformation", region_name=REGION)

    try:
        response = cf.describe_stacks(StackName="ComputeStack")
        for output in response["Stacks"][0].get("Outputs", []):
            key = output["OutputKey"].lower()
            if "response" in key and ("handler" in key or "function" in key or "lambda" in key or "arn" in key):
                return output["OutputValue"]
    except (ClientError, IndexError, KeyError):
        pass

    # Fallback: list Lambda functions and find by naming convention
    lambda_client = boto3.client("lambda", region_name=REGION)
    try:
        paginator = lambda_client.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page["Functions"]:
                if "ResponseHandler" in fn["FunctionName"] or "response-handler" in fn["FunctionName"]:
                    return fn["FunctionName"]
    except ClientError:
        pass

    print("[ERROR] Could not find the response_handler Lambda function.")
    print("  Make sure the ComputeStack is deployed: cdk deploy ComputeStack")
    sys.exit(1)


def lookup_tracking_record(pa_request_id: str) -> dict | None:
    """Fetch the PA tracking record from DynamoDB."""
    dynamo = boto3.resource("dynamodb", region_name=REGION)
    table = dynamo.Table(TRACKING_TABLE)

    try:
        response = table.get_item(Key={"pa_request_id": pa_request_id})
        return response.get("Item")
    except ClientError as exc:
        print(f"[WARN] Could not look up tracking record: {exc}")
        return None


def invoke_response_handler(function_name: str, payload: dict) -> dict:
    """Invoke the response_handler Lambda synchronously."""
    lambda_client = boto3.client("lambda", region_name=REGION)

    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode(),
    )

    response_payload = json.loads(response["Payload"].read())

    if "FunctionError" in response:
        print(f"[ERROR] Lambda execution failed: {response_payload}")
        sys.exit(1)

    return response_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate an insurance provider response for a PA request."
    )
    parser.add_argument(
        "--pa-request-id",
        required=True,
        help="The PA request ID to simulate a response for.",
    )
    parser.add_argument(
        "--outcome",
        required=True,
        choices=["APPROVED", "REJECTED"],
        help="Simulated outcome: APPROVED or REJECTED.",
    )
    parser.add_argument(
        "--reasons",
        required=False,
        default=None,
        help="Rejection reasons (only applicable for REJECTED outcome).",
    )
    args = parser.parse_args()

    pa_request_id = args.pa_request_id
    outcome = args.outcome
    reasons = args.reasons

    if outcome == "APPROVED" and reasons:
        print("[WARN] --reasons is ignored for APPROVED outcomes.")
        reasons = None

    # ------------------------------------------------------------------ #
    # Look up the tracking record
    # ------------------------------------------------------------------ #
    print(f"[1/3] Looking up tracking record for {pa_request_id}...")
    record = lookup_tracking_record(pa_request_id)
    if record:
        print(f"  Found: status={record.get('status', 'UNKNOWN')}, "
              f"patient_id={record.get('patient_id', 'N/A')}")
    else:
        print(f"  [WARN] No tracking record found for {pa_request_id}.")
        print("  Proceeding anyway -- the Lambda will handle the missing record.")
    print()

    # ------------------------------------------------------------------ #
    # Build and send the simulated response
    # ------------------------------------------------------------------ #
    print("[2/3] Resolving response_handler Lambda...")
    function_name = get_lambda_function_name()
    print(f"  Function: {function_name}")
    print()

    payload = {
        "pa_request_id": pa_request_id,
        "response": {
            "outcome": outcome,
        },
    }
    if reasons:
        payload["response"]["rejection_reasons"] = reasons

    print(f"[3/3] Invoking response_handler with simulated {outcome}...")
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    print()

    result = invoke_response_handler(function_name, payload)

    print("=" * 60)
    print("Result:")
    print("=" * 60)
    print(json.dumps(result, indent=2, default=str))
    print()

    if outcome == "APPROVED":
        print("The PA request has been marked as APPROVED.")
        print("The save_learnings step will extract and persist reusable memories.")
    else:
        print("The PA request has been marked as REJECTED.")
        if reasons:
            print(f"  Rejection reasons: {reasons}")
        print()
        print("Watch for the self-improvement pipeline execution in the")
        print("Step Functions console. The system will attempt to revise")
        print("and resubmit the PA request with improvements.")
        print()
        print(f"  https://{REGION}.console.aws.amazon.com/states/home?region={REGION}#/statemachines")


if __name__ == "__main__":
    main()
