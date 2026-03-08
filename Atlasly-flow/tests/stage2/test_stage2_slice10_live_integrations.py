from __future__ import annotations

from datetime import datetime, timezone
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage2.ahj_intelligence import AddressInput
from scripts.stage2.ahj_intelligence import ShovelsClient
from scripts.stage2.connector_credentials import ConnectorCredentialError
from scripts.stage2.connector_credentials import ConnectorCredentialVault
from scripts.stage2.live_connectors import AccelaLiveAdapter
from scripts.stage2.live_connectors import build_live_connector_adapter
from scripts.stage2.connector_runtime import ConnectorPollError
from scripts.stage2.repositories import Stage2PersistenceStore
from scripts.stage2.repositories import Stage2Repository


class Stage2Slice10LiveIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Stage2Repository(Stage2PersistenceStore.empty())
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.vault = ConnectorCredentialVault(repository=self.repo, env={})

    def test_connector_vault_rotate_and_resolve(self):
        self.vault.rotate_reference(
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id=None,
            credential_ref="accela_prod_token",
            created_by="owner-user",
            scopes=["records:read"],
            auth_scheme="bearer",
        )
        env = {"ATLASLY_CONNECTOR_SECRET_ACCELA_PROD_TOKEN": "secret-token"}
        vault = ConnectorCredentialVault(repository=self.repo, env=env)
        auth = vault.resolve_auth(
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id="ca.san_jose.building",
        )
        self.assertEqual(auth.credential_ref, "accela_prod_token")
        self.assertEqual(auth.headers()["Authorization"], "Bearer secret-token")

    def test_connector_vault_missing_secret_fails(self):
        self.vault.rotate_reference(
            organization_id=self.org_id,
            connector="accela_api",
            ahj_id=None,
            credential_ref="missing_secret",
            created_by="owner-user",
        )
        with self.assertRaises(ConnectorCredentialError) as ctx:
            self.vault.resolve_auth(
                organization_id=self.org_id,
                connector="accela_api",
                ahj_id=None,
            )
        self.assertEqual(ctx.exception.status, 503)

    def test_accela_adapter_parses_records_payload(self):
        adapter = AccelaLiveAdapter(
            base_url="https://apis.accela.com",
            headers={"Authorization": "Bearer test"},
        )
        payload = {
            "result": [
                {
                    "id": "permit-001",
                    "status": {"value": "Under Review"},
                    "lastModifiedDate": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
        with patch("scripts.stage2.live_connectors._http_get_json", return_value=payload):
            observations = adapter.poll(ahj_id="ca.san_jose.building")
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].permit_id, "permit-001")
        self.assertEqual(observations[0].raw_status, "Under Review")

    def test_build_live_connector_requires_credential(self):
        with self.assertRaises(ConnectorPollError) as ctx:
            build_live_connector_adapter(
                organization_id=self.org_id,
                connector="accela_api",
                ahj_id=None,
                repository=self.repo,
                env={},
            )
        self.assertIn("not_found", str(ctx.exception))

    def test_shovels_resolve_ahj_parses_address_and_permit_samples(self):
        client = ShovelsClient(api_key="test-key")
        with patch(
            "scripts.stage2.ahj_intelligence._http_get_json",
            side_effect=[
                {"results": [{"geo_id": "geo-1", "jurisdiction_id": "ca.san_jose.building"}]},
                {
                    "results": [
                        {"jurisdiction": "City of San Jose", "status": "issued"},
                        {"jurisdiction": "City of San Jose", "status": "under_review"},
                    ]
                },
            ],
        ):
            result = client.resolve_ahj(
                address=AddressInput(
                    line1="200 Market St",
                    city="San Jose",
                    state="CA",
                    postal_code="95113",
                )
            )
        self.assertEqual(result["geo_id"], "geo-1")
        self.assertEqual(result["ahj_id"], "ca.san_jose.building")
        self.assertEqual(result["sample_permit_count"], 2)


if __name__ == "__main__":
    unittest.main()
