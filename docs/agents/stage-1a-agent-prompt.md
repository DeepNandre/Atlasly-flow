# Stage 1A Agent Prompt

Use the full content in `docs/agents/shared-context.md` as the first half of your prompt.

## Stage-specific mission
Focus on `docs/stages/stage-1a-comment-extraction.md`.

Perform deep research on how to execute Stage 1A:
- Multimodal PDF parsing pipelines for scanned municipal letters.
- Extraction schema design and robust confidence scoring.
- Quality benchmarking strategy (precision/recall by discipline and AHJ segment).
- Human-review queue design for low-confidence outputs.
- Citation grounding and hallucination controls.

Deliverables:
- Model/pipeline architecture options with recommended default.
- Evaluation harness design and threshold strategy.
- Production hardening checklist for extraction reliability.
