#!/usr/bin/env python3
"""Upload a recording (and optional patient data) to S3 to trigger the PA pipeline.

Usage:
    python3 scripts/trigger_pipeline.py --recording path/to/recording.mp3
    python3 scripts/trigger_pipeline.py --recording path/to/recording.wav --patient-data path/to/patient.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"


def get_data_bucket() -> str:
    """Retrieve the data bucket name from CloudFormation stack outputs."""
    cf = boto3.client("cloudformation", region_name=REGION)

    try:
        response = cf.describe_stacks(StackName="StorageStack")
        outputs = response["Stacks"][0].get("Outputs", [])
        for output in outputs:
            key = output["OutputKey"].lower()
            if "databucket" in key or "bucket" in key:
                return output["OutputValue"]
    except (ClientError, IndexError, KeyError):
        pass

    # Fallback: search for the bucket by naming convention
    s3 = boto3.client("s3", region_name=REGION)
    try:
        buckets = s3.list_buckets()["Buckets"]
        for bucket in buckets:
            if "storagestack" in bucket["Name"].lower() and "databucket" in bucket["Name"].lower():
                return bucket["Name"]
    except ClientError:
        pass

    print("[ERROR] Could not determine the S3 data bucket name.")
    print("  Make sure the StorageStack is deployed: cdk deploy StorageStack")
    sys.exit(1)


def upload_file(bucket: str, local_path: str, s3_prefix: str) -> str:
    """Upload a local file to S3 and return the S3 key."""
    s3 = boto3.client("s3", region_name=REGION)
    filename = os.path.basename(local_path)
    s3_key = f"{s3_prefix}/{filename}"

    print(f"  Uploading {local_path} -> s3://{bucket}/{s3_key}")
    s3.upload_file(local_path, bucket, s3_key)
    return s3_key


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a recording to S3 to trigger the PA pipeline."
    )
    parser.add_argument(
        "--recording",
        required=True,
        help="Path to the audio recording file (mp3, wav, or flac).",
    )
    parser.add_argument(
        "--patient-data",
        required=False,
        help="Path to a patient data JSON file (optional).",
    )
    args = parser.parse_args()

    # Validate recording file
    recording_path = Path(args.recording).resolve()
    if not recording_path.exists():
        print(f"[ERROR] Recording file not found: {recording_path}")
        sys.exit(1)

    suffix = recording_path.suffix.lower()
    if suffix not in (".mp3", ".wav", ".flac"):
        print(f"[WARN] Unexpected file extension '{suffix}'. Supported: .mp3, .wav, .flac")
        print("  The pipeline S3 trigger is configured for .mp3, .wav, and .flac files.")

    # Validate patient data file (if provided)
    patient_data_path = None
    if args.patient_data:
        patient_data_path = Path(args.patient_data).resolve()
        if not patient_data_path.exists():
            print(f"[ERROR] Patient data file not found: {patient_data_path}")
            sys.exit(1)

    # Get bucket name
    print("[1/2] Resolving S3 bucket...")
    bucket = get_data_bucket()
    print(f"  Bucket: {bucket}")
    print()

    # Upload files
    print("[2/2] Uploading files...")
    recording_key = upload_file(bucket, str(recording_path), "recordings")

    patient_key = None
    if patient_data_path:
        patient_key = upload_file(bucket, str(patient_data_path), "patient-data")

    print()
    print("=" * 60)
    print("Upload complete!")
    print("=" * 60)
    print()
    print(f"  Recording S3 key:     {recording_key}")
    if patient_key:
        print(f"  Patient data S3 key:  {patient_key}")
    print()
    print("The S3 upload event will trigger the transcribe Lambda,")
    print("which starts the Step Functions pipeline automatically.")
    print()
    print("Watch the pipeline execution in the Step Functions console:")
    print(f"  https://{REGION}.console.aws.amazon.com/states/home?region={REGION}#/statemachines")
    print()


if __name__ == "__main__":
    main()
