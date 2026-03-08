#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest discover -s tests/stage0_5 -p 'test_*.py'

echo "Stage 0.5 hardening/runtime tests passed"
