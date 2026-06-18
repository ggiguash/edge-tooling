#!/usr/bin/bash
set -euo pipefail

# Extract sosreport archives from downloaded Prow job artifacts and write
# a JSON index of the high-signal files inside them.
#
# Shared across components (MicroShift, LVMS, etc.) via symlinks in each
# plugin's scripts/ directory. Intended for analysis agents that cannot
# run tar directly (CI permission allowlist) — this script is the one
# permitted mechanism for sosreport extraction.
#
# Usage:
#   extract-sosreport.sh <artifacts-dir> <dest>
#
#   <artifacts-dir>: local job artifacts directory (searched recursively
#                    for sosreport-*.tar.xz)
#   <dest>:          extraction destination directory
#
# Output: writes <dest>/index.json:
#   {"sosreports": [{
#      "archive": "<tarball path>",
#      "extracted_to": "<dir>",
#      "journals": ["..."],
#      "namespace_pod_logs": "<dir or empty string>",
#      "highlights": [{"file": "...", "line": N, "text": "..."}]
#   }]}
#
# Extraction is idempotent: if <dest>/index.json already exists the
# script exits immediately.
#
# Progress/errors: stderr. Absence of sosreports is NOT an error — the
# caller records it as an analysis gap.

HIGHLIGHT_RE='panic|OOM|oom-kill|segfault|Failed to start|level=error|FATAL|leader election lost'
MAX_HIGHLIGHTS=100

usage() {
    echo "Usage: $(basename "$0") <artifacts-dir> <dest>" >&2
    exit 1
}

main() {
    [[ ${#} -ne 2 ]] && usage
    local artifacts_dir="${1}"
    local dest="${2}"

    [[ -d "${artifacts_dir}" ]] || { echo "Error: not a directory: ${artifacts_dir}" >&2; exit 1; }

    local -a tarballs=()
    while IFS= read -r t; do
        tarballs+=("${t}")
    done < <(find "${artifacts_dir}" -name 'sosreport-*.tar.xz' | sort)

    if [[ -f "${dest}/index.json" ]]; then
        echo "Cached: ${dest}/index.json" >&2
        return 0
    fi

    if [[ ${#tarballs[@]} -eq 0 ]]; then
        echo "No sosreports found in ${artifacts_dir}" >&2
        mkdir -p "${dest}"
        echo '{"sosreports": [], "note": "no sosreport found"}' > "${dest}/index.json"
        return 0
    fi

    echo "Found ${#tarballs[@]} sosreport(s)" >&2

    local result='{"sosreports": []}'
    local tarball
    for tarball in "${tarballs[@]}"; do
        local name
        name="$(basename "${tarball}" .tar.xz)"
        local outdir="${dest}/${name}"

        echo "  extracting: ${name}" >&2
        mkdir -p "${outdir}"
        # Sosreport tarballs contain a single top-level directory named
        # after the archive — strip it so files land directly in outdir.
        tar --no-same-owner --strip-components=1 -xf "${tarball}" -C "${outdir}"

        # Index high-signal locations. Journal command output lands under
        # per-plugin dirs (sos_commands/logs/, sos_commands/microshift/, ...).
        local journals_json
        journals_json=$(find "${outdir}" \
            \( -path '*/sos_commands/*journalctl*' -o -path '*/var/log/journal/*' \) \
            -type f 2>/dev/null | sort | jq -R . | jq -s .)

        local ns_logs
        ns_logs=$(find "${outdir}" -type d -path '*/sos_commands/*/namespaces' 2>/dev/null | head -1)

        # Pre-grep highlights across journals, component command output, and
        # dead-container logs (previous.log explains why a container exited).
        local -a scan_targets=()
        while IFS= read -r f; do
            scan_targets+=("${f}")
        done < <(find "${outdir}" \
            \( -path '*/sos_commands/*journalctl*' -o -path '*/sos_commands/*/inspect_*' \
               -o -path '*/namespaces/*/logs/previous.log' \) \
            -type f 2>/dev/null | sort)

        local highlights_json="[]"
        if [[ ${#scan_targets[@]} -gt 0 ]]; then
            # Grep high-signal patterns and parse each match into a
            # {file, line, text} JSON object for the index.
            highlights_json=$({ grep -nHIE "${HIGHLIGHT_RE}" "${scan_targets[@]}" 2>/dev/null || true; } \
                | head -${MAX_HIGHLIGHTS} \
                | jq -R 'capture("^(?<file>[^:]+):(?<line>[0-9]+):(?<text>.*)$")
                         | {file: .file, line: (.line | tonumber), text: (.text[0:200])}' \
                | jq -s .)
        fi

        result=$(echo "${result}" | jq \
            --arg archive "${tarball}" \
            --arg outdir "${outdir}" \
            --argjson journals "${journals_json}" \
            --arg nslogs "${ns_logs}" \
            --argjson highlights "${highlights_json}" \
            '.sosreports += [{
                archive: $archive,
                extracted_to: $outdir,
                journals: $journals,
                namespace_pod_logs: $nslogs,
                highlights: $highlights
            }]')
    done

    echo "${result}" > "${dest}/index.json"
    echo "Index written to ${dest}/index.json" >&2
}

main "${@}"
