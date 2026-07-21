"""Phase C2 / PR1 — source corroboration engine. Pure, deterministic, offline."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.research.corroboration import (corroborate, registrable_key,
                                           tolerance, DEFAULT_TOLERANCE)


def fig(value, url, source_id, unit="SMEs"):
    return {"value": value, "url": url, "source_id": source_id, "unit": unit}


class RegistrableKeyTests(unittest.TestCase):
    def test_subdomains_collapse_to_one_org(self):
        self.assertEqual(registrable_key("https://data.worldbank.org/x"),
                         registrable_key("worldbank.org"))

    def test_gov_entities_stay_distinct(self):
        # two different UAE regulators are NOT one "gov.ae" voice
        self.assertNotEqual(registrable_key("sca.gov.ae"), registrable_key("mohre.gov.ae"))

    def test_www_and_scheme_ignored(self):
        self.assertEqual(registrable_key("https://www.imf.org/report"), "imf.org")


class VerifiedTests(unittest.TestCase):
    def test_two_independent_t1_agree_is_verified(self):
        v = corroborate([fig(557000, "imf.org", "RSRC-1"), fig(560000, "worldbank.org", "RSRC-2")])
        self.assertEqual(v["status"], "verified")
        self.assertEqual(v["reason"], "corroborated")
        self.assertEqual(v["value"], 558500.0)                 # median of the agreeing set
        self.assertCountEqual(v["supporting_source_ids"], ["RSRC-1", "RSRC-2"])
        self.assertEqual(v["independent_t1_t2_count"], 2)

    def test_t1_plus_t2_agree_is_verified(self):
        v = corroborate([fig(500, "imf.org", "RSRC-1"), fig(505, "mckinsey.com", "RSRC-2")])
        self.assertEqual(v["status"], "verified")

    def test_three_agree_one_outlier_still_verified_on_the_cluster(self):
        v = corroborate([fig(100, "imf.org", "R1"), fig(102, "oecd.org", "R2"),
                         fig(101, "worldbank.org", "R3"), fig(900, "bis.org", "R4")])
        self.assertEqual(v["status"], "verified")
        self.assertNotIn("R4", v["supporting_source_ids"])     # the 900 outlier is excluded


class LowConfidenceTests(unittest.TestCase):
    def test_primary_plus_statista_is_not_two_sources(self):
        # Statista is T3 (aggregator) -> only ONE T1/T2 voice -> not verified.
        v = corroborate([fig(557000, "mckinsey.com", "RSRC-1"), fig(557000, "statista.com", "RSRC-2")])
        self.assertEqual(v["status"], "low_confidence")
        self.assertEqual(v["reason"], "single_source")
        self.assertEqual(v["independent_t1_t2_count"], 1)
        self.assertEqual(v["tier_breakdown"]["T3"], 1)

    def test_same_org_twice_is_one_voice(self):
        v = corroborate([fig(557000, "data.worldbank.org", "R1"), fig(560000, "worldbank.org", "R2")])
        self.assertEqual(v["status"], "low_confidence")
        self.assertEqual(v["independent_t1_t2_count"], 1)

    def test_disagreeing_t1_sources(self):
        v = corroborate([fig(300000, "imf.org", "R1"), fig(600000, "oecd.org", "R2")])
        self.assertEqual(v["status"], "low_confidence")
        self.assertEqual(v["reason"], "t1_t2_sources_disagree")

    def test_single_source_keeps_a_flagged_value(self):
        v = corroborate([fig(557000, "imf.org", "R1")])
        self.assertEqual(v["status"], "low_confidence")
        self.assertEqual(v["reason"], "single_source")
        self.assertEqual(v["value"], 557000.0)                 # stored, but flagged

    def test_only_lower_tier_sources(self):
        v = corroborate([fig(557000, "reddit.com", "R1"), fig(560000, "medium.com", "R2")])
        self.assertEqual(v["status"], "low_confidence")
        self.assertEqual(v["reason"], "only_lower_tier_sources")
        self.assertIsNotNone(v["value"])                       # still stored
        self.assertEqual(v["independent_t1_t2_count"], 0)

    def test_unit_mismatch_is_low_confidence(self):
        v = corroborate([fig(557000, "imf.org", "R1", unit="SMEs"),
                         fig(560000, "oecd.org", "R2", unit="USD")])
        self.assertEqual(v["status"], "low_confidence")
        self.assertEqual(v["reason"], "unit_mismatch")

    def test_no_figures(self):
        v = corroborate([])
        self.assertEqual(v["reason"], "no_figures")
        self.assertIsNone(v["value"])

    def test_non_numeric_values_ignored(self):
        v = corroborate([fig("lots", "imf.org", "R1"), fig(True, "oecd.org", "R2")])
        self.assertEqual(v["reason"], "no_figures")


class ToleranceTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("C2_CORROBORATION_TOLERANCE", None)

    def test_default_is_tight(self):
        self.assertEqual(tolerance(), DEFAULT_TOLERANCE)
        self.assertEqual(DEFAULT_TOLERANCE, 0.10)

    def test_env_override(self):
        os.environ["C2_CORROBORATION_TOLERANCE"] = "0.02"
        # 100 vs 108 is within 10% but not within 2% -> no longer corroborated
        v = corroborate([fig(100, "imf.org", "R1"), fig(108, "oecd.org", "R2")], tol=tolerance())
        self.assertEqual(v["status"], "low_confidence")

    def test_bad_env_ignored(self):
        os.environ["C2_CORROBORATION_TOLERANCE"] = "not-a-number"
        self.assertEqual(tolerance(), DEFAULT_TOLERANCE)

    def test_determinism(self):
        args = [fig(557000, "imf.org", "R1"), fig(560000, "worldbank.org", "R2")]
        self.assertEqual(corroborate(args), corroborate(args))


if __name__ == "__main__":
    unittest.main()
