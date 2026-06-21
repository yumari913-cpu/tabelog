# AWS Instagram Scheduler

This setup uses AWS only as the reliable scheduler. At 20:00 JST, AWS EventBridge Scheduler invokes a small Lambda function. The Lambda function calls GitHub's workflow dispatch API, and the existing GitHub workflow builds the Instagram assets and publishes the feed plus story.

This avoids packaging image-generation libraries and Japanese fonts into Lambda, while moving the timing trigger away from GitHub scheduled workflows.

## Cost

For this workload, AWS should stay inside the free tier in normal use:

- EventBridge Scheduler: two schedules, one daily and one weekly.
- Lambda: one short invocation per schedule.

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
3. Run:

```bash
export AWS_REGION=ap-northeast-1
export GITHUB_TOKEN='YOUR_GITHUB_FINE_GRAINED_TOKEN'
chmod +x deploy/aws_github_scheduler_setup.sh
./deploy/aws_github_scheduler_setup.sh
```

The script creates or updates:

- Lambda function: `tabelog-instagram-github-scheduler`
- EventBridge schedule: `tabelog-instagram-github-scheduler-daily-2000-jst`
- EventBridge schedule: `tabelog-instagram-github-scheduler-weekly-sync-mon-1000-jst`
- Minimal IAM roles for Lambda logging and Scheduler invocation

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

## After AWS Is Confirmed

Once AWS triggering is confirmed, the GitHub cron schedules can be removed or left as fallback. Leaving them temporarily is safe because the workflow checks `posted_review_urls.csv` before posting and should avoid duplicate daily posts.
