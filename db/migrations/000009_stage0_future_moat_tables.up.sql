BEGIN;

CREATE TABLE permit_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  permit_id uuid NOT NULL,
  review_cycle integer NOT NULL,
  reviewer text NULL,
  submitted_at timestamptz NULL,
  outcome text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT permit_reviews_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT permit_reviews_permit_fk
    FOREIGN KEY (organization_id, permit_id)
    REFERENCES permits(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT permit_reviews_cycle_chk CHECK (review_cycle > 0)
);

CREATE UNIQUE INDEX permit_reviews_cycle_unique
  ON permit_reviews (permit_id, review_cycle);

CREATE TABLE ahj_comments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  permit_review_id uuid NOT NULL,
  citation_text text NOT NULL,
  discipline text NULL,
  severity text NULL,
  raw_source jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ahj_comments_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT ahj_comments_permit_review_fk
    FOREIGN KEY (organization_id, permit_review_id)
    REFERENCES permit_reviews(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT ahj_comments_citation_nonempty_chk CHECK (length(trim(citation_text)) > 0)
);

CREATE TABLE code_citations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  ahj_comment_id uuid NOT NULL,
  code_system text NOT NULL,
  section text NOT NULL,
  excerpt text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT code_citations_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT code_citations_ahj_comment_fk
    FOREIGN KEY (organization_id, ahj_comment_id)
    REFERENCES ahj_comments(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT code_citations_code_system_nonempty_chk CHECK (length(trim(code_system)) > 0),
  CONSTRAINT code_citations_section_nonempty_chk CHECK (length(trim(section)) > 0)
);

CREATE TABLE review_outcomes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  permit_review_id uuid NOT NULL,
  resolution_status text NOT NULL,
  resolved_by uuid NULL REFERENCES users(id),
  resolved_at timestamptz NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT review_outcomes_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT review_outcomes_permit_review_fk
    FOREIGN KEY (organization_id, permit_review_id)
    REFERENCES permit_reviews(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT review_outcomes_resolution_status_nonempty_chk CHECK (length(trim(resolution_status)) > 0)
);

CREATE INDEX permit_reviews_org_id_id_idx
  ON permit_reviews (organization_id, id);

CREATE INDEX permit_reviews_permit_id_created_at_idx
  ON permit_reviews (permit_id, created_at DESC);

CREATE INDEX ahj_comments_org_id_id_idx
  ON ahj_comments (organization_id, id);

CREATE INDEX ahj_comments_permit_review_id_idx
  ON ahj_comments (permit_review_id);

CREATE INDEX code_citations_org_id_id_idx
  ON code_citations (organization_id, id);

CREATE INDEX code_citations_ahj_comment_id_idx
  ON code_citations (ahj_comment_id);

CREATE INDEX review_outcomes_org_id_id_idx
  ON review_outcomes (organization_id, id);

CREATE INDEX review_outcomes_permit_review_id_idx
  ON review_outcomes (permit_review_id);

ALTER TABLE permit_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE ahj_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE code_citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_outcomes ENABLE ROW LEVEL SECURITY;

ALTER TABLE permit_reviews FORCE ROW LEVEL SECURITY;
ALTER TABLE ahj_comments FORCE ROW LEVEL SECURITY;
ALTER TABLE code_citations FORCE ROW LEVEL SECURITY;
ALTER TABLE review_outcomes FORCE ROW LEVEL SECURITY;

CREATE POLICY permit_reviews_select_pol
  ON permit_reviews FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY permit_reviews_write_pol
  ON permit_reviews FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

CREATE POLICY ahj_comments_select_pol
  ON ahj_comments FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY ahj_comments_write_pol
  ON ahj_comments FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

CREATE POLICY code_citations_select_pol
  ON code_citations FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY code_citations_write_pol
  ON code_citations FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

CREATE POLICY review_outcomes_select_pol
  ON review_outcomes FOR SELECT
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_access(organization_id)
  );

CREATE POLICY review_outcomes_write_pol
  ON review_outcomes FOR ALL
  USING (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  )
  WITH CHECK (
    organization_id = app_current_organization_id()
    AND app_has_org_role(organization_id, ARRAY['owner', 'admin', 'pm', 'reviewer']::membership_role[])
  );

COMMIT;

