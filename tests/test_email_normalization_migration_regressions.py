import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class EmailNormalizationMigrationRegressionTests(unittest.TestCase):
    def test_migration_detects_case_collisions_before_lowercasing(self):
        source = (ROOT / "alembic/versions/6f0e2f8a6c41_normalize_email_columns.py").read_text()
        self.assertIn('SELECT id, email FROM users WHERE email IS NOT NULL', source)
        self.assertIn('SELECT id, email FROM two_factor_auth WHERE email IS NOT NULL', source)
        self.assertIn('_raise_on_case_collisions("users", _find_case_collisions(user_rows))', source)
        self.assertIn('_raise_on_case_collisions("two_factor_auth", _find_case_collisions(two_factor_rows))', source)
        self.assertIn('Cannot normalize {table_name} emails because multiple rows collapse', source)

    def test_migration_lowercases_users_otps_and_two_factor_auth(self):
        source = (ROOT / "alembic/versions/6f0e2f8a6c41_normalize_email_columns.py").read_text()
        self.assertIn("UPDATE users", source)
        self.assertIn("UPDATE otp_codes", source)
        self.assertIn("UPDATE two_factor_auth", source)
        self.assertIn("SET email = lower(trim(email))", source)


if __name__ == "__main__":
    unittest.main()
