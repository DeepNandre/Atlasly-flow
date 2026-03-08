# Construction Permitting Market and Incumbent Analysis (US)

Date checked: March 3, 2026

## Why this matters
The core market reality is unchanged: permitting is a fragmented, local process, and winning products reduce cycle time uncertainty, not just form-filling time.

## Incumbent teardown

### 1) PermitFlow (direct software incumbent)
What they publicly position:
- End-to-end permitting workflows across project types with dedicated product surfaces for:
  - Permit Portfolio
  - Research Agent
  - Intake Agent
  - Inspections & Closeouts
  - License Management
- Broad US coverage claim and enterprise messaging.

What this implies for us:
- The competitive baseline is no longer only "submission + status"; it includes a full permit lifecycle control plane.
- Their packaging around "agents" means users expect automation-first UX, not manual wizard fatigue.

## 2) Pulley (hybrid software + expert network)
What they publicly position:
- Pull permits in any US city via software plus local permitting experts.
- Fast upfront estimate of cost/timeline plus optional hands-on service execution.

What this implies for us:
- Service-backed execution is still a moat in edge-case jurisdictions.
- To compete without a large field workforce, we need stronger exception-handling workflows, confidence scoring, and handoff tooling.

## 3) GreenLite (AI + expert-assisted permitting/compliance)
What they publicly position:
- AI + local experts for permits, zoning approvals, and code compliance.
- Strong developer/owner outcomes language (cycle-time and risk reduction).

What this implies for us:
- "Compliance before submission" is becoming table stakes for higher-value projects.
- Our Stage 3 moat (predictive rejection and preflight risk) should be shipped early as a differentiator, not left as long-term R&D.

## 4) Permittable (AI-forward emerging player)
What they publicly position:
- AI transforms project documents into permit packages and workflows; explicit support for portfolio management.

What this implies for us:
- New entrants are attacking document-to-application automation quickly.
- We need stronger contract reliability and workflow governance than "AI extraction only" products.

## 5) Legacy government system layer (not direct competitors, critical integration layer)

### Accela
- Government platform for planning/permitting, licensing, inspections, and self-service.

### OpenGov Permitting & Licensing
- Public docs describe APIs for permit applications and inspections.

### Cloudpermit
- Public API docs (OpenAPI, versioning policy).

### Clariti
- Public product positioning around permitting/licensing workflows for local governments.

Implication across all legacy systems:
- Integration robustness is product-critical: retry strategy, auth rotation, schema versioning, provenance capture, and human fallback queues must be first-class.

## Adjacent accelerators and constraint systems

### NREL SolarAPP+
- National initiative for instant residential solar permitting in participating jurisdictions.
- For solar verticals, we should support SolarAPP+ routing before defaulting to manual municipal flow.

### Shovels data platform
- Provides permit and planning intelligence APIs; useful for AHJ mapping, demand forecasting, and market expansion.

### Autodesk Platform Services + Revit API
- Foundation for upstream BIM/CAD compliance workflows.

### Stripe Connect
- Foundation for milestone escrow and payout orchestration.

## Competitive feature matrix (what users now expect)

| Capability | PermitFlow | Pulley | GreenLite | Required for Atlasly MVP |
|---|---|---|---|---|
| Multi-project permit portfolio | Yes | Yes | Partial | Yes |
| AHJ research automation | Yes | Partial | Partial | Yes |
| Intake + autofill orchestration | Yes | Yes | Partial | Yes |
| Status sync / tracking | Yes | Yes | Yes | Yes |
| Comment parsing and routing | Implied/yes | Yes | Partial | Yes |
| Inspection/closeout workflows | Yes | Service-backed | Partial | Yes (baseline) |
| License management | Yes | Service-backed | Unknown | Yes (baseline) |
| Service network fallback | Unknown | Yes | Yes | Needed via partner model |
| Pre-submission compliance intelligence | Partial | Partial | Strong | Yes (differentiator) |
| Financial orchestration | Limited public detail | Limited public detail | Limited public detail | Yes (differentiator) |

## Hard product truths
1. A pure parser is not a product moat; workflow reliability is.
2. Enterprise buyers need auditability, deterministic fallbacks, and clear ownership per failure mode.
3. The biggest value unlock is cycle-time predictability (variance reduction), not only average-time reduction.
4. Vertical flows (solar, EV charging, MEP) are faster GTM wedges than generic "all construction".

## Sources
- PermitFlow main site and product pages: https://www.permitflow.com/
- PermitFlow product page (agents/lifecycle modules): https://www.permitflow.com/product
- PermitFlow license management: https://www.permitflow.com/license-management
- Pulley construction permitting page: https://www.withpulley.com/
- GreenLite site: https://greenlite.com/
- Permittable site: https://www.permittable.ai/
- Accela product pages: https://www.accela.com/solutions/planning-and-permitting/
- OpenGov developer docs landing: https://developers.opengov.com/
- OpenGov API reference landing: https://developers.opengov.com/reference
- Cloudpermit API docs: https://developer.cloudpermit.com/
- Clariti permitting and licensing page: https://www.claritisoftware.com/permits-and-licensing
- NREL SolarAPP+: https://www.nrel.gov/solar/solarapp.html
- Shovels API docs: https://developer.shovels.ai/
- Autodesk Platform Services docs: https://aps.autodesk.com/developer/documentation
- Revit API docs: https://www.revitapidocs.com/
- Stripe Connect docs: https://docs.stripe.com/connect
