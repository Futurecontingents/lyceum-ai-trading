"""Options-domain types and read-only research helpers belong here.

Order construction and submission are intentionally absent during setup.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OptionCandidate:
    symbol: str
    underlying_symbol: str
    strike_price: Decimal
    expiration_date: str
    option_type: str
