BEGIN;

DROP POLICY IF EXISTS review_outcomes_write_pol ON review_outcomes;
DROP POLICY IF EXISTS review_outcomes_select_pol ON review_outcomes;
DROP POLICY IF EXISTS code_citations_write_pol ON code_citations;
DROP POLICY IF EXISTS code_citations_select_pol ON code_citations;
DROP POLICY IF EXISTS ahj_comments_write_pol ON ahj_comments;
DROP POLICY IF EXISTS ahj_comments_select_pol ON ahj_comments;
DROP POLICY IF EXISTS permit_reviews_write_pol ON permit_reviews;
DROP POLICY IF EXISTS permit_reviews_select_pol ON permit_reviews;

ALTER TABLE review_outcomes NO FORCE ROW LEVEL SECURITY;
ALTER TABLE code_citations NO FORCE ROW LEVEL SECURITY;
ALTER TABLE ahj_comments NO FORCE ROW LEVEL SECURITY;
ALTER TABLE permit_reviews NO FORCE ROW LEVEL SECURITY;

ALTER TABLE review_outcomes DISABLE ROW LEVEL SECURITY;
ALTER TABLE code_citations DISABLE ROW LEVEL SECURITY;
ALTER TABLE ahj_comments DISABLE ROW LEVEL SECURITY;
ALTER TABLE permit_reviews DISABLE ROW LEVEL SECURITY;

DROP TABLE IF EXISTS review_outcomes;
DROP TABLE IF EXISTS code_citations;
DROP TABLE IF EXISTS ahj_comments;
DROP TABLE IF EXISTS permit_reviews;

COMMIT;

