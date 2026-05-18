#!/usr/bin/env bash
# Remove generated comparison results while preserving nuclear data in run_artifacts/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR"

rm -rf results
rm -f openmc_result_dict.json fispact_result_dict.json exp_data_dict.json fispact.json
rm -f docs/*.png
rm -rf __pycache__ scripts/__pycache__

echo "Removed generated results, result JSON, docs PNGs, and Python caches."
echo "Preserved run_artifacts/ nuclear data and extracted fns/ benchmark inputs."
echo "Preserved overview.html dashboard."
