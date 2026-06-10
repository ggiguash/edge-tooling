#!/bin/bash
set -euo pipefail

API_BASE="https://catalog.redhat.com/api/containers/v1/repositories/registry/registry.access.redhat.com/repository"

usage() {
    cat >&2 <<EOF
Usage: $(basename "$0") <repository> <command> [options]

Arguments:
  repository   Full repository path (e.g. openshift4/microshift-bootc-rhel9)

Commands:
  tags      List all tags for all images
  streams   List content streams (e.g. 4.18, 4.19, 4.20)
  images    List all images with arch, digest, health, and dates (filterable via --tag)

Options:
  --tag TAG    Filter images to a specific tag
EOF
    exit 1
}

fetch_api() {
    local url="${API_BASE}/$1"
    local attempt result
    for attempt in 1 2 3; do
        if result=$(curl -s --fail "${url}"); then
            echo "${result}"
            return 0
        fi
        sleep "${attempt}"
    done
    echo "Error: failed to fetch ${url} after 3 attempts" >&2
    return 1
}

cmd_tags() {
    local repo=$1
    fetch_api "${repo}/images?page_size=500" \
        | jq '[.data[].repositories[].tags[].name] | unique'
}

cmd_streams() {
    local repo=$1
    fetch_api "${repo}" | jq '.content_stream_tags'
}

cmd_images() {
    local repo=$1 tag=${2:-}
    fetch_api "${repo}/images?page_size=500" | jq --arg tag "${tag}" '
        [.data[]
         | select($tag == "" or any(.repositories[].tags[]; .name == $tag))
         | {
            tag: ([.repositories[].tags[].name | select(startswith("v"))] | sort_by(length) | first // null),
            architecture: .architecture,
            digest: (.image_id | split(":")[1][:12]),
            freshness_grade: (.freshness_grades | last | .grade // null),
            grade_start_date: (.freshness_grades | last | .start_date // null),
            last_update_date: .last_update_date
        }] | sort_by(.tag, .architecture)'
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
        tags)    cmd_tags "${repo}" ;;
        streams) cmd_streams "${repo}" ;;
        images)  cmd_images "${repo}" "${tag}" ;;
        *)       usage ;;
    esac
}

main "$@"
