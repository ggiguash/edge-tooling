#!/usr/bin/bash
set -euo pipefail

# Extract the analysis-relevant subset of a single sosreport tarball.
#
# Usage:
#   extract-sosreport.sh <sosreport.tar.xz>
#
# Only extracts:
#   - sos_commands/*/namespaces/*          (pod logs, events, pod YAML)
#   - sos_commands/*/inspect_*             (component command outputs)
#   - sos_commands/*/cluster-scoped-resources/*  (nodes, CRDs, webhooks)
#
# Journals live as plain-text journal_*.log files alongside the tarball.
#
# Output: <tarball-parent>/sos-extracted/<sosreport-name>/
#
# Extraction is idempotent: if the output directory already exists, it
# is left untouched. The output directory path is printed to stdout.

usage() {
    echo "Usage: $(basename "$0") <sosreport.tar.xz>" >&2
    exit 1
}

main() {
    [[ ${#} -ne 1 ]] && usage
    local tarball="${1}"

    [[ -f "${tarball}" ]] || { echo "Error: not a file: ${tarball}" >&2; exit 1; }

    local name
    name="$(basename "${tarball}" .tar.xz)"
    local dest
    dest="$(dirname "${tarball}")/sos-extracted/${name}"

    if [[ -d "${dest}" ]]; then
        echo "Cached: ${dest}" >&2
        echo "${dest}"
        return 0
    fi

    echo "Extracting ${name} (pod logs, inspect, cluster-scoped-resources only)" >&2
    mkdir -p "${dest}"

    if ! tar --no-same-owner --strip-components=1 --wildcards \
         -xf "${tarball}" -C "${dest}" \
         '*/sos_commands/*/namespaces/*' \
         '*/sos_commands/*/inspect_*' \
         '*/sos_commands/*/cluster-scoped-resources/*' 2>/dev/null; then
        echo "WARNING: extraction had errors or no matching files in ${name}" >&2
    fi

    echo "${dest}"
}

main "${@}"
