#!/bin/bash
set -euo pipefail

API_BASE="https://catalog.redhat.com/api/containers/v1/repositories/registry/registry.access.redhat.com/repository"

usage() {
    cat >&2 <<EOF
Usage: $(basename "$0") <repository> <command> [options]

Arguments:
  repository   Full repository path (e.g. openshift4/microshift-bootc-rhel9)

Commands:
  id        Print the catalog repository ID (used in catalog URLs)
  tags      List all tags (filterable via --tag)
  streams   List content streams (e.g. 4.18, 4.19, 4.20)
  images    List all images with arch, digest, health, and dates (filterable via --tag)

Options:
  --tag TAG    Filter to tags containing TAG (e.g. 4.20, latest)
EOF
    exit 1
}

# page_size=500 is the API maximum; no pagination is implemented.
# Server-side filter= keeps results well under this limit when --tag is
# used, so truncation only risks unfiltered calls against repos with 500+
# images across all releases. Do NOT add include= — it strips fields
# (architecture, freshness_grades, dates) that filter_images.py needs.
fetch_api() {
    local url="${API_BASE}/$1"
    curl -s --fail --max-time 60 --retry 3 --retry-delay 5 "${url}"
}

cmd_tags() {
    local repo=$1 tag=${2:-}
    local tag_args=()
    [[ -z "${tag}" ]] || tag_args=(--tag "${tag}")
    # Server-side filter narrows to images tagged vX.Y, avoiding the 500-image cap.
    # Client-side filter_images.py still runs as a second pass for exact matching.
    local query="page_size=500"
    if [[ -n "${tag}" ]]; then
        query+="&filter=repositories.tags.name~=v${tag}"
    fi
    fetch_api "${repo}/images?${query}" \
        | python3 "$(dirname "$0")/filter_images.py" tags "${tag_args[@]}"
}

cmd_id() {
    local repo=$1
    fetch_api "${repo}" | jq -r '._id // empty'
}

cmd_streams() {
    local repo=$1
    fetch_api "${repo}" | jq '.content_stream_tags'
}

cmd_images() {
    local repo=$1 tag=${2:-}
    local tag_args=()
    [[ -z "${tag}" ]] || tag_args=(--tag "${tag}")
    # Server-side filter narrows to images tagged vX.Y, avoiding the 500-image cap.
    # Client-side filter_images.py still runs as a second pass for exact matching.
    local query="page_size=500"
    if [[ -n "${tag}" ]]; then
        query+="&filter=repositories.tags.name~=v${tag}"
    fi
    fetch_api "${repo}/images?${query}" \
        | python3 "$(dirname "$0")/filter_images.py" images "${tag_args[@]}"
}

main() {
    command -v jq >/dev/null 2>&1 || { echo "Error: jq is required" >&2; exit 1; }
    command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is required" >&2; exit 1; }

    [[ $# -ge 2 ]] || usage

    local repo=$1 cmd=$2
    shift 2

    local tag=""
    while [[ $# -gt 0 ]]; do
        case $1 in
            --tag) [[ -n ${2:-} ]] || { echo "Error: --tag requires a value" >&2; exit 1; }; tag=$2; shift 2 ;;
            *) usage ;;
        esac
    done

    case ${cmd} in
        id)      cmd_id "${repo}" ;;
        tags)    cmd_tags "${repo}" "${tag}" ;;
        streams) cmd_streams "${repo}" ;;
        images)  cmd_images "${repo}" "${tag}" ;;
        *)       usage ;;
    esac
}

main "$@"
