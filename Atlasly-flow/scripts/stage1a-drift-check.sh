#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_events=(
  "comment_letter.parsing_started"
  "comment_letter.extraction_completed"
  "comment_letter.approved"
)

for ev in "${required_events[@]}"; do
  rg -q "$ev" "$root_dir/db/migrations" "$root_dir/contracts/stage1a/events" "$root_dir/docs/implementation/stage-1a" || {
    echo "Missing required event reference: $ev" >&2
    exit 1
  }
done

# Ensure no unregistered Stage 1A event literals are present.
found_events="$(rg --no-filename -o "comment_letter\\.[a-z_]+" \
  "$root_dir/db" \
  "$root_dir/contracts/stage1a/events" \
  "$root_dir/docs/implementation/stage-1a" \
  | sort -u)"

for ev in $found_events; do
  ok=0
  for required in "${required_events[@]}"; do
    if [[ "$ev" == "$required" ]]; then
      ok=1
      break
    fi
  done
  if [[ $ok -ne 1 ]]; then
    echo "Found unregistered Stage 1A event literal: $ev" >&2
    exit 1
  fi
done

# Ensure API paths are locked.
rg -q "^  /comment-letters:$" "$root_dir/contracts/stage1a/api/comment-letters.openapi.yaml"
rg -q "^  /comment-letters/\{letterId\}:$" "$root_dir/contracts/stage1a/api/comment-letters.openapi.yaml"
rg -q "^  /comment-letters/\{letterId\}/extractions:$" "$root_dir/contracts/stage1a/api/comment-letters.openapi.yaml"
rg -q "^  /comment-letters/\{letterId\}/approve:$" "$root_dir/contracts/stage1a/api/comment-letters.openapi.yaml"

echo "Stage 1A contract drift checks passed"
