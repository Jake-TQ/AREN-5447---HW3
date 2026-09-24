"""Transparent preliminary dwelling-service estimator.

This is an engineering aid, not a permit-ready design.  Its built-in profile
models the U.S. NEC optional dwelling method (Article 220.82) for a single
120/240 V dwelling.  Local amendments, equipment instructions, temperature,
terminal ratings, conductor installation, and the AHJ always control.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Any


# Common dwelling-service choices, assuming 75 C terminations and the
# dwelling-service/feeder permission.  Keep this table configurable: it is
# not a substitute for the adopted edition's ampacity tables and corrections.
## JAKE NOTE: CHANGED 100 RATING TO #2 AWG CU SINCE WE WON'T EVER GO SMALLER THAN A 100A BREAKER SO
## PICK #2 AWG CU TO MATCH
DWELLING_CONDUCTORS = {
    "copper": [(85, "#4 AWG Cu"),(100, "#2 AWG Cu"), (125, "#1 AWG Cu"),
               (150, "1/0 AWG Cu"), (175, "2/0 AWG Cu"), (200, "3/0 AWG Cu"),
               (225, "4/0 AWG Cu"), (250, "250 kcmil Cu"), (300, "350 kcmil Cu"),
               (350, "500 kcmil Cu")],
    "aluminum": [(100, "1/0 AWG Al"), (125, "2/0 AWG Al"),
                 (150, "3/0 AWG Al"), (175, "4/0 AWG Al"), (200, "250 kcmil Al"),
                 (225, "300 kcmil Al"), (250, "350 kcmil Al"), (300, "500 kcmil Al"),
                 (350, "700 kcmil Al")],
}

# Equipment grounding conductor only: commonly used copper table values.
EGC_COPPER = [(15, "#14 AWG Cu"), (20, "#12 AWG Cu"), (60, "#10 AWG Cu"),
              (100, "#8 AWG Cu"), (200, "#6 AWG Cu"), (300, "#4 AWG Cu"),
              (400, "#3 AWG Cu")]
STANDARD_MAIN_BREAKERS = [100, 125, 150, 175, 200, 225, 250, 300, 350, 400]

# Demand factors transcribed from the supplied electrical-dryer table.  The
# source omits a 43-dryer row; the final 25% tier is applied to 43 and above.
DRYER_DEMAND_FACTORS = {
    5: 0.85, 6: 0.75, 7: 0.65, 8: 0.60, 9: 0.55, 10: 0.50,
    11: 0.47, 12: 0.46, 13: 0.45, 14: 0.44, 15: 0.43, 16: 0.42,
    17: 0.41, 18: 0.40, 19: 0.39, 20: 0.38, 21: 0.37, 22: 0.36,
    23: 0.35, 24: 0.345, 25: 0.34, 26: 0.335, 27: 0.33, 28: 0.325,
    29: 0.32, 30: 0.315, 31: 0.31, 32: 0.305, 33: 0.30, 34: 0.295,
    35: 0.29, 36: 0.285, 37: 0.28, 38: 0.275, 39: 0.27, 40: 0.265,
    41: 0.26, 42: 0.255,
}

RANGE_A_FACTORS = {
    1: .80, 2: .75, 3: .70, 4: .66, 5: .62, 6: .59, 7: .56, 8: .53,
    9: .51, 10: .49, 11: .47, 12: .45, 13: .43, 14: .41, 15: .40,
    16: .39, 17: .38, 18: .37, 19: .36, 20: .35, 21: .34, 22: .33,
    23: .32, 24: .31, 25: .30,
}
RANGE_B_FACTORS = {
    1: .80, 2: .65, 3: .55, 4: .50, 5: .45, 6: .43, 7: .40, 8: .36,
    9: .35, 10: .34, 11: .32, 12: .32, 13: .32, 14: .32, 15: .32,
    16: .28, 17: .28, 18: .28, 19: .28, 20: .28, 21: .26, 22: .26,
    23: .26, 24: .26, 25: .26,
}

#

@dataclass
class Result:
    general_load_va: float
    appliance_load_va: float
    appliance_demand_va: float
    appliance_120v_load_va: float
    appliance_120v_demand_va: float
    dryer_count: int
    dryer_connected_va: float
    dryer_demand_factor_percent: float
    dryer_demand_va: float
    range_count: int
    range_connected_va: float
    range_demand_va: float
    range_demand_breakdown: list[dict[str, Any]]
    demanded_general_and_appliance_va: float
    heating_or_cooling_va: float
    calculated_service_va: float
    calculated_service_amps: float
    main_breaker_amps: int
    phase_conductors: str
    neutral_calculated_amps: float
    neutral_conductor: str
    equipment_grounding_conductor: str
    warnings: list[str]

def _first_at_least(table: list[tuple[int, str]], amps: float) -> tuple[int, str]:
    for rating, value in table:
        if rating >= amps:
            return rating, value
    raise ValueError("Calculated size exceeds the built-in 400 A table; engineer a custom profile.")


def dryer_demand_factor(count: int) -> float:
    """Return the table demand factor for a group of electric dryers."""
    if count < 0:
        raise ValueError("Dryer count cannot be negative.")
    if count <= 4:
        return 1.0
    return DRYER_DEMAND_FACTORS.get(count, 0.25)


def _range_percent_factor(count: int, factors: dict[int, float], tail_factor: float) -> float:
    if count <= 25:
        return factors[count]
    if count <= 30:
        return tail_factor
    if count <= 40:
        return tail_factor - .02
    if count <= 50:
        return tail_factor - .04
    if count <= 60:
        return tail_factor - .06
    return tail_factor - .08


def _column_c_base_kw(count: int) -> float:
    values = [0, 8, 11, 14, 17, 20, 21, 22, 23, 24, 25, 26, 27, 28,
              29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40]
    if count <= 25:
        return values[count]
    return (15 if count <= 40 else 25) + count


def calculate_range_demand(range_loads_va: list[float]) -> tuple[float, list[dict[str, Any]]]:
    """Apply the supplied Table 7.2 range/oven demand rules."""
    bands = {"A": [], "B": [], "C": []}
    for load in range_loads_va:
        if load < 0:
            raise ValueError("Range loads cannot be negative.")
        kw = load / 1000
        bands["A" if kw < 3.4 else "B" if kw < 8.75 else "C"].append(kw)

    demand_kw = 0.0
    breakdown: list[dict[str, Any]] = []
    for column, loads_kw in bands.items():
        count = len(loads_kw)
        if not count:
            continue
        connected_kw = sum(loads_kw)
        if column in ("A", "B"):
            factor = _range_percent_factor(count, RANGE_A_FACTORS if column == "A" else RANGE_B_FACTORS,
                                           .30 if column == "A" else .24)
            group_demand_kw = connected_kw * factor
            detail = {"column": column, "count": count, "connected_kw": connected_kw,
                      "demand_factor_percent": factor * 100, "demand_kw": group_demand_kw}
        else:
            base_kw = _column_c_base_kw(count)
            over_12_kw = sum(math.ceil(max(load - 12, 0)) for load in loads_kw)
            group_demand_kw = base_kw * (1 + .05 * over_12_kw)
            detail = {"column": column, "count": count, "connected_kw": connected_kw,
                      "column_c_base_demand_kw": base_kw, "over_12_kw": over_12_kw,
                      "demand_kw": group_demand_kw}
        demand_kw += group_demand_kw
        breakdown.append(detail)
    return demand_kw * 1000, breakdown


def calculate(data: dict[str, Any]) -> Result:
    """Calculate a preliminary service from a JSON-compatible input mapping.

    appliance_loads_va is a list of nameplate VA values for included permanent
    appliances. appliance_loads_120v_va identifies the subset of appliance
    loads that operate at 120 V and are included in the neutral calculation.
    dryer_loads_va is a separate list of dryer nameplate VA values;
    a single dryer is counted at no less than 5,000 VA; groups of dryers use
    their combined nameplate load before the group demand factor is applied.
    range_loads_va is a separate list of range or oven
    nameplate VA values. HVAC values
    must already account for any required continuous-load or motor treatment.
    """
    area = float(data["floor_area_sqft"])
    voltage = float(data.get("voltage", 240))
    if area <= 0 or voltage <= 0:
        raise ValueError("floor_area_sqft and voltage must be positive.")
    if voltage not in (208, 240):
        raise ValueError("Built-in profile supports only 120/208 V or 120/240 V single phase.")
    kitchen = max(2, int(data.get("small_appliance_circuits", 2))) * 1500
    laundry = max(1, int(data.get("laundry_circuits", 1))) * 1500
    general = area * 3 + kitchen + laundry
    demanded_general = 3000 + 0.35*(general-3000) if general > 3000 else general

    appliance_loads = [float(load) for load in data.get("appliance_loads_va", [])]
    appliances = sum(appliance_loads)
    # Apply the requested 75% appliance demand when there are more than four.
    appliance_demand = appliances * 0.75 if len(appliance_loads) > 4 else appliances
    appliance_120v_loads = [float(load) for load in data.get("appliance_loads_120v_va", [])]
    if any(load < 0 for load in appliance_120v_loads):
        raise ValueError("120 V appliance loads cannot be negative.")
    appliance_120v = sum(appliance_120v_loads)
    appliance_120v_demand = (
        appliance_120v * 0.75 if len(appliance_loads) > 4 else appliance_120v
    )

    # Dryer Calcs
    dryer_loads = [float(load) for load in data.get("dryer_loads_va", [])]
    if any(load < 0 for load in dryer_loads):
        raise ValueError("Dryer loads cannot be negative.")
    dryer_connected = sum(dryer_loads)
    if len(dryer_loads) == 1:
        dryer_connected = max(dryer_loads[0], 5_000)
    dryer_factor = dryer_demand_factor(len(dryer_loads))
    dryer_demand = dryer_connected * dryer_factor

    # Range Calcs
    range_loads = [float(load) for load in data.get("range_loads_va", [])]
    range_demand, range_breakdown = calculate_range_demand(range_loads)

    demanded_other = demanded_general + appliance_demand + dryer_demand + range_demand
    #demanded_other = min(other, 10_000) + max(other - 10_000, 0) * 0.40

    heating = float(data.get("heating_va", 0))
    cooling = float(data.get("cooling_va", 0))
    motor_loads = [float(load) for load in data.get("motor_loads_va", [])]
    if heating < 0 or cooling < 0 or appliances < 0:
        raise ValueError("Loads cannot be negative.")
    hvac = max(heating, cooling)
    # Preserve the intended 25% adder for the largest listed motor without
    # failing when no motor loads are supplied.
    motor_derate = 0.25 * max(motor_loads, default=0)

    service_va = demanded_other + hvac + motor_derate
    service_amps = service_va / voltage

    neutral_va = demanded_general + appliance_120v_demand + 0.7 * (dryer_demand + range_demand)
    neutral_amps = neutral_va / voltage

    # This optional method applies only where the calculated load is at least
    # 100 A.  Do not silently use it below that threshold.
    warnings = [
        "Preliminary estimate only—verify adopted code edition, local amendments, utility requirements, and AHJ approval.",
        "Neutral conductor is sized from neutral_amps. Verify the neutral-load calculation against the adopted code and actual maximum unbalanced load.",
        "The ground value is a feeder EGC reference only. A service grounding-electrode conductor needs electrode type and largest ungrounded conductor details.",
        "Verify conductor ampacity for terminal temperature ratings, ambient temperature, bundling, raceway fill, and equipment instructions.",
    ]
    if service_amps < 100:
        warnings.insert(0, "Calculated load is below 100 A; this optional-method profile is not applicable. Use the standard method or a local approved method.")

    main, _ = _first_at_least([(x, str(x)) for x in STANDARD_MAIN_BREAKERS], max(100, service_amps))
    material = data.get("conductor_material", "aluminum").lower()
    if material not in DWELLING_CONDUCTORS:
        raise ValueError("conductor_material must be 'copper' or 'aluminum'.")
    _, phase = _first_at_least(DWELLING_CONDUCTORS[material], main)
    _, neutral = _first_at_least(DWELLING_CONDUCTORS[material], neutral_amps)
    _, egc_size = _first_at_least(EGC_COPPER, main)
    # An EGC normally accompanies a feeder, not the service conductors ahead
    # of the service disconnect. Do not confuse it with the separately sized GEC.
    egc = f"For a feeder only: {egc_size}; service GEC requires electrode details"
    return Result(general, appliances, appliance_demand, appliance_120v, appliance_120v_demand,
                  len(dryer_loads), dryer_connected,
                  dryer_factor * 100, dryer_demand, len(range_loads), sum(range_loads),
                  range_demand, range_breakdown, demanded_other, hvac, service_va, service_amps,
                  main, phase, neutral_amps, neutral, egc, warnings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preliminary NEC-style dwelling service estimator")
    parser.add_argument("input", help="Path to an input JSON file")
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as file:
        data = json.load(file)
    result = calculate(data)
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
