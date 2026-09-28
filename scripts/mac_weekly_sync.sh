#!/bin/bash
set -euo pipefail

BASE_DIR="/Users/sasakiyuusuke/Documents/食べログ×Instagram"
REPO_DIR="${BASE_DIR}/.automation-repo"
KEY_PATH="${BASE_DIR}/.local-secrets/github_deploy_key"
VENV_DIR="${BASE_DIR}/.automation-venv"
LOG_DIR="${BASE_DIR}/logs"
SSH_COMMAND="ssh -i ${KEY_PATH} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

mkdir -p "${LOG_DIR}"
exec >> "${LOG_DIR}/mac-weekly-sync.log" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] weekly preparation started"

if [ ! -f "${KEY_PATH}" ]; then
  echo "Deploy key is missing: ${KEY_PATH}"
  exit 1
fi

export GIT_SSH_COMMAND="${SSH_COMMAND}"
if [ ! -d "${REPO_DIR}/.git" ]; then
  git clone git@github.com:yumari913-cpu/tabelog.git "${REPO_DIR}"
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  /usr/bin/python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/python" -m pip install -q -r "${REPO_DIR}/requirements.txt"
"${VENV_DIR}/bin/python" "${BASE_DIR}/scripts/mac_weekly_prepare.py" \
  --repo-dir "${REPO_DIR}" \
  --prepare-count 10

echo "[$(date '+%Y-%m-%d %H:%M:%S')] weekly preparation completed"
