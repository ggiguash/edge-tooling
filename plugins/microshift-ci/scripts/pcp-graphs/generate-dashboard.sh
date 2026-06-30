#!/bin/bash
# Generate an interactive PCP performance dashboard from per-VM PCP archives.
#
# For each scenario that has PCP archives (pcp-archives.tar in vms/<host>/pcp/),
# extracts metrics and produces an interactive HTML dashboard.
#
# Usage: generate-dashboard.sh --workdir DIR [--parallel N] [--timezone TZ]
#
# Prerequisites: python3, and one of:
#   - pcp-export-pcp2json (native)
#   - podman or docker (container fallback)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORKDIR=""
PARALLEL=6
TIMEZONE="UTC"
PCP2JSON_MODE=""  # "native" or "container"
CONTAINER_RT=""   # "podman" or "docker"
CONTAINER_IMAGE="pcp2json-tool"

usage() {
    echo "Usage: ${0} --workdir DIR [--parallel N] [--timezone TZ]" >&2
    echo "  --workdir DIR   : work directory containing artifacts/<build_id>/ (required)" >&2
    echo "  --parallel N    : number of parallel extraction jobs (default: 6)" >&2
    echo "  --timezone TZ   : IANA timezone for timestamps (default: UTC)" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --workdir)
            [[ $# -lt 2 ]] && { echo "Error: --workdir requires a directory" >&2; usage; }
            WORKDIR="$2"; shift 2 ;;
        --parallel)
            [[ $# -lt 2 ]] && { echo "Error: --parallel requires a number" >&2; usage; }
            PARALLEL="$2"; shift 2 ;;
        --timezone)
            [[ $# -lt 2 ]] && { echo "Error: --timezone requires a value" >&2; usage; }
            TIMEZONE="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown argument: $1" >&2; usage ;;
    esac
done

if [[ -z "${WORKDIR}" ]]; then
    echo "Error: --workdir is required" >&2
    usage
fi

# ---------------------------------------------------------------------------
# pcp2json detection: native or container fallback
# ---------------------------------------------------------------------------

detect_pcp2json() {
    if command -v pcp2json >/dev/null 2>&1; then
        PCP2JSON_MODE="native"
        echo "Using native pcp2json" >&2
        return 0
    fi

    for rt in podman docker; do
        if command -v "${rt}" >/dev/null 2>&1; then
            CONTAINER_RT="${rt}"
            break
        fi
    done

    if [[ -z "${CONTAINER_RT}" ]]; then
        echo "ERROR: pcp2json not found and no container runtime (podman/docker) available." >&2
        echo "Install one of:" >&2
        echo "  - pcp-export-pcp2json (dnf install pcp-export-pcp2json)" >&2
        echo "  - podman or docker (for container fallback)" >&2
        exit 1
    fi

    PCP2JSON_MODE="container"
    ensure_container_image
}

ensure_container_image() {
    if ${CONTAINER_RT} image exists "${CONTAINER_IMAGE}" 2>/dev/null; then
        echo "Using ${CONTAINER_RT} container (image ${CONTAINER_IMAGE})" >&2
        return 0
    fi

    echo "Building ${CONTAINER_IMAGE} container image..." >&2
    ${CONTAINER_RT} build -t "${CONTAINER_IMAGE}" -f - . <<'DOCKERFILE'
FROM registry.fedoraproject.org/fedora-minimal:41
RUN microdnf install -y pcp-export-pcp2json python3-requests && microdnf clean all
ENTRYPOINT ["pcp2json"]
DOCKERFILE
}

# Run pcp2json on a PCP archive directory.
# Args: pcp_dir metrics...
# Stdout: JSON output
run_pcp2json() {
    local pcp_dir="$1"
    shift

    if [[ "${PCP2JSON_MODE}" == "native" ]]; then
        (cd "${pcp_dir}" && pcp2json -a . -t 15sec "$@") 2>/dev/null || true
    else
        ${CONTAINER_RT} run --rm -v "${pcp_dir}:/data:Z" "${CONTAINER_IMAGE}" \
            -a /data -t 15sec "$@" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# PCP tarball discovery and processing
# ---------------------------------------------------------------------------

find_pcp_tarballs() {
    find "${WORKDIR}/artifacts" -name "pcp-archives.tar" -path "*/vms/*/pcp/*" \
        2>/dev/null | sort
}

parse_tarball_path() {
    local tar_path="$1"
    local rel="${tar_path#"${WORKDIR}/artifacts/"}"

    BUILD_ID=$(echo "${rel}" | cut -d/ -f1)
    SCENARIO=$(echo "${tar_path}" | sed -nE 's|.*/scenario-info/([^/]+)/vms/.*|\1|p')
    VM_HOST=$(echo "${tar_path}" | sed -nE 's|.*/vms/([^/]+)/pcp/.*|\1|p')
}

# Extract a single metric type from a PCP archive dir.
# Args: pcp_dir output_json parse_script metrics...
extract_metric() {
    local pcp_dir="$1"
    local output_json="$2"
    local parse_script="$3"
    shift 3

    local tmpfile
    tmpfile=$(mktemp)

    if run_pcp2json "${pcp_dir}" "$@" > "${tmpfile}" && [[ -s "${tmpfile}" ]]; then
        if python3 "${SCRIPT_DIR}/${parse_script}" --timezone "${TIMEZONE}" \
                "${tmpfile}" "${output_json}" 2>/dev/null; then
            rm -f "${tmpfile}"
            return 0
        fi
    fi

    rm -f "${tmpfile}"
    return 1
}

process_tarball() {
    local tar_path="$1"

    parse_tarball_path "${tar_path}"

    if [[ -z "${BUILD_ID}" || -z "${SCENARIO}" || -z "${VM_HOST}" ]]; then
        echo "  SKIP: cannot parse path ${tar_path}" >&2
        return 0
    fi

    local output_dir="${WORKDIR}/pcp-dashboard/${BUILD_ID}/${SCENARIO}"
    mkdir -p "${output_dir}"

    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf '${tmp_dir}'" RETURN

    if ! tar xf "${tar_path}" -C "${tmp_dir}" 2>/dev/null; then
        echo "  ${SCENARIO}: tar extraction failed" >&2
        return 0
    fi

    # Find the PCP archive directory (contains the Latest folio or .meta files)
    local pcp_dir=""
    if [[ -f "${tmp_dir}/Latest" ]]; then
        pcp_dir="${tmp_dir}"
    else
        pcp_dir=$(find "${tmp_dir}" -name "Latest" -exec dirname {} \; 2>/dev/null | head -1)
        if [[ -z "${pcp_dir}" ]]; then
            pcp_dir=$(find "${tmp_dir}" -name "*.meta" -exec dirname {} \; 2>/dev/null | head -1)
        fi
    fi

    if [[ -z "${pcp_dir}" ]]; then
        echo "  ${SCENARIO}: no PCP archive found in tarball" >&2
        return 0
    fi

    local ok=0

    extract_metric "${pcp_dir}" "${output_dir}/cpu.json" "parse_cpu.py" \
        kernel.all.cpu.user kernel.all.cpu.sys kernel.all.cpu.idle kernel.all.cpu.wait.total \
        && ok=$((ok + 1))

    extract_metric "${pcp_dir}" "${output_dir}/mem.json" "parse_mem.py" \
        mem.util.used mem.util.free mem.util.cached mem.physmem \
        && ok=$((ok + 1))

    extract_metric "${pcp_dir}" "${output_dir}/io.json" "parse_pcp.py" \
        disk.dev.read disk.dev.write disk.dev.await disk.dev.aveq \
        && ok=$((ok + 1))

    extract_metric "${pcp_dir}" "${output_dir}/disk.json" "parse_disk_usage.py" \
        filesys.used filesys.capacity filesys.mountdir \
        && ok=$((ok + 1))

    echo "  ${BUILD_ID}/${SCENARIO} (${VM_HOST}): ${ok}/4 metrics" >&2
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

detect_pcp2json

export -f process_tarball parse_tarball_path run_pcp2json extract_metric
export SCRIPT_DIR WORKDIR TIMEZONE PCP2JSON_MODE CONTAINER_RT CONTAINER_IMAGE

tarballs=$(find_pcp_tarballs)

if [[ -z "${tarballs}" ]]; then
    echo "No per-VM PCP archives found in ${WORKDIR}/artifacts" >&2
    exit 0
fi

total=$(echo "${tarballs}" | wc -l | tr -d ' ')

# Container mode: run sequentially to avoid overwhelming the container runtime.
# Native mode: run in parallel.
if [[ "${PCP2JSON_MODE}" == "container" ]]; then
    echo "Processing PCP archives for ${total} scenario VMs (sequential, container mode)..." >&2
    while IFS= read -r tar_path; do
        process_tarball "${tar_path}"
    done <<< "${tarballs}"
else
    echo "Processing PCP archives for ${total} scenario VMs (${PARALLEL} parallel)..." >&2
    while IFS= read -r tar_path; do
        process_tarball "${tar_path}" &
        while [[ $(jobs -rp | wc -l) -ge ${PARALLEL} ]]; do
            wait -n 2>/dev/null || true
        done
    done <<< "${tarballs}"
    wait
fi

# Extract scenario metadata
echo "Extracting scenario metadata..." >&2
python3 "${SCRIPT_DIR}/extract_scenarios.py" --workdir "${WORKDIR}"

# Generate the HTML dashboard
echo "Generating HTML dashboard..." >&2
python3 "${SCRIPT_DIR}/create-pcp-dashboard.py" \
    --workdir "${WORKDIR}" --timezone "${TIMEZONE}"

output="${WORKDIR}/pcp-dashboard.html"
if [[ -f "${output}" ]]; then
    echo "Dashboard: ${output}" >&2
else
    echo "ERROR: Dashboard generation failed" >&2
    exit 1
fi
