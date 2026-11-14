#!/usr/bin/env bash
set -euo pipefail
work_dir=$(mktemp -d)
trap 'find "$work_dir" -type f -delete; rmdir "$work_dir"' EXIT
curl -fsSL --retry 3 -o "$work_dir/infisical.tar.gz" https://github.com/Infisical/cli/releases/download/v0.45.6/cli_0.45.6_linux_amd64.tar.gz
printf '%s  %s\n' b427391e76113e351fa0509d6493cb400577dec26b28afb462c2c2f9c5a37d4d "$work_dir/infisical.tar.gz" | sha256sum -c -
tar -xzf "$work_dir/infisical.tar.gz" -C "$work_dir" infisical
sudo install -m 755 "$work_dir/infisical" /usr/local/bin/infisical
