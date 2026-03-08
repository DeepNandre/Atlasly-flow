# Construction Permitting Software: Master PRD & Strategic Truth Book

## 1. Industry Overview & Mission

The US construction industry is a $1.6 trillion market severely constrained by a highly fragmented and archaic pre-construction bottleneck: municipal permitting. There are over 20,000 distinct Authorities Having Jurisdiction (AHJs), such as city planning departments and county fire marshals, utilizing over 500,000 unique forms.

The traditional process relies on manual data entry, physical "permit expediters," and opaque bureaucratic review cycles. This results in massive delays, inflating holding costs, and locking up working capital for developers. The mission of this software is to build an "AI workforce" that completely automates AHJ research, application preparation, submission, and municipal comment resolution, ultimately capturing a multi-billion-dollar opportunity by replacing high-cost human consultants with a highly scalable, AI-native SaaS platform.

## 2. The Incumbent Landscape

To build a superior product, we must first map what our primary competitors are doing:

* **PermitFlow:** The closest direct competitor. They offer an end-to-end B2B software platform that uses AI agents to automate jurisdiction research, auto-fill applications, and submit them to municipalities. They act as a centralized dashboard for enterprise general contractors and integrate deeply with Procore.
* **Pulley:** A hybrid SaaS and "expert network" marketplace. They provide a workflow dashboard (featuring tools like "AutoParser" for municipal comments and "City Sync" for status tracking) but rely on a network of 300+ human contractors to handle the physical expediting.


* **GreenLite:** They bypass the software-only approach by employing certified in-house experts and AI (LiteTable) to conduct "Private Plan Reviews." They legally stamp plans for code compliance *before* submission, allowing developers to bypass local municipal backlogs entirely in jurisdictions that allow third-party reviews.


* **B2G Legacy Systems (Accela, Clariti, Cloudpermit):** These are the incumbent government-side portals. We do not compete with them; we must seamlessly integrate with their APIs to push and pull data.

## 3. Core Pain Points & "White Space" Opportunities

Our product must solve the core pain points that incumbents solve, but we will win by dominating the underserved "white spaces."

**The Baseline Pain Points (Must-Solve):**

* **The Black Box of Review:** Contractors submit plans and wait weeks with no visibility into the status.
* **Comment Letter Purgatory:** AHJs return dense, unstructured 40-page PDF documents detailing code violations. Deciphering these and assigning revisions to architects and engineers takes weeks.
* **Hyper-Local Chaos:** Every zip code requires different, obscure forms and localized zoning rule adherence.

**The "White Space" (Our Winning Differentiation):**

* **Upstream Generative Compliance:** Existing tools only act *after* the plans are drafted. We will build plugins for design software (Autodesk Revit) that use AI to check for code compliance in real-time *while* the architect is drawing.
* **FinTech & Capital Underwriting:** Permitting is a financial risk. We will integrate FinTech workflows to offer automated invoice factoring to sub-contractors upon permit issuance, or milestone-based billing tied to actual municipal approvals.


* **Trade-Specific Niche Workflows:** Instead of only targeting massive enterprise General Contractors, we will build specialized flows for high-velocity, high-volume trades (e.g., Solar, EV Charging, Commercial MEP contractors) who pull millions of simple permits but are ignored by enterprise software.

---

## 4. Staged Development Plan (Feature by Feature)

Do not attempt to build the entire system at once. Follow this staged, sequential development roadmap.

### Stage 1: The "Wedge" MVP (Automated Comment Resolution)

*Goal: Overcome enterprise switching costs by solving the most painful bottleneck immediately.*

* **Feature 1: The PDF AI Parser:** An upload interface where users drag-and-drop unstructured, 40-page PDF municipal comment letters.
* **Feature 2: LLM Extraction & Categorization:** Utilize a vision-capable LLM to read the PDF, extract individual code violations, and categorize them by discipline (e.g., Structural, Electrical, Plumbing).
* **Feature 3: Jira-Style Ticketing:** Automatically convert the extracted comments into actionable, structured task tickets.
* **Feature 4: Auto-Assignment Routing:** Allow the General Contractor to instantly assign these tickets to the specific sub-contractors or architects via email/dashboard notifications.
* **Success Metric:** Transform a 2-week manual review process into a 10-minute automated triage workflow.

### Stage 2: Achieving Incumbent Parity (Research & Submission Engine)

*Goal: Build out the core functionality that competes directly with PermitFlow and Pulley.*

* **Feature 1: Project Intake Wizard:** A dynamic questionnaire that ingests project details (location, type, size) and utilizes external APIs to instantly identify the governing AHJ and its specific requirements.
* **Feature 2: Smart Form Auto-Fill:** A database of digitized municipal forms. The system maps the project intake data to the specific PDF fields of the AHJ's unique forms, completely automating data entry.
* **Feature 3: "City Sync" Integration:** Web scrapers and API connectors that plug into B2G portals (Accela, OpenGov) to automatically pull real-time permit status updates, eliminating the need for contractors to manually refresh city websites.


* **Feature 4: Unified Multi-Project Dashboard:** A command center for project managers to view the status of hundreds of permits across different states and municipalities on a single screen.

### Stage 3: Building the Moat (Advanced AI & Proprietary Workflows)

*Goal: Create deep defensibility so competitors cannot replicate the software.*

* **Feature 1: Proprietary AHJ Feedback Loop (Data Moat):** Architect the database to log every rejection and approval reason per municipality. Over time, the AI learns the specific behavioral quirks of individual city reviewers, creating a predictive engine that no new startup can copy without historical transaction data.
* **Feature 2: Ecosystem Integrations:** Build robust bidirectional APIs with Procore (for project management synchronization) and standard accounting software.
* **Feature 3: Upstream CAD/BIM Plugin:** An extension for architectural software that runs instant pass/fail evaluations against digitized local zoning codes on 2D/3D models before they are ever exported to PDF.
* **Feature 4: Milestone Billing Engine:** A FinTech module that automatically releases escrow payments or triggers sub-contractor invoices the second the "City Sync" feature detects a permit has been officially issued.

---

## 5. Technical Architecture & External Resources

To execute this PRD, the development environment should leverage the following resources and architectural concepts:

**External APIs & Data Sources to Connect:**

1. **Shovels.ai API:** Crucial for early development. This API provides instant access to building permit data, contractor data, and geographical boundaries for thousands of US jurisdictions, saving you from having to map the AHJ landscape manually.
2. **B2G System APIs (The Integrations):**
* Accela Civic Platform API
* OpenGov API
* Cloudpermit API
* *Note: For municipalities without APIs, you will need to build secure, compliant web scrapers (like UI-TARS or specialized computer-use models) to extract portal statuses.*


3. **Construction Ecosystem APIs:**
* Procore API (Absolutely vital for B2B enterprise adoption).
* Autodesk Platform Services (Forge) API (for Phase 3 CAD integrations).



**AI & LLM Stack:**

* **Vision/Multimodal Models:** Required for parsing unstructured architectural plans and scanned PDF comment letters.
* **RAG (Retrieval-Augmented Generation) Architecture:** You will need to build a RAG pipeline that ingests and indexes public municipal building codes (IBC, IRC, and local zoning amendments). When the AI parses a comment letter, it must query this RAG database to cite the exact local code preventing hallucinations.

**Development Philosophy:**
Build the UI/UX to be extremely simple. Construction project managers do not have time for steep learning curves. The complexity (RAG pipelines, localized code databases, and web scrapers) must be entirely abstracted away behind a clean, consumer-grade interface.
