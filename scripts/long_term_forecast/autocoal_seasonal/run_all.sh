#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"

indexes=(CCI4500 CCI5000 CCI5500 CCI3800out CCI4700out CCI5500out)

for index in "${indexes[@]}"; do
  echo
  echo "=============================="
  echo "Running seasonal pipeline: $index"
  echo "=============================="
  bash "$script_dir/run_one.sh" "$index"
done

echo
echo "=============================="
echo "Synchronizing seasonal coal forecasts"
echo "=============================="
cd "$script_dir/../../.."
python autoinfer/sync_forecasts.py \
  --folder autoinfer/seasonal \
  --strength "${SYNC_STRENGTH:-0.8}" \
  --anchor-mode "${SYNC_ANCHOR_MODE:-imported_mean}" \
  --align-targets "${SYNC_ALIGN_TARGETS:-domestic}"
