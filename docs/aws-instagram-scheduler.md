# AWS Instagram Scheduler

This setup uses AWS only as the reliable scheduler. At 20:00 JST, AWS EventBridge Scheduler invokes a small Lambda function. The Lambda function calls GitHub's workflow dispatch API, and the existing GitHub workflow builds the Instagram assets and publishes the feed plus story.

This avoids packaging image-generation libraries and Japanese fonts into Lambda, while moving the timing trigger away from GitHub scheduled workflows.

GitHub credentials are stored in AWS Secrets Manager. The Lambda function receives only the secret name and has permission to read that one secret.

## Cost

For this workload, AWS should stay inside the free tier in normal use:

- EventBridge Scheduler: two schedules, one daily and one weekly.
- Lambda: one short invocation per schedule.
- Secrets Manager: one secret for the GitHub token. This is normally the only fixed AWS charge in this setup.

## What AWS Runs

- Daily Instagram post: `20:00 JST`
- Weekly Tabelog URL sync: Monday `10:00 JST`

Both schedules use `Asia/Tokyo` timezone and `Flexible time window: OFF`.

## Required GitHub Token

Create a GitHub fine-grained personal access token with access to:

- Repository: `yumari913-cpu/tabelog`
- Permission: `Actions: Read and write`
- Permission: `Contents: Read-only` is usually enough for dispatch, but `Read and write` is acceptable if GitHub requires it for this repository workflow setup.

Keep this token private.

## Deploy From AWS CloudShell

1. Open AWS CloudShell in the Tokyo region.
2. Upload or clone this repository.
3. For the first deploy, set the GitHub token:

```bash
export AWS_REGION=ap-northeast-1
export GITHUB_TOKEN='YOUR_GITHUB_FINE_GRAINED_TOKEN'
```

4. Run:

```bash
chmod +x deploy/aws_github_scheduler_setup.sh
./deploy/aws_github_scheduler_setup.sh
```

The script creates or updates:

- Lambda function: `tabelog-instagram-github-scheduler`
- EventBridge schedule: `tabelog-instagram-github-scheduler-daily-2000-jst`
- EventBridge schedule: `tabelog-instagram-github-scheduler-weekly-sync-mon-1000-jst`
- Secrets Manager secret: `/tabelog-instagram-github-scheduler/github-token`
- Minimal IAM roles for Lambda logging and Scheduler invocation

After the first deploy, `GITHUB_TOKEN` is not required unless you want to rotate/update the token. The token is read from Secrets Manager.

## Test

After deployment, run a manual Lambda test with this event:

```json
{"mode":"daily_post"}
```

For URL sync:

```json
{"mode":"sync_reviews"}
```

Then check GitHub Actions:

- `Daily Instagram Post`
- `Sync Tabelog Review URLs`

You can also invoke the Lambda directly from CloudShell:

```bash
aws lambda invoke \
  --function-name tabelog-instagram-github-scheduler \
  --payload '{"mode":"daily_post"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/tabelog-instagram-daily-result.json \
  --region ap-northeast-1

cat /tmp/tabelog-instagram-daily-result.json
```

For weekly review URL sync:

```bash
aws lambda invoke \
  --function-name tabelog-instagram-github-scheduler \
  --payload '{"mode":"sync_reviews"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/tabelog-instagram-sync-result.json \
  --region ap-northeast-1

cat /tmp/tabelog-instagram-sync-result.json
```

## Token Rotation

When the GitHub token expires or needs replacement:

```bash
export AWS_REGION=ap-northeast-1
export GITHUB_TOKEN='NEW_GITHUB_FINE_GRAINED_TOKEN'
./deploy/aws_github_scheduler_setup.sh
```

The script updates the existing Secrets Manager value and keeps the Lambda/Scheduler configuration unchanged.

## After AWS Is Confirmed

Once AWS triggering is confirmed, the GitHub cron schedules can be removed or left as fallback. Leaving them temporarily is safe because the workflow checks `posted_review_urls.csv` before posting and should avoid duplicate daily posts.

For strict AWS-only timing, remove or disable the GitHub `schedule:` block after the Lambda test succeeds. Keep `workflow_dispatch:` because AWS uses it.
