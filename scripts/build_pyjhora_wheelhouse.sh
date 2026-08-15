#!/usr/bin/env bash
set -euo pipefail

release_root=${1:?Pass the absolute release root}
source_dir="${release_root}/runtime/pyjhora-source/pyjhora-mcp"
wheelhouse="${release_root}/runtime/pyjhora-wheelhouse"

chmod -R u+rwX,go+rX "${source_dir}"
find "${source_dir}" -type d -exec chmod 0755 {} +
find "${source_dir}" -type f -exec chmod 0644 {} +

mkdir -p "${wheelhouse}"
find "${wheelhouse}" -mindepth 1 -maxdepth 1 -type f -delete

docker run --rm \
  --volume "${source_dir}:/src:ro" \
  --volume "${wheelhouse}:/wheelhouse" \
  python:3.11.13-slim-bookworm@sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1 \
  sh -ceu 'python -m pip wheel --wheel-dir /wheelhouse /src'

cd "${wheelhouse}"
sha256sum -- *.whl | sort -k2 > SHA256SUMS
cd "${release_root}"
python3 scripts/wheelhouse_contract.py "${wheelhouse}"
