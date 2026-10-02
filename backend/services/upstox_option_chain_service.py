"""
Upstox Option Chain Service (Alias Wrapper)
===========================================
Delegates option chain operations directly to backend.services.option_chain_service.
"""

from backend.services.option_chain_service import (
    OptionChainFetchError,
    get_spot_price,
    get_full_chain,
    fetch_option_chain,
    get_available_expiries,
    get_atm_option
)

__all__ = [
    "OptionChainFetchError",
    "get_spot_price",
    "get_full_chain",
    "fetch_option_chain",
    "get_available_expiries",
    "get_atm_option"
]
