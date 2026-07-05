import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PublicClientCutoverTests(unittest.TestCase):
    def test_wallet_transfer_out_uses_nomba_and_tracks_transfer_state(self):
        source = (ROOT / "client/routes/wallet.py").read_text()
        self.assertIn("@router.post(\"/transfer-out\", response_model=WalletTransferOutResponse)", source)
        self.assertIn("verify_transaction_pin(current_user, data.transaction_pin)", source)
        self.assertIn("_validate_transfer_details(data)", source)
        self.assertIn("nomba_service.create_transfer(", source)
        self.assertIn('"transfer_state": transfer_state', source)
        self.assertIn('"balance_applied": is_final_success', source)
        self.assertIn("txn.status = \"pending\"", source)
        self.assertIn("txn.status = \"success\"", source)
        self.assertIn("txn.status = \"failed\"", source)

    def test_bills_and_dashboard_require_estate_membership(self):
        bills_source = (ROOT / "client/routes/bills.py").read_text()
        dashboard_source = (ROOT / "client/routes/dashboard.py").read_text()
        invites_source = (ROOT / "client/routes/invites.py").read_text()
        self.assertIn("require_estate_membership", bills_source)
        self.assertIn("require_estate_membership", dashboard_source)
        self.assertIn("require_estate_membership", invites_source)
        self.assertIn("get_current_unit", bills_source)
        self.assertIn("get_current_unit", invites_source)

    def test_webhooks_reconcile_transfer_out_transactions(self):
        source = (ROOT / "client/routes/webhooks.py").read_text()
        self.assertIn("_apply_transfer_out_webhook", source)
        self.assertIn('Transaction.provider == "nomba_transfer_out"', source)
        self.assertIn('event_type in {"transfer.success", "transaction.success", "transfer.failed", "transaction.failed", "transfer.pending", "transaction.pending"}', source)
        self.assertIn('balance_applied = bool(metadata.get("balance_applied"))', source)
        self.assertIn('metadata["balance_applied"] = True', source)
        self.assertIn("_verify_nomba_webhook_signature", source)
        self.assertIn("nomba-sig-value", source)
        self.assertIn("wallet_credit_applied", source)

    def test_wallet_setup_is_explicit_and_reusable(self):
        wallet_source = (ROOT / "client/routes/wallet.py").read_text()
        helper_source = (ROOT / "client/core/wallet_setup.py").read_text()
        self.assertIn('@router.post("/setup", response_model=WalletSetupResponse)', wallet_source)
        self.assertIn("provision_wallet_virtual_account(", wallet_source)
        self.assertIn("wallet_setup_required", wallet_source)
        self.assertIn("wallet_setup_failed", wallet_source)
        self.assertIn("wallet_virtual_account_payload", wallet_source)
        self.assertIn("ensure_wallet_profile", helper_source)
        self.assertIn("normalize_bvn(", helper_source)

    def test_public_docs_describe_current_client_only_scope(self):
        readme = (ROOT / "README.md").read_text()
        working_context = (ROOT / "docs/WORKING_CONTEXT.md").read_text()
        client_doc = (ROOT / "docs/apps/client-service.md").read_text()
        self.assertIn("Public resident client", readme)
        self.assertIn("direct signup", working_context)
        self.assertIn("Nomba transfer-out", working_context)
        self.assertIn("estate-code onboarding", client_doc)
        self.assertIn("bank transfer-out withdrawals", client_doc)

    def test_service_charge_is_internal_ledger_only(self):
        payment_service = (ROOT / "client/core/services/payment_service.py").read_text()
        bills_source = (ROOT / "client/routes/bills.py").read_text()
        auth_source = (ROOT / "client/routes/auth.py").read_text()
        nomba_source = (ROOT / "client/core/nomba.py").read_text()

        self.assertNotIn("SERVICE_CHARGE_REVENUE_ACCOUNT_ID", payment_service)
        self.assertNotIn("create_book_transfer(", payment_service)
        self.assertIn("user.wallet_balance -= amount", payment_service)
        self.assertIn("You must belong to this unit to pay service charge", bills_source)
        self.assertIn('@router.post("/leave-estate")', auth_source)
        self.assertIn("list_billers", nomba_source)
        self.assertIn("validate_bill_customer", nomba_source)
        self.assertIn("initiate_bill_payment", nomba_source)


if __name__ == "__main__":
    unittest.main()
