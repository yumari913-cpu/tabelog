# GitHub ActionsからGCPへデプロイする手順

この手順は、GCPプロジェクト `project-54f6f630-4689-4053-9da` を使う前提です。

## 1. Cloud Shellを開く

[Google Cloud Console](https://console.cloud.google.com/) を開き、プロジェクトを選びます。

```text
project-54f6f630-4689-4053-9da
```

右上の `>_` アイコンからCloud Shellを開きます。

## 2. 初期値を設定

Cloud Shellで以下を実行します。

```bash
export PROJECT_ID="project-54f6f630-4689-4053-9da"
export REGION="asia-northeast1"
export SERVICE_ACCOUNT="github-actions-deployer"
export POOL_ID="github-actions-pool"
export PROVIDER_ID="github-actions-provider"
export GITHUB_REPO="yumari913-cpu/tabelog"
```

## 3. 必要なAPIを有効化

```bash
gcloud config set project "${PROJECT_ID}"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com
```

## 4. GitHub Actions用サービスアカウントを作る

```bash
gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
  --display-name="GitHub Actions Deployer"
```

サービスアカウントのメールアドレスを変数に入れます。

```bash
export SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
```

## 5. デプロイに必要な権限を付ける

```bash
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/cloudbuild.builds.editor"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/cloudscheduler.admin"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/serviceusage.serviceUsageAdmin"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/iam.serviceAccountUser"
```

## 6. Workload Identity Federationを作る

```bash
gcloud iam workload-identity-pools create "${POOL_ID}" \
  --location="global" \
  --display-name="GitHub Actions Pool"
```

```bash
gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --display-name="GitHub Actions Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

Pool IDを取得します。

```bash
export WORKLOAD_IDENTITY_POOL_ID="$(gcloud iam workload-identity-pools describe "${POOL_ID}" \
  --location="global" \
  --format="value(name)")"
```

GitHubリポジトリからこのサービスアカウントを使えるようにします。

```bash
gcloud iam service-accounts add-iam-policy-binding "${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${GITHUB_REPO}"
```

GitHubに設定するProvider名を表示します。

```bash
gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --format="value(name)"
```

## 7. Instagram用Secretを作る

`IG_USER_ID` は以下です。

```text
17841475921413218
```

Cloud Shellで実行します。

```bash
printf '17841475921413218' | gcloud secrets create ig-user-id --data-file=-
```

アクセストークンは再発行した新しいものを使ってください。チャットには貼らず、Cloud Shellに直接貼ります。

```bash
printf 'ここに新しいInstagramアクセストークン' | gcloud secrets create ig-access-token --data-file=-
```

同期トークンを作ります。

```bash
printf 'mogmog-sync-2026-random-secret' | gcloud secrets create sync-token --data-file=-
```

## 8. GitHub Repository Variablesを設定

GitHubリポジトリで以下を開きます。

```text
Settings
→ Secrets and variables
→ Actions
→ Variables
```

以下を追加します。

```text
GCP_PROJECT_ID = project-54f6f630-4689-4053-9da
GCP_REGION = asia-northeast1
GCS_BUCKET = project-54f6f630-4689-4053-9da-tabelog-instagram-media
AUTO_PUBLISH_FEED = false
AUTO_PUBLISH_STORY = false
AUTO_PUBLISH_REEL = false
```

最初は `AUTO_PUBLISH_FEED=false` にしてください。

## 9. GitHub Repository Secretsを設定

同じ画面で `Secrets` に以下を追加します。

```text
GCP_SERVICE_ACCOUNT = github-actions-deployer@project-54f6f630-4689-4053-9da.iam.gserviceaccount.com
GCP_WORKLOAD_IDENTITY_PROVIDER = 手順6で表示されたProvider名
SYNC_TOKEN_VALUE = mogmog-sync-2026-random-secret
```

`GCP_WORKLOAD_IDENTITY_PROVIDER` は以下のような形式です。

```text
projects/123456789/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions-provider
```

## 10. GitHub Actionsを実行

GitHubリポジトリで以下を開きます。

```text
Actions
→ Deploy to GCP Cloud Run
→ Run workflow
```

成功すると、ログの最後にCloud Run URLが表示されます。

```text
Service URL: https://xxxxx-xxxxx-an.a.run.app
```

このURLがオンライン版の管理画面です。

## 11. 自動投稿をオンにする

テストが終わってから、GitHub Variablesの以下を変更します。

```text
AUTO_PUBLISH_FEED = true
```

その後、もう一度GitHub Actionsを実行します。
