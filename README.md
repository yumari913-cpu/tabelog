# 食べログ to Instagram 自動投稿システム

食べログのレビュアーページから口コミを取り込み、Instagram投稿用の下書きを作る小さな管理システムです。

## できること

- 食べログの過去口コミを一括取り込み
- 新規口コミだけを検知して追加
- Instagramフィード用キャプションを自動生成
- フィード1枚目用の「場所＋店名」画像を生成
- 投稿パッケージをZIPで生成
- Instagram Graph APIの認証情報を設定するとフィード、リール、ストーリーズ投稿を実行
- 認証情報がない場合は安全に下書きだけ作成

## 初期設定

```bash
cp config.example.json config.json
```

`config.json` にInstagramの情報を入れます。

- `ig_user_id`: InstagramプロアカウントのID
- `access_token`: Instagram Graph APIで発行したアクセストークン
- `public_base_url`: 生成した画像や動画をInstagramが取得できる公開URL

Instagram APIはローカルファイルを直接受け取れないため、実投稿には画像・動画を公開URLで配信する必要があります。

## 使い方

過去投稿を取り込みます。

```bash
python3 cli.py backfill
```

新規投稿をチェックします。

```bash
python3 cli.py sync
```

新規投稿を定期チェックします。

```bash
python3 scheduler.py --interval-minutes 60
```

管理画面を開きます。

```bash
python3 app.py
```

ブラウザで `http://localhost:8000` を開きます。

## 投稿方針

まずは「取り込み、下書き確認、手動投稿」が安全です。Instagram認証情報と公開URLが整ったら、管理画面またはCLIから投稿できます。

`config.json` の `auto_publish.feed` を `true` にすると、新規検知した口コミをフィードへ自動投稿します。`story` と `reel` も同じ設定でオンにできます。

リール投稿には動画ファイルが必要です。このシステムには簡易リール生成の入口を用意していますが、実運用では `ffmpeg` を入れて写真スライド動画を生成する構成をおすすめします。

## 実運用で必要なもの

- Instagramプロアカウント
- Metaアプリ
- Instagram Graph APIのアクセストークン
- Instagramが画像・動画を取得できる公開URL
- 常時起動するMac、サーバー、またはクラウド環境

## GCPでオンライン稼働する

おすすめ構成は以下です。

- Cloud Run: 管理画面と同期APIを常時公開
- Cloud Scheduler: 1時間ごとに新規投稿チェック
- Cloud Storage: 投稿リスト、フィード1枚目画像、ストーリーズ画像、リール動画を保存
- Secret Manager: Instagram API情報と同期トークンを保存

まずGCP側にSecretを作ります。

```bash
printf 'YOUR_IG_USER_ID' | gcloud secrets create ig-user-id --data-file=-
printf 'YOUR_IG_ACCESS_TOKEN' | gcloud secrets create ig-access-token --data-file=-
printf 'RANDOM_SYNC_TOKEN' | gcloud secrets create sync-token --data-file=-
```

次にデプロイします。

```bash
PROJECT_ID=your-gcp-project-id \
REGION=asia-northeast1 \
SYNC_TOKEN_VALUE=RANDOM_SYNC_TOKEN \
bash deploy/gcp_setup.sh
```

自動投稿をオンにする場合は、デプロイ時に環境変数を追加します。

```bash
AUTO_PUBLISH_FEED=true \
PROJECT_ID=your-gcp-project-id \
REGION=asia-northeast1 \
SYNC_TOKEN_VALUE=RANDOM_SYNC_TOKEN \
bash deploy/gcp_setup.sh
```

フィード投稿は、1枚目に「場所＋店名」のカバー画像を自動生成し、その後ろに食べログ投稿写真を並べるカルーセル形式です。

## GitHubからGCPへデプロイする

[.github/workflows/deploy-gcp.yml](.github/workflows/deploy-gcp.yml) を追加済みです。GitHub Actionsで使う場合は、Repository VariablesとSecretsに以下を設定します。

- Variables: `GCP_PROJECT_ID`, `GCP_REGION`, `GCS_BUCKET`, `AUTO_PUBLISH_FEED`, `AUTO_PUBLISH_STORY`, `AUTO_PUBLISH_REEL`
- Secrets: `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `SYNC_TOKEN_VALUE`

Instagram API情報はGitHub Secretsではなく、GCP Secret Managerに置く設計です。

初心者向けの詳しい手順は [docs/github-actions-gcp-setup.md](docs/github-actions-gcp-setup.md) にまとめています。
