import importlib.util
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_phase2_horizon_validation.py"
spec = importlib.util.spec_from_file_location("phase2_validation", SCRIPT)
phase2 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(phase2)


class Phase3AuditTests(unittest.TestCase):
    def test_identical_loss_arrays_are_not_significant(self):
        losses = np.array([0.01, 0.02, 0.03, 0.04])
        result = phase2.dm_test(losses, losses)
        self.assertEqual(result["mean_loss_difference_a_minus_b"], 0.0)
        self.assertEqual(result["statistic"], 0.0)
        self.assertEqual(result["p_value"], 1.0)
        self.assertTrue(result["identical_loss_series"])

    def test_roundoff_only_loss_arrays_are_not_significant(self):
        left = np.array([0.01, 0.02, 0.03])
        right = left + np.array([1e-16, -1e-16, 1e-16])
        result = phase2.dm_test(left, right)
        self.assertEqual(result["statistic"], 0.0)
        self.assertEqual(result["p_value"], 1.0)


if __name__ == "__main__":
    unittest.main()
