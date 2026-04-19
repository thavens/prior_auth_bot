#!/usr/bin/env python3
"""Seed pa_physicians and pa_patients with synthetic demo data."""

import boto3
from datetime import datetime, timezone

REGION = "us-east-1"

PHYSICIANS = [
    {
        "physician_id": "doc_042",
        "first_name": "Robert",
        "last_name": "Chen",
        "npi": "1234567890",
        "specialty": "Oncology",
        "phone": "916-555-0200",
        "fax": "916-555-0201",
    },
    {
        "physician_id": "doc_043",
        "first_name": "Sarah",
        "last_name": "Kim",
        "npi": "2345678901",
        "specialty": "Rheumatology",
        "phone": "916-555-0300",
        "fax": "916-555-0301",
    },
    {
        "physician_id": "doc_044",
        "first_name": "James",
        "last_name": "Patel",
        "npi": "3456789012",
        "specialty": "Cardiology",
        "phone": "916-555-0400",
        "fax": "916-555-0401",
    },
    {
        "physician_id": "doc_045",
        "first_name": "Maria",
        "last_name": "Rodriguez",
        "npi": "4567890123",
        "specialty": "Neurology",
        "phone": "916-555-0500",
        "fax": "916-555-0501",
    },
]

PATIENTS = [
    {
        "patient_id": "pat_001",
        "first_name": "Jane",
        "last_name": "Doe",
        "dob": "1985-03-12",
        "insurance_provider": "medi-cal",
        "insurance_id": "MC-9876543",
        "address": "123 Main St, Sacramento, CA 95814",
        "phone": "916-555-0100",
        "primary_physician_id": "doc_042",
    },
    {
        "patient_id": "pat_002",
        "first_name": "Michael",
        "last_name": "Johnson",
        "dob": "1972-07-22",
        "insurance_provider": "medi-cal",
        "insurance_id": "MC-1234567",
        "address": "456 Oak Ave, Sacramento, CA 95816",
        "phone": "916-555-0110",
        "primary_physician_id": "doc_042",
    },
    {
        "patient_id": "pat_003",
        "first_name": "Emily",
        "last_name": "Zhang",
        "dob": "1990-11-05",
        "insurance_provider": "medi-cal",
        "insurance_id": "MC-5551234",
        "address": "789 Elm Blvd, Sacramento, CA 95818",
        "phone": "916-555-0120",
        "primary_physician_id": "doc_043",
    },
]


def seed():
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    now = datetime.now(timezone.utc).isoformat()

    physicians_table = dynamodb.Table("pa_physicians")
    for doc in PHYSICIANS:
        existing = physicians_table.get_item(Key={"physician_id": doc["physician_id"]}).get("Item")
        if existing:
            print(f"  {doc['physician_id']} ({doc['last_name']}): already exists")
            continue
        physicians_table.put_item(Item={**doc, "created_at": now, "updated_at": now})
        print(f"  {doc['physician_id']} ({doc['last_name']}): created")

    patients_table = dynamodb.Table("pa_patients")
    for pat in PATIENTS:
        existing = patients_table.get_item(Key={"patient_id": pat["patient_id"]}).get("Item")
        if existing:
            print(f"  {pat['patient_id']} ({pat['last_name']}): already exists")
            continue
        patients_table.put_item(Item={**pat, "created_at": now, "updated_at": now})
        print(f"  {pat['patient_id']} ({pat['last_name']}): created")


if __name__ == "__main__":
    print("=== Seeding Patient & Physician Data ===")
    seed()
    print("=== Done ===")
