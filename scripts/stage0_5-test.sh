#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest \
  tests/stage0_5/test_stage0_5_contracts.py \
  tests/stage0_5/test_stage0_5_runtime_api.py

echo "Stage 0.5 service/runtime tests passed"
