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

fetch_api() {
    local url="${API_BASE}/$1"
    curl -s --fail --max-time 60 --retry 3 --retry-delay 5 "${url}"
}

cmd_tags() {
    local repo=$1 tag=${2:-}
    fetch_api "${repo}/images?page_size=500" \
        | jq --arg tag "${tag}" '
            [.data[].repositories[].tags[].name]
            | unique
            # Substring filter: --tag 5.0 matches "v5.0.1" and "4.15.0"
            | if $tag == "" then . else [.[] | select(contains($tag))] end'
}

cmd_id() {
    local repo=$1
    fetch_api "${repo}" | jq -r '._id'
}

cmd_streams() {
    local repo=$1
    fetch_api "${repo}" | jq '.content_stream_tags'
}

cmd_images() {
    local repo=$1 tag=${2:-}
    [[ -n "${tag}" ]] || { echo "Error: --tag is required for images" >&2; return 1; }
    # freshness_grades is a pre-computed degradation schedule (e.g. B→C→D→F),
    # not a history — select the entry whose date range contains today.
    fetch_api "${repo}/images?page_size=500" | jq --arg tag "${tag}" '
        [.data[]
         # Version-aware filter: --tag 5.0 matches "v5.0.1" but NOT "4.15.0"
         | select(any(.repositories[].tags[]; .name | test("(^|[^0-9])" + ($tag | gsub("\\."; "\\.")))))
         | {
            _id,
            tags: [.repositories[].tags[].name] | sort_by(length),
            architecture: .architecture,
            digest: (.image_id | split(":")[1][:12]),
            freshness_grade: ([.freshness_grades[] | select(.start_date <= (now | todate) and ((.end_date // "9999-12-31T00:00:00+00:00") > (now | todate)))] | first | .grade // null),
            creation_date: .creation_date,
            last_update_date: .last_update_date
        }] | sort_by(.tags[0], .architecture)'
}

main() {
    command -v jq >/dev/null 2>&1 || { echo "Error: jq is required" >&2; exit 1; }

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
