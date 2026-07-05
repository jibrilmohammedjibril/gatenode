import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ClientAuthRegressionTests(unittest.TestCase):
    def test_signup_supports_direct_account_creation(self):
        source = (ROOT / "client/routes/auth.py").read_text()
        schema_source = (ROOT / "client/schemas.py").read_text()
        self.assertIn("@router.post(\"/signup\", response_model=ClientTokenResponse)", source)
        self.assertIn("hashed_password=get_password_hash(data.password)", source)
        self.assertIn("estate_id=None", source)
        self.assertIn("class ClientSignup(BaseModel):", schema_source)
        self.assertIn("first_name: str", schema_source)
        self.assertIn("last_name: str", schema_source)
        self.assertIn("phone_number: Optional[str] = None", schema_source)

    def test_join_estate_links_default_unit_and_assigns_estate(self):
        source = (ROOT / "client/routes/auth.py").read_text()
        join_section = source.split('@router.post("/join-estate"', 1)[1].split('@router.post("/login"', 1)[0]
        self.assertIn("select(Unit, Block, Estate)", join_section)
        self.assertIn("Unit.access_code == code", join_section)
        self.assertIn("UserUnit(", join_section)
        self.assertIn("current_user.estate_id = estate.id", join_section)
        self.assertIn('"isPrimary": link.is_primary', join_section)

    def test_login_and_refresh_keep_household_role_state_explicit(self):
        source = (ROOT / "client/routes/auth.py").read_text()
        self.assertIn("if user.role != UserRole.RESIDENT:", source)
        self.assertIn("link.role in [HouseholdRole.ADMIN, HouseholdRole.SUB_ADMIN]", source)
        self.assertIn("_build_token_response(user, token, refresh_token, context)", source)
        self.assertIn('"estate_id": context["estate_id"]', source)
        self.assertIn('"unit_id": context["unit_id"]', source)

    def test_feed_posts_require_estate_membership(self):
        source = (ROOT / "client/routes/feed.py").read_text()
        self.assertIn('x_estate_id: str = Header(..., alias="X-Estate-ID")', source)
        self.assertIn('x_unit_id: str = Header(..., alias="X-Unit-ID")', source)
        self.assertIn("current_user: User = Depends(require_estate_membership)", source)
        self.assertIn('detail="X-Estate-ID does not match the authenticated user\'s estate"', source)
        self.assertIn('detail="Access to this unit denied"', source)

    def test_require_estate_membership_is_a_direct_dependency(self):
        source = (ROOT / "client/core/deps.py").read_text()
        self.assertIn("async def require_estate_membership(", source)
        self.assertIn("user: User = Depends(get_current_user)", source)
        self.assertIn('detail="Join an estate to continue"', source)


if __name__ == "__main__":
    unittest.main()
