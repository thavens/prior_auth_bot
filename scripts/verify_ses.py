#!/usr/bin/env python3
"""Verify the SES email identity used by the Prior Authorization Bot.

Checks whether michael.lavery.2017@gmail.com is verified in SES.
If not verified, prints instructions for the user.
"""

from __future__ import annotations

import sys

import boto3
from botocore.exceptions import ClientError

EMAIL = "michael.lavery.2017@gmail.com"
REGION = "us-east-1"


def main() -> None:
    ses = boto3.client("ses", region_name=REGION)

    try:
        response = ses.get_identity_verification_attributes(Identities=[EMAIL])
    except ClientError as exc:
        print(f"[ERROR] Failed to query SES: {exc}")
        sys.exit(1)

    attrs = response.get("VerificationAttributes", {}).get(EMAIL, {})
    status = attrs.get("VerificationStatus", "NotStarted")

    if status == "Success":
        print(f"[OK] SES email identity '{EMAIL}' is verified and ready to send.")
    elif status == "Pending":
        print(f"[PENDING] SES email identity '{EMAIL}' is awaiting verification.")
        print()
        print("  A verification email has been sent to the address above.")
        print("  Please check your inbox (and spam folder) and click the")
        print("  verification link to complete the process.")
        print()
        print("  Once verified, re-run this script to confirm:")
        print("    python3 scripts/verify_ses.py")
    elif status == "Failed":
        print(f"[FAILED] SES verification for '{EMAIL}' has failed.")
        print()
        print("  Try deleting and re-creating the identity:")
        print(f"    aws ses delete-identity --identity {EMAIL}")
        print(f"    aws ses verify-email-identity --email-address {EMAIL}")
        sys.exit(1)
    else:
        print(f"[NOT STARTED] SES email identity '{EMAIL}' has not been submitted for verification.")
        print()
        print("  The CDK deployment should have created the identity.")
        print("  If the deployment succeeded, check your inbox for the verification email.")
        print("  Otherwise, manually request verification:")
        print(f"    aws ses verify-email-identity --email-address {EMAIL}")
        print()
        print("  Then re-run this script:")
        print("    python3 scripts/verify_ses.py")


if __name__ == "__main__":
    main()
