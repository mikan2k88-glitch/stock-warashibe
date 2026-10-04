from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    sector: str


ROBUSTNESS_UNIVERSE = (
    UniverseMember("9432.T", "telecom"),
    UniverseMember("6740.T", "electronics"),
    UniverseMember("2370.T", "healthcare"),
    UniverseMember("9973.T", "retail"),
    UniverseMember("8107.T", "consumer"),
    UniverseMember("2315.T", "technology"),
    UniverseMember("4564.T", "healthcare"),
    UniverseMember("4597.T", "healthcare"),
    UniverseMember("6993.T", "consumer"),
    UniverseMember("7610.T", "retail"),
    UniverseMember("9424.T", "telecom"),
    UniverseMember("1757.T", "construction"),
    UniverseMember("3777.T", "technology"),
    UniverseMember("8894.T", "real_estate"),
    UniverseMember("5955.T", "materials"),
    UniverseMember("6659.T", "electronics"),
    UniverseMember("8918.T", "real_estate"),
    UniverseMember("5721.T", "materials"),
    UniverseMember("8783.T", "financials"),
    UniverseMember("3840.T", "technology"),
)

UNIVERSE_POLICY = {
    "declared_before_evaluation": True,
    "performance_used_for_selection": False,
    "selection_basis": "predeclared low-price Japan-stock research candidates",
    "point_in_time_constituent_source": False,
    "survivor_bias_eliminated": False,
    "known_bias": (
        "The universe is fixed before this evaluation, but it is not reconstructed "
        "from a historical point-in-time constituent source. Current affordability "
        "screening can retain survivorship/price-path bias."
    ),
}
