# GCP費用ガードレール

## この構成で使うGCP機能

- Cloud Run
- Cloud Scheduler
- Cloud Storage
- Secret Manager
- Artifact Registry
- Cloud Build

## 無料枠に寄せる設定

Cloud Run:

- `min-instances=0`: 常時起動しない
- `max-instances=1`: 暴走しても1台まで
- `cpu=1`
- `memory=512Mi`
- `timeout=180`
- `cpu-throttling`: リクエスト処理中だけCPUを使う
- `no-cpu-boost`: 起動時CPUブーストによる追加消費を避ける

Cloud Scheduler:

- ジョブは3つだけ
- Cloud Schedulerの無料枠は請求先アカウントあたり3ジョブ/月
- 実行回数ではなくジョブ数課金なので、3ジョブ以内を守る
- 追加で作られていたInstagram専用ジョブは削除する

残すジョブ:

- `tabelog-instagram-sync`
- `tabelog-instagram-threads-tick`
- `tabelog-instagram-threads-engage`

削除するジョブ:

- `tabelog-instagram-instagram-sync-review-urls`
- `tabelog-instagram-instagram-post-next`

Cloud Storage:

- `us-central1` を使う
- Cloud Storage Always Free対象リージョンに合わせる
- Cloud Buildの一時ソース保管バケットは7日で削除するライフサイクルを設定

Artifact Registry:

- Dockerイメージは最新3個を保持
- 7日以上古いイメージは削除対象にする

GitHub Actions:

- push時の自動デプロイは無効
- 手動実行 `workflow_dispatch` のみ
- 不要なCloud Build実行を避ける

## 必ず設定する予算アラート

GCP Consoleで設定します。

```text
Billing
→ Budgets & alerts
→ Create budget
```

おすすめ:

```text
Budget amount: 100円
Alert: 50%, 90%, 100%
```

さらに安全にするなら:

```text
Budget amount: 10円
Alert: 50%, 90%, 100%
```

予算アラートは課金を自動停止するものではありません。メールで気づくための仕組みです。

## 追加で手動確認するコマンド

Cloud Runの設定確認:

```bash
gcloud run services describe tabelog-instagram \
  --region us-central1 \
  --format='value(spec.template.spec.containerConcurrency,spec.template.metadata.annotations.autoscaling.knative.dev/maxScale,spec.template.metadata.annotations.autoscaling.knative.dev/minScale)'
```

Cloud Schedulerのジョブ数確認:

```bash
gcloud scheduler jobs list --location us-central1
```

無料枠優先で不要なSchedulerジョブを手動削除する場合:

```bash
gcloud scheduler jobs delete tabelog-instagram-instagram-sync-review-urls \
  --location us-central1 \
  --quiet

gcloud scheduler jobs delete tabelog-instagram-instagram-post-next \
  --location us-central1 \
  --quiet
```

Artifact Registryのイメージ確認:

```bash
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/tabelog-instagram-threads/tabelog-instagram
```

## 注意

完全な0円保証はできません。Cloud Buildを何度も実行する、画像や動画を大量保存する、外部アクセスが増える、他プロジェクトでSchedulerを使う、などで課金される可能性があります。

無料枠を最優先にしたため、Instagram専用の20時投稿ジョブは削除対象にしています。20時固定投稿をCloud Schedulerで別ジョブとして戻すと、Schedulerが4ジョブ以上になり無料枠から外れる可能性があります。
