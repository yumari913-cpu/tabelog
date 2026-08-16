import json
import os
import boto3
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def env(name, default=""):
    return os.getenv(name, default).strip()


def get_github_token():
    token = env("GITHUB_TOKEN")
    if token:
        return token

    secret_id = env("GITHUB_TOKEN_SECRET_ID")
    if not secret_id:
        raise RuntimeError("GITHUB_TOKEN_SECRET_ID or GITHUB_TOKEN is required.")

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    secret = response.get("SecretString", "")
    if not secret:
        raise RuntimeError("GitHub token secret is empty.")

    try:
        parsed = json.loads(secret)
    except json.JSONDecodeError:
        return secret.strip()

    return (
        parsed.get("GITHUB_TOKEN")
        or parsed.get("github_token")
        or parsed.get("token")
        or ""
    ).strip()


def dispatch_workflow(workflow, inputs=None):
    token = get_github_token()
    owner = env("GITHUB_OWNER", "yumari913-cpu")
    repo = env("GITHUB_REPO", "tabelog")
    ref = env("GITHUB_REF", "main")
    if not token:
        raise RuntimeError("GitHub token is required.")

    payload = {"ref": ref}
    if inputs:
        payload["inputs"] = inputs

    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "tabelog-instagram-aws-scheduler",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as res:
            return {"workflow": workflow, "status": res.status}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub workflow dispatch failed {exc.code}: {body}") from exc


def lambda_handler(event, context):
    mode = (event or {}).get("mode", env("MODE", "daily_post"))

    if mode == "daily_post":
        result = dispatch_workflow(
            env("DAILY_WORKFLOW", "daily-instagram-post.yml"),
            {"dry_run": "false"},
        )
    elif mode == "sync_reviews":
        result = dispatch_workflow(env("SYNC_WORKFLOW", "sync-review-urls.yml"))
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return {
        "ok": True,
        "mode": mode,
        "result": result,
    }
