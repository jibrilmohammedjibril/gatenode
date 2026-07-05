import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ClientKycRegressionTests(unittest.TestCase):
    def test_client_unit_model_exposes_address_metadata(self):
        source = (ROOT / "client/core/models.py").read_text()
        self.assertIn("address_metadata = Column(JSON, nullable=True)", source)

    def test_kyc_flow_uses_nomba_wallet_creation(self):
        source = (ROOT / "client/routes/kyc.py").read_text()
        helper_source = (ROOT / "client/core/wallet_setup.py").read_text()
        self.assertIn("from core.wallet_setup import provision_wallet_virtual_account", source)
        self.assertIn("wallet_profile = await provision_wallet_virtual_account(", source)
        self.assertIn('"virtualAccount": wallet_virtual_account_payload(wallet_profile)', source)
        self.assertIn("create_virtual_account(", helper_source)
        self.assertIn("wallet_profile.nomba_account_ref", helper_source)
        self.assertIn("wallet_profile.nomba_account_id", helper_source)
        self.assertIn("wallet_profile.status = \"active\"", helper_source)
        self.assertIn("user.bvn_verified = True", helper_source)

    def test_kyc_flow_requires_wallet_profile_state_checks(self):
        source = (ROOT / "client/routes/kyc.py").read_text()
        helper_source = (ROOT / "client/core/wallet_setup.py").read_text()
        self.assertIn("ensure_wallet_profile(user.id, wallet_profile)", helper_source)
        self.assertIn("if wallet_profile.status == \"active\" and has_full_virtual_account:", helper_source)
        self.assertIn("account_creation_failed", helper_source)


if __name__ == "__main__":
    unittest.main()
