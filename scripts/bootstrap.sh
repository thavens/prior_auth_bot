#!/usr/bin/env bash
# bootstrap.sh -- One-shot setup and deployment for the Prior Authorization Bot
#
# Usage:
#   ./scripts/bootstrap.sh
#
# Prerequisites: aws cli, cdk cli, python3.12+

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ------------------------------------------------------------------ #
# Colors for output
# ------------------------------------------------------------------ #
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ------------------------------------------------------------------ #
# 1. Check required tools
# ------------------------------------------------------------------ #
info "Checking required tools..."

command -v aws     >/dev/null 2>&1 || error "aws cli not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
command -v cdk     >/dev/null 2>&1 || error "cdk cli not found. Install: npm install -g aws-cdk"
command -v python3 >/dev/null 2>&1 || error "python3 not found. Install Python 3.12+."

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Found python3 $PYTHON_VERSION"

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || error "AWS credentials not configured. Run: aws configure"
AWS_REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")
info "AWS Account: $AWS_ACCOUNT  Region: $AWS_REGION"

# ------------------------------------------------------------------ #
# 2. Create and activate virtual environment
# ------------------------------------------------------------------ #
VENV_DIR="$PROJECT_ROOT/.venv"

if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    info "Virtual environment already exists at $VENV_DIR"
fi

info "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# ------------------------------------------------------------------ #
# 3. Install dependencies
# ------------------------------------------------------------------ #
info "Installing project dependencies..."
pip install --upgrade pip --quiet
pip install -e "$PROJECT_ROOT" --quiet
pip install -e "$PROJECT_ROOT[dev]" --quiet
pip install -e "$PROJECT_ROOT[lambda]" --quiet

info "Dependencies installed successfully."

# ------------------------------------------------------------------ #
# 4. CDK bootstrap
# ------------------------------------------------------------------ #
info "Running cdk bootstrap for $AWS_ACCOUNT/$AWS_REGION..."
cd "$PROJECT_ROOT"
cdk bootstrap "aws://$AWS_ACCOUNT/$AWS_REGION"

# ------------------------------------------------------------------ #
# 5. Deploy all stacks
# ------------------------------------------------------------------ #
info "Deploying all CDK stacks (this may take 10-15 minutes)..."
cdk deploy --all --require-approval never

# ------------------------------------------------------------------ #
# 6. Verify SES email identity
# ------------------------------------------------------------------ #
info "Verifying SES email identity..."
python3 "$SCRIPT_DIR/verify_ses.py"

# ------------------------------------------------------------------ #
# 7. Upload sample data to S3
# ------------------------------------------------------------------ #
info "Retrieving S3 bucket name from CloudFormation outputs..."
DATA_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name StorageStack \
    --query 'Stacks[0].Outputs[?contains(OutputKey,`DataBucket`)].OutputValue' \
    --output text 2>/dev/null || true)

if [ -z "$DATA_BUCKET" ]; then
    # Fallback: find the bucket by prefix
    DATA_BUCKET=$(aws s3 ls | grep -o 'storagestack-databucket[^ ]*' | head -1 || true)
fi

if [ -n "$DATA_BUCKET" ]; then
    info "Uploading sample data to s3://$DATA_BUCKET..."

    # Patient data
    aws s3 cp "$PROJECT_ROOT/sample_data/patient_data/" \
        "s3://$DATA_BUCKET/patient-data/" --recursive

    # Blank forms (if any exist)
    if [ -d "$PROJECT_ROOT/sample_data/blank_forms" ] && [ "$(ls -A "$PROJECT_ROOT/sample_data/blank_forms" 2>/dev/null)" ]; then
        aws s3 cp "$PROJECT_ROOT/sample_data/blank_forms/" \
            "s3://$DATA_BUCKET/blank-forms/" --recursive
    else
        warn "No blank forms found in sample_data/blank_forms/. Skipping."
    fi

    # Recordings (if any exist)
    if [ -d "$PROJECT_ROOT/sample_data/recordings" ] && [ "$(ls -A "$PROJECT_ROOT/sample_data/recordings" 2>/dev/null)" ]; then
        aws s3 cp "$PROJECT_ROOT/sample_data/recordings/" \
            "s3://$DATA_BUCKET/recordings/" --recursive
    else
        warn "No recordings found in sample_data/recordings/. Skipping."
    fi

    info "Sample data uploaded."
else
    warn "Could not determine S3 bucket name. Skipping sample data upload."
    warn "You can upload manually: aws s3 cp sample_data/patient_data/ s3://<BUCKET>/patient-data/ --recursive"
fi

# ------------------------------------------------------------------ #
# 8. Seed OpenSearch indices
# ------------------------------------------------------------------ #
info "Seeding OpenSearch indices..."
python3 "$SCRIPT_DIR/seed_opensearch.py"

# ------------------------------------------------------------------ #
# 9. Summary
# ------------------------------------------------------------------ #
echo ""
echo "============================================================"
info "Prior Authorization Bot -- Deployment Summary"
echo "============================================================"
echo ""

# Collect stack outputs
for STACK in StorageStack SearchStack MessagingStack ComputeStack PipelineStack MonitoringStack; do
    echo -e "${GREEN}--- $STACK ---${NC}"
    aws cloudformation describe-stacks \
        --stack-name "$STACK" \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
        --output table 2>/dev/null || warn "Could not retrieve outputs for $STACK"
    echo ""
done

info "Deployment complete! Next steps:"
echo "  1. Confirm the SES verification email (check michael.lavery.2017@gmail.com)"
echo "  2. Confirm the SNS subscription email"
echo "  3. Upload a recording to trigger the pipeline:"
echo "     python3 scripts/trigger_pipeline.py --recording <path-to-audio>"
echo ""
