#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

python3 -m unittest \
  tests.stage0.test_stage0_contracts \
  tests.stage0.test_stage0_foundation_runtime

