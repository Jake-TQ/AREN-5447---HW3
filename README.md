# Dwelling service entrance estimator

This is a transparent **preliminary** sizing algorithm for one U.S.-style,
single-phase 120/240 V (or 120/208 V) dwelling unit. It uses the commonly
used optional dwelling calculation structure: 3 VA/ft² general load, required
small-appliance and laundry loads, 100% of the first 10 kVA of the combined
load and 40% of the balance, plus the larger heating or cooling load.

It does not replace a licensed electrical designer or the authority having
jurisdiction (AHJ). It is intentionally conservative about the neutral.

## Run

```powershell
python dwelling_service.py example_dwelling.json
python -m unittest -v
```

## Input model

| Field | Meaning |
|---|---|
| `floor_area_sqft` | Conditioned/eligible dwelling floor area. Required. |
| `voltage` | `240` (default) or `208`. |
| `small_appliance_circuits` | Minimum two is enforced. |
| `laundry_circuits` | Minimum one is enforced. |
| `appliance_loads_va` | Nameplate VA list for the included permanent appliances. |
| `dryer_loads_va` | Separate dryer nameplate-VA list; one dryer is counted at at least 5,000 VA. |
| `range_loads_va` | Separate range/oven nameplate-VA list; Table 7.2 is applied. |
| `heating_va`, `cooling_va` | Properly calculated HVAC loads; only the larger is added. |
| `conductor_material` | `copper` or `aluminum` (default). |

When `appliance_loads_va` has more than four entries, the calculator applies a
75% demand factor to their combined value before applying the dwelling-load
demand calculation. The raw and adjusted appliance totals are both reported.

## Dryer demand factor

Put dryers in `dryer_loads_va`, not `appliance_loads_va`, to prevent double
counting. The calculator reports `dryer_count`, `dryer_connected_va`,
`dryer_demand_factor_percent`, and `dryer_demand_va`. It uses the supplied
table: a single dryer uses the larger of nameplate or 5,000 VA; groups use
their combined nameplate load. The demand factor is 100% for up to four dryers;
85% for five; then the listed factors
through 42 dryers; and 25% for 43 or more. The supplied image has no row for
exactly 43 dryers, so the final 25% tier is used for 43 and above.

## Range demand factor

Put ranges and ovens in `range_loads_va`, not `appliance_loads_va`, to avoid
double counting. The calculator applies the supplied Table 7.2 values: Column
A below 3.5 kW, Column B from 3.5 through less than 8.75 kW, and Column C at
8.75 kW and above. For a Column C range above 12 kW, it adds 5% of the Column
C demand for each kW or major fraction above 12 kW. `range_demand_breakdown`
shows the selected column and calculations for review.

## Outputs and limits

`phase_conductors` sizes both ungrounded conductors. `neutral_conductor` is
sized from the calculated `neutral_calculated_amps` value, rather than the
main-breaker size. Verify this neutral-load calculation against maximum
unbalanced load from the actual 120 V circuit schedule. The
`equipment_grounding_conductor` output gives a **feeder** EGC reference, not a
service conductor. A service's **grounding electrode conductor (GEC)** is a
different design decision that depends on electrode type(s) and conductor
details, so this program refuses to guess it.

The built-in conductor table covers 100–400 A and assumes the dwelling-service
or dwelling-feeder permission, 75 °C terminations, and no derating/correction
conditions. Add a jurisdiction-specific profile before using a different code
edition or installation condition.

Relevant verification points: NEC-style optional dwelling calculation
(Article 220.82), dwelling service/feeder conductor allowance (310.12),
overcurrent protection (240), EGC sizing (250.122), and GEC sizing (250.66).
The optional method is only eligible where its conditions are satisfied;
particularly, this tool emits a warning for calculated loads below 100 A.
