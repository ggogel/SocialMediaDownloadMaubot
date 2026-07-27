#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/.." && pwd)"
output_path="${1:-"$repo_dir/package.mbp"}"
python_bin="${PYTHON:-python3}"

if [[ "$output_path" != /* ]]; then
    output_path="$(pwd)/$output_path"
fi

build_dir="$(mktemp -d "${TMPDIR:-/tmp}/socialmediadownload-build.XXXXXX")"
payload_dir="$build_dir/payload"

cleanup() {
    find "$build_dir" -depth -delete
}
trap cleanup EXIT

mkdir "$payload_dir"

"$python_bin" -m pip install \
    --disable-pip-version-check \
    --no-compile \
    --no-deps \
    --requirement "$repo_dir/requirements.txt" \
    --target "$payload_dir"

if [[ -d "$payload_dir/bin" ]]; then
    find "$payload_dir/bin" -depth -delete
fi

cp "$repo_dir/base-config.yaml" "$payload_dir/"
cp "$repo_dir/maubot.yaml" "$payload_dir/"
cp "$repo_dir/socialmediadownload.py" "$payload_dir/"

(
    cd "$payload_dir"
    zip -qr "$build_dir/package.mbp" .
)

mv -f "$build_dir/package.mbp" "$output_path"
echo "Built $output_path"
