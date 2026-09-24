import unittest

from dwelling_service import calculate


class DwellingServiceTests(unittest.TestCase):
    def test_optional_method_example(self):
        result = calculate({
            "floor_area_sqft": 2400,
            "appliance_loads_va": [12000, 5500, 4500, 4500, 1200],
            "cooling_va": 7200,
            "conductor_material": "aluminum",
        })
        # Five appliances: 27,700 x 75%=20,775; general demand=6,045; +7,200 HVAC.
        self.assertEqual(result.appliance_demand_va, 20775)
        self.assertEqual(result.calculated_service_va, 34020)
        self.assertAlmostEqual(result.calculated_service_amps, 141.75, places=3)
        self.assertEqual(result.main_breaker_amps, 150)
        self.assertEqual(result.phase_conductors, "3/0 AWG Al")

    def test_minimum_required_circuits(self):
        result = calculate({"floor_area_sqft": 1000, "small_appliance_circuits": 0, "laundry_circuits": 0})
        self.assertEqual(result.general_load_va, 7500)

    def test_four_appliances_do_not_receive_reduction(self):
        result = calculate({"floor_area_sqft": 1000, "appliance_loads_va": [1000] * 4})
        self.assertEqual(result.appliance_demand_va, 4000)

    def test_five_dryers_use_85_percent_of_combined_nameplates(self):
        result = calculate({
            "floor_area_sqft": 1000,
            "dryer_loads_va": [4000, 5000, 6000, 5000, 7000],
        })
        self.assertEqual(result.dryer_count, 5)
        self.assertEqual(result.dryer_connected_va, 27000)
        self.assertEqual(result.dryer_demand_factor_percent, 85)
        self.assertEqual(result.dryer_demand_va, 22950)

    def test_one_dryer_has_a_5000_va_minimum(self):
        result = calculate({"floor_area_sqft": 1000, "dryer_loads_va": [4000]})
        self.assertEqual(result.dryer_connected_va, 5000)

    def test_three_standard_ranges_use_column_c(self):
        result = calculate({"floor_area_sqft": 1000, "range_loads_va": [12000, 12000, 12000]})
        self.assertEqual(result.range_count, 3)
        self.assertEqual(result.range_demand_va, 14000)
        self.assertEqual(result.range_demand_breakdown[0]["column"], "C")

    def test_large_range_adds_five_percent_per_kw_over_twelve(self):
        result = calculate({"floor_area_sqft": 1000, "range_loads_va": [15000]})
        self.assertEqual(result.range_demand_va, 9200)

    def test_neutral_conductor_uses_neutral_amps_not_main_breaker(self):
        result = calculate({
            "floor_area_sqft": 2400,
            "appliance_loads_va": [12000, 5500, 4500, 4500, 1200],
            "appliance_loads_120v_va": [1200],
            "dryer_loads_va": [5000] * 5,
            "range_loads_va": [12000],
            "conductor_material": "aluminum",
        })
        self.assertEqual(result.appliance_120v_demand_va, 1200)
        self.assertAlmostEqual(result.neutral_calculated_amps, 115.5, places=3)
        self.assertEqual(result.phase_conductors, "350 kcmil Al")
        self.assertEqual(result.neutral_conductor, "2/0 AWG Al")


if __name__ == "__main__":
    unittest.main()
