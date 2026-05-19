#!/usr/bin/env bash
# Pack the curated library into repo.tar.gz.
#
# Includes only:
#   - STEP files  (*.step, *.stp)
#   - Altium footprints (*.PcbLib)
#   - Altium symbols   (*.SchLib)
#   - README* at the repo root
#
# Excludes any path component containing a non-ASCII byte (UTF-8 file names).
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
OUT="${REPO_TARBALL_OUT:-${REPO_ROOT}/repo.tar.gz}"

cd "${REPO_ROOT}"

list="$(mktemp)"
trap 'rm -f "${list}"' EXIT

# Collect everything we want to ship. -print0 to be safe with spaces.
find . \
    -path ./.git -prune -o \
    -type f \( \
        -iname '*.step' -o \
        -iname '*.stp' -o \
        -iname '*.PcbLib' -o \
        -iname '*.SchLib' \
    \) -print0 > "${list}"

# README* lives at the repo root only.
find . -maxdepth 1 -type f -iname 'readme*' -print0 >> "${list}"

# Filter out any path containing a byte outside printable ASCII (0x20-0x7e)
# or tab/newline. With LC_ALL=C, grep operates on bytes and [:print:] is ASCII.
filtered="$(mktemp)"
trap 'rm -f "${list}" "${filtered}"' EXIT
LC_ALL=C tr '\0' '\n' < "${list}" \
    | LC_ALL=C grep -v '[^[:print:]]' \
    > "${filtered}"

count="$(wc -l < "${filtered}" | tr -d ' ')"
echo "Packing ${count} files into ${OUT}"

if [[ "${count}" -eq 0 ]]; then
    echo "No files matched the include rules - aborting." >&2
    exit 1
fi

# GNU tar on linux. -T - reads NUL-delimited names when given --null,
# but we have newline-delimited; -T plain handles that.
tar -czf "${OUT}" -T "${filtered}"

echo "Wrote ${OUT} ($(du -h "${OUT}" | cut -f1))"
