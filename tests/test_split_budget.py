"""Durable attempt limits without contacting an image provider."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.split_budget import SplitLayersBudget


class DurableBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "budget.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def test_restart_and_unknown_result_never_refund(self):
        budget = SplitLayersBudget(1, ledger_path=self.path, task_id="task")
        operation = budget.spend(details={"model": "stub", "revision": 2, "layer": "bg"})
        restored = SplitLayersBudget.restore(self.path, "task")
        self.assertEqual(restored.snapshot(), {"limit": 1, "used": 1, "remaining": 0})
        self.assertFalse(restored.spend())
        self.assertEqual(restored.calls()[0]["status"], "unknown")
        restored.finish(operation, "failed")
        self.assertFalse(SplitLayersBudget(64, ledger_path=self.path, task_id="task").spend())
        self.assertIsNone(SplitLayersBudget.restore(self.path, "missing"))

    def test_multiple_clients_reserve_atomically(self):
        SplitLayersBudget(3, ledger_path=self.path, task_id="task")

        def reserve(_):
            return SplitLayersBudget(3, ledger_path=self.path, task_id="task").spend()

        with ThreadPoolExecutor(max_workers=8) as executor:
            reservations = list(executor.map(reserve, range(16)))
        self.assertEqual(sum(bool(item) for item in reservations), 3)
        restored = SplitLayersBudget.restore(self.path, "task")
        self.assertEqual(restored.snapshot()["used"], 3)
        self.assertEqual(len(restored.calls()), 3)

    def test_new_allowance_is_an_absolute_total(self):
        budget = SplitLayersBudget(2, ledger_path=self.path, task_id="task")
        key = budget.spend(details={"layer": "subject"})
        budget.finish(key, "completed")
        budget.mark_accepted([key], False)
        budget.set_limit(2)
        self.assertTrue(budget.spend())
        budget.set_limit(2)
        self.assertFalse(budget.spend())
        budget.set_limit(3)
        self.assertTrue(budget.spend())
        self.assertFalse(budget.spend())
        self.assertEqual(budget.calls()[0]["accepted"], False)


if __name__ == "__main__":
    unittest.main()
