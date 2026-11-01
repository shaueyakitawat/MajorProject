"""
tests/test_cost_engine.py
================================================================================
Unit tests for IndianDerivativesCostEngine:
Validates pre- and post-October 1, 2024 statutory friction calculations.
================================================================================
"""

import unittest
from backend.services.cost_engine import IndianDerivativesCostEngine


class TestIndianDerivativesCostEngine(unittest.TestCase):
    def test_pre_october_2024_sell_friction(self):
        """
        Validates pre-Budget 2024 rates:
        STT = 0.0625%, Exchange = 0.053%, Brokerage = ₹20, Stamp Duty = 0
        """
        res = IndianDerivativesCostEngine.calculate_order_friction(
            trade_date="2024-08-15",
            price=100.0,
            qty=100,
            side="SELL",
        )
        self.assertEqual(res.brokerage, 20.0)
        self.assertEqual(res.stt, 6.25)  # 10,000 * 0.000625
        self.assertEqual(res.exchange_fee, 5.30)  # 10,000 * 0.00053
        self.assertEqual(res.sebi_fee, 0.01)  # 10,000 * 0.000001
        self.assertEqual(res.stamp_duty, 0.0)  # Zero on sell
        expected_gst = round((20.0 + 5.30 + 0.01) * 0.18, 2)
        self.assertEqual(res.gst, expected_gst)

    def test_post_october_2024_sell_friction(self):
        """
        Validates post-Budget 2024 rates:
        STT = 0.100%, Exchange = 0.035%, Brokerage = ₹20
        """
        res = IndianDerivativesCostEngine.calculate_order_friction(
            trade_date="2024-10-15",
            price=100.0,
            qty=100,
            side="SELL",
        )
        self.assertEqual(res.brokerage, 20.0)
        self.assertEqual(res.stt, 10.00)  # 10,000 * 0.00100 (increased STT)
        self.assertEqual(res.exchange_fee, 3.50)  # 10,000 * 0.00035 (revised NSE tariff)
        self.assertEqual(res.stamp_duty, 0.0)

    def test_buy_friction_stamp_duty(self):
        """
        Validates Stamp Duty on Buy orders:
        Stamp Duty = 0.003%, STT = 0
        """
        res = IndianDerivativesCostEngine.calculate_order_friction(
            trade_date="2024-11-01",
            price=100.0,
            qty=100,
            side="BUY",
        )
        self.assertEqual(res.stt, 0.0)  # STT is zero for buyers in India
        self.assertEqual(res.stamp_duty, 0.30)  # 10,000 * 0.00003
        self.assertEqual(res.brokerage, 20.0)

    def test_round_trip_reconciliation(self):
        """
        Validates round-trip calculations for short option entry (SELL) and exit (BUY).
        """
        res = IndianDerivativesCostEngine.calculate_round_trip_friction(
            entry_date="2024-09-15",
            exit_date="2024-10-05",
            entry_price=120.0,
            exit_price=90.0,
            side="SELL",
            qty=195,
        )
        self.assertEqual(res.brokerage, 40.0)
        self.assertEqual(res.stt, 14.62)
        self.assertGreater(res.total_friction, 0)


if __name__ == "__main__":
    unittest.main()
