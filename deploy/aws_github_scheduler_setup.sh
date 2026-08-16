#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${APP_NAME:-tabelog-instagram-github-scheduler}"
AWS_REGION="${AWS_REGION:-ap-northeast-1}"
GITHUB_OWNER="${GITHUB_OWNER:-yumari913-cpu}"
GITHUB_REPO="${GITHUB_REPO:-tabelog}"
GITHUB_REF="${GITHUB_REF:-main}"
GITHUB_TOKEN_SECRET_NAME="${GITHUB_TOKEN_SECRET_NAME:-/${APP_NAME}/github-token}"

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI is required. Run this script in AWS CloudShell or install AWS CLI locally." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="/tmp/${APP_NAME}-build"
ZIP_PATH="/tmp/${APP_NAME}.zip"
LAMBDA_ROLE_NAME="${APP_NAME}-lambda-role"
SCHEDULER_ROLE_NAME="${APP_NAME}-scheduler-role"

rm -rf "${BUILD_DIR}" "${ZIP_PATH}"
mkdir -p "${BUILD_DIR}"
cp "${ROOT_DIR}/aws_scheduler/trigger_github_workflow.py" "${BUILD_DIR}/lambda_function.py"
(cd "${BUILD_DIR}" && zip -q -r "${ZIP_PATH}" .)

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"
SCHEDULER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${SCHEDULER_ROLE_NAME}"
SECRET_ARN=""

if aws secretsmanager describe-secret --secret-id "${GITHUB_TOKEN_SECRET_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  SECRET_ARN="$(aws secretsmanager describe-secret --secret-id "${GITHUB_TOKEN_SECRET_NAME}" --region "${AWS_REGION}" --query ARN --output text)"
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    aws secretsmanager put-secret-value \
      --secret-id "${GITHUB_TOKEN_SECRET_NAME}" \
      --secret-string "${GITHUB_TOKEN}" \
      --region "${AWS_REGION}" >/dev/null
    echo "Updated GitHub token secret: ${GITHUB_TOKEN_SECRET_NAME}"
  else
    echo "Using existing GitHub token secret: ${GITHUB_TOKEN_SECRET_NAME}"
  fi
else
  if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "Secret ${GITHUB_TOKEN_SECRET_NAME} does not exist. Set GITHUB_TOKEN for the first deploy." >&2
    echo "It needs Actions: write permission for ${GITHUB_OWNER}/${GITHUB_REPO}." >&2
    exit 1
  fi
  SECRET_ARN="$(aws secretsmanager create-secret \
    --name "${GITHUB_TOKEN_SECRET_NAME}" \
    --secret-string "${GITHUB_TOKEN}" \
    --region "${AWS_REGION}" \
    --query ARN \
    --output text)"
  echo "Created GitHub token secret: ${GITHUB_TOKEN_SECRET_NAME}"
fi

if ! aws iam get-role --role-name "${LAMBDA_ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role \
    --role-name "${LAMBDA_ROLE_NAME}" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy \
    --role-name "${LAMBDA_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "Created Lambda role. Waiting for IAM propagation..."
  sleep 12
fi

aws iam put-role-policy \
  --role-name "${LAMBDA_ROLE_NAME}" \
  --policy-name "${APP_NAME}-read-github-token-secret" \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",\"Resource\":\"${SECRET_ARN}\"}]}" >/dev/null

if aws lambda get-function --function-name "${APP_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  aws lambda update-function-code \
    --function-name "${APP_NAME}" \
    --zip-file "fileb://${ZIP_PATH}" \
    --region "${AWS_REGION}" >/dev/null
else
  aws lambda create-function \
    --function-name "${APP_NAME}" \
    --runtime python3.11 \
    --handler lambda_function.lambda_handler \
    --role "${LAMBDA_ROLE_ARN}" \
    --zip-file "fileb://${ZIP_PATH}" \
    --timeout 30 \
    --memory-size 128 \
    --region "${AWS_REGION}" >/dev/null
fi

aws lambda update-function-configuration \
  --function-name "${APP_NAME}" \
  --region "${AWS_REGION}" \
  --environment "Variables={GITHUB_TOKEN_SECRET_ID=${GITHUB_TOKEN_SECRET_NAME},GITHUB_OWNER=${GITHUB_OWNER},GITHUB_REPO=${GITHUB_REPO},GITHUB_REF=${GITHUB_REF}}" >/dev/null

if ! aws iam get-role --role-name "${SCHEDULER_ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role \
    --role-name "${SCHEDULER_ROLE_NAME}" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"scheduler.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
fi

LAMBDA_ARN="$(aws lambda get-function --function-name "${APP_NAME}" --region "${AWS_REGION}" --query 'Configuration.FunctionArn' --output text)"
aws iam put-role-policy \
  --role-name "${SCHEDULER_ROLE_NAME}" \
  --policy-name "${APP_NAME}-invoke-lambda" \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"${LAMBDA_ARN}\"}]}" >/dev/null

upsert_schedule() {
  local name="$1"
  local expression="$2"
  local input="$3"
  if aws scheduler get-schedule --name "${name}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    aws scheduler update-schedule \
      --name "${name}" \
      --schedule-expression "${expression}" \
      --schedule-expression-timezone "Asia/Tokyo" \
      --flexible-time-window '{"Mode":"OFF"}' \
      --target "{\"Arn\":\"${LAMBDA_ARN}\",\"RoleArn\":\"${SCHEDULER_ROLE_ARN}\",\"Input\":\"${input//"/\\\"}\"}" \
      --region "${AWS_REGION}" >/dev/null
  else
    aws scheduler create-schedule \
      --name "${name}" \
      --schedule-expression "${expression}" \
      --schedule-expression-timezone "Asia/Tokyo" \
      --flexible-time-window '{"Mode":"OFF"}' \
      --target "{\"Arn\":\"${LAMBDA_ARN}\",\"RoleArn\":\"${SCHEDULER_ROLE_ARN}\",\"Input\":\"${input//"/\\\"}\"}" \
      --region "${AWS_REGION}" >/dev/null
  fi
}

upsert_schedule "${APP_NAME}-daily-2000-jst" "cron(0 20 * * ? *)" '{"mode":"daily_post"}'
upsert_schedule "${APP_NAME}-weekly-sync-mon-1000-jst" "cron(0 10 ? * MON *)" '{"mode":"sync_reviews"}'

echo "AWS scheduler migration is ready."
echo "Daily Instagram post trigger: 20:00 JST"
echo "Weekly Tabelog URL sync trigger: Monday 10:00 JST"
echo "Lambda: ${APP_NAME}"
echo "GitHub token secret: ${GITHUB_TOKEN_SECRET_NAME}"
