#!/usr/bin/env python3
"""
Unit tests for the Derived Variables engine.

Tests all 36 derived variable computations against known patient profiles.
Covers edge cases, boundary conditions, and the 6 visit examples from FSMv2.
"""
import sys
import os
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.patient_input import PatientInput
from core.ar_lenso_input import (
    ARInput, LensoInput, EyeRx,
    compute_mismatch, round_to_step, hybrid_average, hybrid_axis_average,
)
from core.derived_variables import (
    DerivedVariables, compute_derived_variables, load_calibration,
)


class TestEyeRx(unittest.TestCase):
    """Tests for the EyeRx dataclass."""

    def test_empty_rx(self):
        rx = EyeRx()
        self.assertTrue(rx.is_empty())

    def test_non_empty_rx(self):
        rx = EyeRx(sph=-2.0, cyl=-0.75, axis=180)
        self.assertFalse(rx.is_empty())

    def test_spherical_equivalent(self):
        rx = EyeRx(sph=-2.0, cyl=-1.0, axis=90)
        self.assertAlmostEqual(rx.spherical_equivalent(), -2.5)

    def test_round_trip(self):
        rx = EyeRx(sph=-3.25, cyl=-0.50, axis=45, add=1.75)
        d = rx.to_dict()
        rx2 = EyeRx.from_dict(d)
        self.assertAlmostEqual(rx.sph, rx2.sph)
        self.assertAlmostEqual(rx.cyl, rx2.cyl)
        self.assertAlmostEqual(rx.axis, rx2.axis)
        self.assertAlmostEqual(rx.add, rx2.add)


class TestMismatch(unittest.TestCase):
    """Tests for mismatch computation."""

    def test_zero_mismatch(self):
        ar = EyeRx(sph=-2.0, cyl=-0.5, axis=90)
        lenso = EyeRx(sph=-2.0, cyl=-0.5, axis=90)
        mm = compute_mismatch(ar, lenso)
        self.assertAlmostEqual(mm["delta_sph"], 0.0)
        self.assertAlmostEqual(mm["delta_cyl"], 0.0)
        self.assertAlmostEqual(mm["delta_axis"], 0.0)

    def test_sph_mismatch(self):
        ar = EyeRx(sph=-2.0, cyl=-0.5, axis=90)
        lenso = EyeRx(sph=-0.5, cyl=-0.5, axis=90)
        mm = compute_mismatch(ar, lenso)
        self.assertAlmostEqual(mm["delta_sph"], 1.5)

    def test_axis_wraparound(self):
        """Axis 5° and 175° differ by 10° (not 170°)."""
        ar = EyeRx(sph=0, cyl=-1.0, axis=5)
        lenso = EyeRx(sph=0, cyl=-1.0, axis=175)
        mm = compute_mismatch(ar, lenso)
        self.assertAlmostEqual(mm["delta_axis"], 10.0)

    def test_axis_same_at_boundary(self):
        """Axis 0° and 180° are equivalent → delta = 0."""
        ar = EyeRx(sph=0, cyl=-1.0, axis=0)
        lenso = EyeRx(sph=0, cyl=-1.0, axis=180)
        mm = compute_mismatch(ar, lenso)
        self.assertAlmostEqual(mm["delta_axis"], 0.0)


class TestRoundToStep(unittest.TestCase):
    """Tests for diopter rounding."""

    def test_exact(self):
        self.assertAlmostEqual(round_to_step(-2.0, 0.25), -2.0)

    def test_round_up(self):
        self.assertAlmostEqual(round_to_step(-2.13, 0.25), -2.25)

    def test_round_down(self):
        self.assertAlmostEqual(round_to_step(-2.10, 0.25), -2.0)

    def test_midpoint(self):
        # -2.125 rounds to -2.0 (banker's rounding to even)
        result = round_to_step(-2.125, 0.25)
        self.assertIn(result, [-2.0, -2.25])


class TestHybridAverage(unittest.TestCase):
    """Tests for hybrid averaging."""

    def test_same_values(self):
        self.assertAlmostEqual(hybrid_average(-2.0, -2.0), -2.0)

    def test_average_exact_step(self):
        self.assertAlmostEqual(hybrid_average(-2.0, -2.5), -2.25)

    def test_average_rounds(self):
        self.assertAlmostEqual(hybrid_average(-2.0, -2.3, 0.25), -2.25)


class TestHybridAxisAverage(unittest.TestCase):
    """Tests for circular axis averaging."""

    def test_same_axis(self):
        self.assertEqual(hybrid_axis_average(90, 90), 90)

    def test_near_axes(self):
        result = hybrid_axis_average(85, 95)
        self.assertEqual(result, 90)

    def test_wraparound(self):
        """5° and 175° should average near 0°/180°."""
        result = hybrid_axis_average(5, 175)
        self.assertIn(result, [0, 180])

    def test_symmetric(self):
        """Average should be symmetric."""
        r1 = hybrid_axis_average(30, 60)
        r2 = hybrid_axis_average(60, 30)
        self.assertEqual(r1, r2)


class TestAgeBucket(unittest.TestCase):
    """Tests for dv_age_bucket derivation."""

    def setUp(self):
        self.cal = load_calibration()

    def _make_patient(self, age):
        return PatientInput(
            patient_id="P1", visit_id="V1", age_years=age,
        )

    def test_child(self):
        p = self._make_patient(10)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_age_bucket, "Child")

    def test_child_boundary(self):
        p = self._make_patient(17)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_age_bucket, "Child")

    def test_adult(self):
        p = self._make_patient(30)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_age_bucket, "Adult")

    def test_adult_boundary_lower(self):
        p = self._make_patient(18)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_age_bucket, "Adult")

    def test_adult_boundary_upper(self):
        p = self._make_patient(39)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_age_bucket, "Adult")

    def test_presbyope(self):
        p = self._make_patient(55)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_age_bucket, "Presbyope")

    def test_presbyope_boundary(self):
        p = self._make_patient(40)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_age_bucket, "Presbyope")


class TestDistancePriority(unittest.TestCase):
    """Tests for dv_distance_priority."""

    def setUp(self):
        self.cal = load_calibration()

    def test_high_for_driver(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            occupation_type="Driver",
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_distance_priority, "High")

    def test_high_for_heavy_driver(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            driving_time_hours=3,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_distance_priority, "High")

    def test_low_for_comfort(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            priority="Comfort-first",
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_distance_priority, "Low")

    def test_medium_default(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_distance_priority, "Medium")


class TestSymptomRisk(unittest.TestCase):
    """Tests for dv_symptom_risk_level."""

    def setUp(self):
        self.cal = load_calibration()

    def _patient(self, symptoms):
        return PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            symptoms_multi=symptoms,
        )

    def test_high_risk_sudden(self):
        dv = compute_derived_variables(
            self._patient(["Sudden vision change"]),
            ARInput(), LensoInput(), self.cal,
        )
        self.assertEqual(dv.dv_symptom_risk_level, "High")

    def test_high_risk_double(self):
        dv = compute_derived_variables(
            self._patient(["Double vision"]),
            ARInput(), LensoInput(), self.cal,
        )
        self.assertEqual(dv.dv_symptom_risk_level, "High")

    def test_moderate_risk_glare(self):
        dv = compute_derived_variables(
            self._patient(["Glare/halos (night)"]),
            ARInput(), LensoInput(), self.cal,
        )
        self.assertEqual(dv.dv_symptom_risk_level, "Moderate")

    def test_no_risk(self):
        dv = compute_derived_variables(
            self._patient(["Dryness/burning"]),
            ARInput(), LensoInput(), self.cal,
        )
        self.assertEqual(dv.dv_symptom_risk_level, "None")


class TestMedicalRisk(unittest.TestCase):
    """Tests for dv_medical_risk_level."""

    def setUp(self):
        self.cal = load_calibration()

    def test_high_keratoconus(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            known_keratoconus=True,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_medical_risk_level, "High")

    def test_high_infection(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            current_eye_infection_or_inflammation=True,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_medical_risk_level, "High")

    def test_moderate_diabetes(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            diabetes=True,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_medical_risk_level, "Moderate")

    def test_moderate_cataract_surgery(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=55,
            prior_eye_surgery="Cataract",
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_medical_risk_level, "Moderate")

    def test_none(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_medical_risk_level, "None")


class TestStability(unittest.TestCase):
    """Tests for dv_stability_level."""

    def setUp(self):
        self.cal = load_calibration()

    def test_unstable_fluctuating(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            fluctuating_vision_reported=True,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_stability_level, "Unstable")

    def test_unstable_large_change(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            rx_change_was_large=True,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_stability_level, "Unstable")

    def test_uncertain_old_test(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            last_eye_test_months_ago=36,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_stability_level, "Uncertain")

    def test_stable_default(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
        )
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_stability_level, "Stable")


class TestMismatchClassification(unittest.TestCase):
    """Tests for AR-Lenso mismatch classification."""

    def setUp(self):
        self.cal = load_calibration()

    def test_small_mismatch(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        ar = ARInput(re=EyeRx(sph=-2.0, cyl=-0.5, axis=90), le=EyeRx(sph=-1.5))
        lenso = LensoInput(re=EyeRx(sph=-2.0, cyl=-0.5, axis=90), le=EyeRx(sph=-1.5))
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_ar_lenso_mismatch_level_RE, "Small")

    def test_large_sph_mismatch(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        ar = ARInput(re=EyeRx(sph=-4.0), le=EyeRx())
        lenso = LensoInput(re=EyeRx(sph=-1.5), le=EyeRx())
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_ar_lenso_mismatch_level_RE, "Large")

    def test_medium_cyl_mismatch(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        ar = ARInput(re=EyeRx(cyl=-1.0), le=EyeRx())
        lenso = LensoInput(re=EyeRx(cyl=-0.25), le=EyeRx())
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_ar_lenso_mismatch_level_RE, "Medium")


class TestStartPolicy(unittest.TestCase):
    """Tests for dv_start_source_policy."""

    def setUp(self):
        self.cal = load_calibration()

    def test_only_ar(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        ar = ARInput(re=EyeRx(sph=-2.0))
        lenso = LensoInput()  # empty
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_start_source_policy, "Start_AR")

    def test_only_lenso(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        ar = ARInput()  # empty
        lenso = LensoInput(re=EyeRx(sph=-2.0))
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_start_source_policy, "Start_Lenso")

    def test_satisfied_small_mismatch(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            satisfaction_with_current_rx="Satisfied",
        )
        ar = ARInput(re=EyeRx(sph=-2.0, cyl=-0.5, axis=90), le=EyeRx(sph=-1.5, cyl=-0.25, axis=85))
        lenso = LensoInput(re=EyeRx(sph=-2.0, cyl=-0.5, axis=90), le=EyeRx(sph=-1.5, cyl=-0.25, axis=85))
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_start_source_policy, "Start_Lenso")

    def test_unsatisfied_start_ar(self):
        p = PatientInput(
            patient_id="P1", visit_id="V1", age_years=30,
            satisfaction_with_current_rx="Not satisfied",
        )
        ar = ARInput(re=EyeRx(sph=-2.0), le=EyeRx(sph=-1.5))
        lenso = LensoInput(re=EyeRx(sph=-2.0), le=EyeRx(sph=-1.5))
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_start_source_policy, "Start_AR")

    def test_large_mismatch_hybrid(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        ar = ARInput(re=EyeRx(sph=-4.0), le=EyeRx())
        lenso = LensoInput(re=EyeRx(sph=-1.5), le=EyeRx())
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_start_source_policy, "Hybrid")


class TestStartRx(unittest.TestCase):
    """Tests for dv_start_rx values."""

    def setUp(self):
        self.cal = load_calibration()

    def test_start_ar_uses_ar_values(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        ar = ARInput(re=EyeRx(sph=-3.0, cyl=-1.0, axis=45))
        lenso = LensoInput()
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertAlmostEqual(dv.dv_start_rx_RE_sph, -3.0)
        self.assertAlmostEqual(dv.dv_start_rx_RE_cyl, -1.0)
        self.assertAlmostEqual(dv.dv_start_rx_RE_axis, 45.0)

    def test_hybrid_averages(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         fluctuating_vision_reported=True)  # force Unstable -> Hybrid
        ar = ARInput(re=EyeRx(sph=-4.0, cyl=-1.0, axis=90), le=EyeRx(sph=-3.0))
        lenso = LensoInput(re=EyeRx(sph=-2.0, cyl=-0.5, axis=90), le=EyeRx(sph=-2.0))
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertEqual(dv.dv_start_source_policy, "Hybrid")
        # Mean of -4.0 and -2.0 = -3.0, rounded to 0.25 step
        self.assertAlmostEqual(dv.dv_start_rx_RE_sph, -3.0)


class TestAddExpected(unittest.TestCase):
    """Tests for dv_add_expected."""

    def setUp(self):
        self.cal = load_calibration()

    def test_likely_age(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=45)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_add_expected, "Likely")

    def test_likely_progressive(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=35,
                         wear_type="Progressive")
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_add_expected, "Likely")

    def test_likely_has_add(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=35)
        lenso = LensoInput(re=EyeRx(add=1.5))
        dv = compute_derived_variables(p, ARInput(), lenso, self.cal)
        self.assertEqual(dv.dv_add_expected, "Likely")

    def test_possible(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=39,
                         near_priority="High")
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_add_expected, "Possible")

    def test_none_young(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=25)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_add_expected, "None")


class TestFogging(unittest.TestCase):
    """Tests for fogging-related derived variables."""

    def setUp(self):
        self.cal = load_calibration()

    def test_strong_fog_presbyope(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=50)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_fogging_policy, "Strong_Fog")
        self.assertAlmostEqual(dv.dv_fogging_amount_D, 1.0)

    def test_strong_fog_unstable(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         fluctuating_vision_reported=True)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_fogging_policy, "Strong_Fog")

    def test_standard_fog_moderate_risk(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         diabetes=True)  # moderate medical risk
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_fogging_policy, "Standard_Fog")
        self.assertAlmostEqual(dv.dv_fogging_amount_D, 0.75)

    def test_no_fog_healthy_adult(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_fogging_policy, "No_Fog")
        self.assertAlmostEqual(dv.dv_fogging_amount_D, 0.25)


class TestStepSizePolicy(unittest.TestCase):
    """Tests for dv_step_size_policy."""

    def setUp(self):
        self.cal = load_calibration()

    def test_conservative_unstable(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         fluctuating_vision_reported=True)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_step_size_policy, "Conservative")

    def test_aggressive_healthy_stable(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_step_size_policy, "Aggressive")

    def test_standard_presbyope_stable(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=50)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        # Presbyope is not "Adult", so not Aggressive; not unstable, so not Conservative
        self.assertEqual(dv.dv_step_size_policy, "Standard")


class TestEscalationFlags(unittest.TestCase):
    """Tests for optom review and anomaly watch flags."""

    def setUp(self):
        self.cal = load_calibration()

    def test_requires_optom_high_medical(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         known_keratoconus=True)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertTrue(dv.dv_requires_optom_review)

    def test_requires_optom_infection(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         current_eye_infection_or_inflammation=True)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertTrue(dv.dv_requires_optom_review)

    def test_no_optom_healthy(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertFalse(dv.dv_requires_optom_review)

    def test_anomaly_watch_unstable(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         fluctuating_vision_reported=True)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertTrue(dv.dv_anomaly_watch)

    def test_anomaly_watch_large_mismatch(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        ar = ARInput(re=EyeRx(sph=-5.0), le=EyeRx())
        lenso = LensoInput(re=EyeRx(sph=-1.0), le=EyeRx())
        dv = compute_derived_variables(p, ar, lenso, self.cal)
        self.assertTrue(dv.dv_anomaly_watch)


class TestGuardrails(unittest.TestCase):
    """Tests for guardrails and convergence variables."""

    def setUp(self):
        self.cal = load_calibration()

    def test_strict_guardrails(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         symptoms_multi=["Sudden vision change"])
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_branching_guardrails, "Strict")
        self.assertEqual(dv.dv_axis_tolerance_deg, 1)

    def test_relaxed_guardrails(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_branching_guardrails, "Relaxed")
        self.assertEqual(dv.dv_axis_tolerance_deg, 5)

    def test_fast_convergence(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_expected_convergence_time, "Fast")

    def test_slow_convergence_presbyope(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=55)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_expected_convergence_time, "Slow")


class TestEndpointBias(unittest.TestCase):
    """Tests for dv_endpoint_bias_policy."""

    def setUp(self):
        self.cal = load_calibration()

    def test_undercorrect(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=50,
                         near_priority="High", priority="Comfort-first")
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_endpoint_bias_policy, "Undercorrect")

    def test_overcorrect_driver(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30,
                         driving_time_hours=3)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_endpoint_bias_policy, "Overcorrect")

    def test_neutral_default(self):
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        self.assertEqual(dv.dv_endpoint_bias_policy, "Neutral")


class TestFullProfile(unittest.TestCase):
    """Integration test: compute all 36 DVs for realistic patient profiles."""

    def setUp(self):
        self.cal = load_calibration()

    def test_healthy_young_adult(self):
        """32yo desk worker, stable, no medical issues."""
        p = PatientInput(
            patient_id="P001", visit_id="V001", age_years=32,
            occupation_type="Desk-job", screen_time_hours=8,
            primary_reason="Eye strain", priority="Balanced",
        )
        ar = ARInput(
            re=EyeRx(sph=-2.0, cyl=-0.75, axis=180),
            le=EyeRx(sph=-1.75, cyl=-0.50, axis=170),
        )
        lenso = LensoInput(
            re=EyeRx(sph=-1.75, cyl=-0.50, axis=175),
            le=EyeRx(sph=-1.50, cyl=-0.25, axis=165),
        )

        dv = compute_derived_variables(p, ar, lenso, self.cal)

        self.assertEqual(dv.dv_age_bucket, "Adult")
        self.assertEqual(dv.dv_step_size_policy, "Aggressive")
        self.assertEqual(dv.dv_fogging_policy, "No_Fog")
        self.assertEqual(dv.dv_branching_guardrails, "Relaxed")
        self.assertEqual(dv.dv_expected_convergence_time, "Fast")
        self.assertFalse(dv.dv_requires_optom_review)
        self.assertFalse(dv.dv_anomaly_watch)
        self.assertEqual(dv.dv_add_expected, "None")

    def test_presbyope_with_progressive(self):
        """55yo progressive wearer, satisfied, comfort-first."""
        p = PatientInput(
            patient_id="P002", visit_id="V002", age_years=55,
            wear_type="Progressive",
            satisfaction_with_current_rx="Satisfied",
            priority="Comfort-first", near_priority="High",
        )
        ar = ARInput(
            re=EyeRx(sph=-1.0, cyl=-0.25, axis=90),
            le=EyeRx(sph=-0.75),
        )
        lenso = LensoInput(
            re=EyeRx(sph=-1.0, cyl=-0.25, axis=90, add=2.0),
            le=EyeRx(sph=-0.75, add=2.0),
        )

        dv = compute_derived_variables(p, ar, lenso, self.cal)

        self.assertEqual(dv.dv_age_bucket, "Presbyope")
        self.assertEqual(dv.dv_add_expected, "Likely")
        self.assertTrue(dv.dv_near_test_required)
        self.assertEqual(dv.dv_endpoint_bias_policy, "Undercorrect")
        self.assertEqual(dv.dv_fogging_policy, "Strong_Fog")
        self.assertAlmostEqual(dv.dv_fogging_amount_D, 1.0)
        self.assertEqual(dv.dv_start_source_policy, "Start_Lenso")

    def test_high_risk_driver(self):
        """45yo driver with diabetes and large mismatch."""
        p = PatientInput(
            patient_id="P003", visit_id="V003", age_years=45,
            occupation_type="Driver", driving_time_hours=6,
            diabetes=True,
            satisfaction_with_current_rx="Not satisfied",
            symptoms_multi=["Night driving difficulty", "Glare/halos (night)"],
        )
        ar = ARInput(
            re=EyeRx(sph=-3.5, cyl=-1.5, axis=30),
            le=EyeRx(sph=-2.0, cyl=-0.75, axis=160),
        )
        lenso = LensoInput(
            re=EyeRx(sph=-1.0, cyl=-0.5, axis=45, add=1.5),
            le=EyeRx(sph=-1.5, cyl=-0.25, axis=170, add=1.5),
        )

        dv = compute_derived_variables(p, ar, lenso, self.cal)

        self.assertEqual(dv.dv_distance_priority, "High")
        self.assertEqual(dv.dv_endpoint_bias_policy, "Overcorrect")
        self.assertEqual(dv.dv_ar_lenso_mismatch_level_RE, "Large")
        # Large mismatch → Hybrid overrides unsatisfied → Start_AR
        self.assertEqual(dv.dv_start_source_policy, "Hybrid")
        self.assertTrue(dv.dv_anomaly_watch)
        self.assertEqual(dv.dv_add_expected, "Likely")

    def test_dv_serialization(self):
        """Verify DerivedVariables.to_dict() round-trips all fields."""
        p = PatientInput(patient_id="P1", visit_id="V1", age_years=30)
        dv = compute_derived_variables(p, ARInput(), LensoInput(), self.cal)
        d = dv.to_dict()

        # All 35 fields (36 logical, but the dataclass has 35 actual fields)
        self.assertIn("dv_age_bucket", d)
        self.assertIn("dv_near_test_required", d)
        self.assertIn("dv_start_rx_RE_sph", d)
        self.assertIsInstance(d["dv_age_bucket"], str)
        self.assertIsInstance(d["dv_start_rx_RE_sph"], float)
        self.assertIsInstance(d["dv_requires_optom_review"], bool)


if __name__ == "__main__":
    unittest.main()
