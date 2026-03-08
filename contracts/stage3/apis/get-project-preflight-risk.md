# GET /projects/{projectId}/preflight-risk (Stage 3 v1)

## Purpose
Return permit-specific preflight risk insights with optional recommendations and explainability.

## Parameters
- Path:
  - `projectId` (required): UUIDv4.
- Query:
  - `permit_type` (required): `commercial_ti` | `rooftop_solar` | `electrical_service_upgrade`.
  - `ahj_id` (required): canonical AHJ identifier, regex `^[a-z0-9]+(\.[a-z0-9_]+)+$`.
  - `as_of` (optional): RFC3339 timestamp; defaults to server now.
  - `include_recommendations` (optional): boolean; defaults to `true`.
  - `include_explainability` (optional): boolean; defaults to `true`.

## Derived server context (not client-provided)
- `organization_id` from tenant auth context.
- `requester_role` from RBAC claims.
- `requirements_version_id` from active AHJ requirements.
- `feature_snapshot_ref`, `model_version`, `calibration_version` from intelligence service.

## Response fields (minimum)
- `risk_score` (0..1)
- `risk_band` (`low` | `medium` | `high` | `critical`)
- `confidence_score` (0..1)
- `model_version`
- `top_risk_factors[]` when explainability enabled
- `recommended_actions[]` when recommendations enabled
