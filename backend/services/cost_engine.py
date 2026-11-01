"""
backend/services/cost_engine.py
================================================================================
Historically Versioned Indian Derivatives Transaction Cost Engine
Strictly implements the SEBI and Ministry of Finance statutory rules across
different historical effective-date regimes (including Budget 2024 revisions).
================================================================================
"""

from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass(frozen=True)
class FrictionBreakdown:
    brokerage: float
    stt: float
    exchange_fee: float
    gst: float
    stamp_duty: float
    sebi_fee: float
    total_friction: float


class IndianDerivativesCostEngine:
    """
    Centralized, historically versioned cost engine for Indian index options.
    
    Historical Effective Date Milestones:
    - Prior to 2024-10-01:
        * STT on Option Sale: 0.0625% on premium turnover.
        * Exchange Turnover Charge: 0.053% (NSE equity derivatives slab).
        * SEBI Turnover Fee: ₹10 per crore (0.0001%).
        * Stamp Duty: 0.003% on buy turnover.
        * GST: 18% on (Brokerage + Exchange Charge + SEBI Fee).
        * Brokerage: ₹20 per executed order.
    - Effective 2024-10-01 (Finance (No. 2) Act, 2024):
        * STT on Option Sale: Increased from 0.0625% to 0.100% (not 0.125%, which applies to futures).
        * Exchange Turnover Charge: Revised NSE flat tariff (0.035% - 0.050%).
        * SEBI Turnover Fee: ₹10 per crore (0.0001%).
        * Stamp Duty: 0.003% on buy turnover.
        * GST: 18% on (Brokerage + Exchange Charge + SEBI Fee).
        * Brokerage: ₹20 per executed order.
    """

    STT_REVISION_DATE = pd.Timestamp("2024-10-01")

    @classmethod
    def calculate_order_friction(
        cls,
        trade_date: str | pd.Timestamp,
        price: float,
        qty: int,
        side: str,  # "BUY" or "SELL"
        is_exercise: bool = False,
        brokerage_per_order: float = 20.0,
    ) -> FrictionBreakdown:
        """
        Computes statutory and regulatory deductions for a single order leg.
        """
        dt = pd.to_datetime(trade_date)
        turnover = price * qty

        if turnover <= 0:
            return FrictionBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        # 1. Brokerage
        brokerage = brokerage_per_order if not is_exercise else 0.0

        # 2. Securities Transaction Tax (STT)
        # STT is payable ONLY on the sell side (or on ITM exercise by buyer).
        stt = 0.0
        if is_exercise:
            # In cash-settled index options, ITM option settlement is taxed at 0.125% of intrinsic settlement value for buyer
            if side == "BUY":
                stt = turnover * 0.00125
        elif side == "SELL":
            if dt >= cls.STT_REVISION_DATE:
                stt = turnover * 0.00100  # 0.10% post Budget 2024
            else:
                stt = turnover * 0.000625  # 0.0625% prior to Oct 1, 2024

        # 3. Exchange Turnover Charge
        if dt >= cls.STT_REVISION_DATE:
            exchange_fee = turnover * 0.00035  # Revised flat tariff (₹350/crore)
        else:
            exchange_fee = turnover * 0.00053  # Legacy slab rate (0.053%)

        # 4. SEBI Turnover Fee (₹10 per crore = 0.0001%)
        sebi_fee = turnover * 0.000001

        # 5. Stamp Duty (payable ONLY on buy side: 0.003% = 0.00003)
        stamp_duty = turnover * 0.00003 if side == "BUY" and not is_exercise else 0.0

        # 6. Goods and Services Tax (GST: 18% on Brokerage + Exchange Fee + SEBI Fee)
        gst = (brokerage + exchange_fee + sebi_fee) * 0.18

        total = brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst

        return FrictionBreakdown(
            brokerage=round(brokerage, 2),
            stt=round(stt, 2),
            exchange_fee=round(exchange_fee, 2),
            gst=round(gst, 2),
            stamp_duty=round(stamp_duty, 2),
            sebi_fee=round(sebi_fee, 2),
            total_friction=round(total, 2),
        )

    @classmethod
    def calculate_round_trip_friction(
        cls,
        entry_date: str | pd.Timestamp,
        exit_date: str | pd.Timestamp,
        entry_price: float,
        exit_price: float,
        side: str,  # "BUY" or "SELL" (initial side)
        qty: int,
        is_expiry_settlement: bool = False,
        brokerage_per_order: float = 20.0,
    ) -> FrictionBreakdown:
        """
        Computes complete round-trip friction for an entered and exited position.
        """
        # Entry Leg
        entry_leg = cls.calculate_order_friction(
            trade_date=entry_date,
            price=entry_price,
            qty=qty,
            side=side,
            is_exercise=False,
            brokerage_per_order=brokerage_per_order,
        )

        # Exit Leg
        exit_side = "BUY" if side == "SELL" else "SELL"
        exit_leg = cls.calculate_order_friction(
            trade_date=exit_date,
            price=exit_price,
            qty=qty,
            side=exit_side,
            is_exercise=is_expiry_settlement,
            brokerage_per_order=brokerage_per_order,
        )

        total_brokerage = round(entry_leg.brokerage + exit_leg.brokerage, 2)
        total_stt = round(entry_leg.stt + exit_leg.stt, 2)
        total_exchange = round(entry_leg.exchange_fee + exit_leg.exchange_fee, 2)
        total_gst = round(entry_leg.gst + exit_leg.gst, 2)
        total_stamp = round(entry_leg.stamp_duty + exit_leg.stamp_duty, 2)
        total_sebi = round(entry_leg.sebi_fee + exit_leg.sebi_fee, 2)
        total_friction = round(
            total_brokerage + total_stt + total_exchange + total_gst + total_stamp + total_sebi, 2
        )

        return FrictionBreakdown(
            brokerage=total_brokerage,
            stt=total_stt,
            exchange_fee=total_exchange,
            gst=total_gst,
            stamp_duty=total_stamp,
            sebi_fee=total_sebi,
            total_friction=total_friction,
        )

