#!/usr/bin/bash

set -euo pipefail

GH_TOKEN_VER="${GH_TOKEN_VER:-2.0.8}"
GH_TOKEN_SHA="${GH_TOKEN_SHA:-867d9ebf7dd18e67e2599f0f890f3f41b8673e88c4394a32a05476024c41ea0f}"
GH_TOKEN_RETRY_COUNT="${GH_TOKEN_RETRY_COUNT:-3}"
GOOGLE_CLOUD_REPO_URL="${GOOGLE_CLOUD_REPO_URL:-https://packages.cloud.google.com/yum/repos/cloud-sdk-el9-x86_64}"
MARKDOWNLINT_VERSION="${MARKDOWNLINT_VERSION:-0.40.0}"
MARKDOWNLINT_CLI2_VERSION="${MARKDOWNLINT_CLI2_VERSION:-0.22.1}"

retry_command() {
  local max_attempts="$1"
  shift
  local attempt=1

  until "$@"; do
    if [ "${attempt}" -ge "${max_attempts}" ]; then
      echo "Command failed after ${attempt} attempts: $*" >&2
      return 1
    fi
    echo "Attempt ${attempt}/${max_attempts} failed, retrying..." >&2
    sleep $((attempt * 2))
    attempt=$((attempt + 1))
  done
}

install_gh_token() {
  retry_command "${GH_TOKEN_RETRY_COUNT}" \
    curl -sSL --connect-timeout 10 --max-time 120 --fail \
      "https://github.com/Link-/gh-token/releases/download/v${GH_TOKEN_VER}/linux-amd64" \
      -o /usr/local/bin/gh-token

  echo "${GH_TOKEN_SHA}  /usr/local/bin/gh-token" | sha256sum -c -
  chmod +x /usr/local/bin/gh-token
}

install_google_cloud_cli() {
  tee /etc/yum.repos.d/google-cloud-sdk.repo >/dev/null <<EOF
[google-cloud-cli]
name=Google Cloud CLI
baseurl=${GOOGLE_CLOUD_REPO_URL}
enabled=1
gpgcheck=1
repo_gpgcheck=0
gpgkey=https://packages.cloud.google.com/yum/doc/rpm-package-key.gpg
EOF

  dnf install -y libxcrypt-compat.x86_64 google-cloud-cli
}

install_markdown_tools() {
  npm install -g \
    "markdownlint@v${MARKDOWNLINT_VERSION}" \
    "markdownlint-cli2@v${MARKDOWNLINT_CLI2_VERSION}" \
    markdownlint-cli2-formatter-json \
    markdownlint-cli2-formatter-pretty \
    markdownlint-cli2-formatter-junit
}

cleanup_install_artifacts() {
  dnf clean all
  npm cache clean --force || true
  rm -rf /var/cache/dnf /root/.npm/_cacache
}
