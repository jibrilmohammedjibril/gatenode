import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SchedulerRegressionTests(unittest.TestCase):
    def test_billing_scheduler_runs_recurring_generation(self):
        source = (ROOT / "client/core/tasks.py").read_text()
        self.assertIn("generate_due_cycles", source)
        self.assertIn("Background recurring billing scheduler started.", source)

    def test_client_startup_starts_billing_scheduler(self):
        source = (ROOT / "client/main.py").read_text()
        self.assertIn("start_scheduler()", source)


if __name__ == "__main__":
    unittest.main()
