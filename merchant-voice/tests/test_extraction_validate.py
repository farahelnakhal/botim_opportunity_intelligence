"""Deterministic observation-validation tests — the core of the Phase 3
safeguards. These test extraction_validate.py directly, with no provider
or database involved at all, so they cannot flake on network/DB state."""

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))

from app import extraction_validate as ev  # noqa: E402

SOURCE = ("Sounds useful, I would try it, but honestly suppliers cancel late payments every week "
         "and it costs us real money. I would pay a fee for guaranteed settlement. "
         "My name is Fatima Noor and I run the shop. Our IBAN is AE070331234567890123456.")


def make_context(**overrides):
    context = {
        "answers_by_id": {"MVA-1": {"question_id": "Q1", "original_answer": SOURCE}},
        "valid_seg_ids": {"SEG-uae-importers"}, "valid_opp_ids": {"OPP-013"},
        "valid_asm_ids": {"ASM-OPP-013-willingness_to_pay"},
        "existing_observation_ids": {"MVO-existing1"},
        "identity_strings": ["MVP-secret-participant", "MID-secret-identity"],
        "quote_permission": True,
    }
    context.update(overrides)
    return context


def base_obs(**overrides):
    obs = {
        "observation_type": "pain", "source_answer_id": "MVA-1",
        "source_excerpt": "suppliers cancel late payments every week",
        "normalized_statement": "Suppliers cancel late payments weekly, costing the merchant money.",
        "is_direct_quote": False, "extraction_confidence": "high",
    }
    obs.update(overrides)
    return obs


class StructuredOutputTests(unittest.TestCase):
    def test_valid_observation_accepted(self):
        r = ev.validate_observation(base_obs(), make_context())
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["observation_type"], "pain")

    def test_missing_source_answer_id_rejected(self):
        obs = base_obs()
        del obs["source_answer_id"]
        r = ev.validate_observation(obs, make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "missing_source_answer_id")

    def test_invalid_source_answer_id_rejected(self):
        r = ev.validate_observation(base_obs(source_answer_id="MVA-does-not-exist"), make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "invalid_source_answer_id")

    def test_cross_response_source_reference_rejected(self):
        # answers_by_id is scoped to ONE response by the caller — a
        # source_answer_id from another response simply won't be in it.
        context = make_context(answers_by_id={"MVA-other-response": {"question_id": "Q9", "original_answer": "x"}})
        r = ev.validate_observation(base_obs(), context)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "invalid_source_answer_id")

    def test_missing_source_excerpt_rejected(self):
        r = ev.validate_observation(base_obs(source_excerpt=""), make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "missing_source_excerpt")

    def test_fabricated_source_excerpt_rejected(self):
        r = ev.validate_observation(base_obs(source_excerpt="this text never appears anywhere"),
                                    make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "unsupported_excerpt")

    def test_unicode_whitespace_normalized_excerpt_accepted(self):
        weird = "suppliers   cancel\nlate  payments\tevery week"
        r = ev.validate_observation(base_obs(source_excerpt=weird), make_context())
        self.assertTrue(r.accepted)

    def test_fuzzy_but_unsupported_excerpt_rejected(self):
        # a near-miss reword must NOT be accepted — no fuzzy matching allowed
        r = ev.validate_observation(
            base_obs(source_excerpt="suppliers delay payments most weeks"), make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "unsupported_excerpt")

    def test_unknown_observation_type_rejected(self):
        r = ev.validate_observation(base_obs(observation_type="not_a_real_type"), make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "invalid_observation_type")

    def test_unknown_confidence_rejected(self):
        r = ev.validate_observation(base_obs(extraction_confidence="extremely_sure"), make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "invalid_confidence")

    def test_identity_data_detected_rejected(self):
        r = ev.validate_observation(
            base_obs(normalized_statement="MVP-secret-participant said suppliers cancel late payments"),
            make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "identity_data_detected")


class QuoteVsParaphraseTests(unittest.TestCase):
    def test_direct_quote_accepted_when_identical(self):
        excerpt = "suppliers cancel late payments every week"
        r = ev.validate_observation(
            base_obs(source_excerpt=excerpt, normalized_statement=excerpt, is_direct_quote=True),
            make_context())
        self.assertTrue(r.accepted)
        self.assertTrue(r.observation["is_direct_quote"])
        self.assertNotIn("quote_downgraded", r.observation["sensitivity_flags"])

    def test_paraphrase_forced_to_non_quote(self):
        r = ev.validate_observation(
            base_obs(source_excerpt="suppliers cancel late payments every week",
                    normalized_statement="The merchant reports weekly payment cancellations.",
                    is_direct_quote=True),
            make_context())
        self.assertTrue(r.accepted)
        self.assertFalse(r.observation["is_direct_quote"])

    def test_quote_downgrade_flag_added(self):
        r = ev.validate_observation(
            base_obs(source_excerpt="suppliers cancel late payments every week",
                    normalized_statement="Weekly payment cancellations reported.", is_direct_quote=True),
            make_context())
        self.assertIn("quote_downgraded", r.observation["sensitivity_flags"])

    def test_quote_denied_without_quote_permission(self):
        excerpt = "suppliers cancel late payments every week"
        r = ev.validate_observation(
            base_obs(source_excerpt=excerpt, normalized_statement=excerpt, is_direct_quote=True),
            make_context(quote_permission=False))
        self.assertTrue(r.accepted)
        self.assertFalse(r.observation["is_direct_quote"])


class WillingnessToPayTests(unittest.TestCase):
    def test_generic_interest_downgraded_from_wtp(self):
        r = ev.validate_observation(
            base_obs(observation_type="willingness_to_pay_signal",
                    source_excerpt="Sounds useful, I would try it",
                    normalized_statement="Merchant likes the idea."),
            make_context())
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["observation_type"], "concept_reaction")
        self.assertIn("wtp_downgraded_generic_interest", r.observation["sensitivity_flags"])

    def test_explicit_price_acceptance_retained_as_wtp(self):
        r = ev.validate_observation(
            base_obs(observation_type="willingness_to_pay_signal",
                    source_excerpt="I would pay a fee for guaranteed settlement",
                    normalized_statement="Merchant would pay a fee for guaranteed settlement."),
            make_context())
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["observation_type"], "willingness_to_pay_signal")

    def test_prior_paid_workaround_retained_as_wtp(self):
        context = make_context(answers_by_id={"MVA-1": {"question_id": "Q1",
                                                         "original_answer": "We already pay for a manual reconciliation service today."}})
        r = ev.validate_observation(
            base_obs(observation_type="willingness_to_pay_signal",
                    source_excerpt="We already pay for a manual reconciliation service",
                    normalized_statement="Merchant already pays for manual reconciliation."),
            context)
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["observation_type"], "willingness_to_pay_signal")


class FrequencySeverityTests(unittest.TestCase):
    def test_unsupported_frequency_cleared_on_other_type(self):
        r = ev.validate_observation(base_obs(frequency="daily"), make_context())
        self.assertTrue(r.accepted)
        self.assertIsNone(r.observation["frequency"])
        self.assertIn("unsupported_frequency", r.observation["sensitivity_flags"])

    def test_supported_frequency_retained(self):
        r = ev.validate_observation(base_obs(frequency="weekly"), make_context())
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["frequency"], "weekly")

    def test_unsupported_frequency_observation_rejected(self):
        r = ev.validate_observation(
            base_obs(observation_type="frequency", frequency="daily"), make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "unsupported_frequency_observation")

    def test_unsupported_severity_cleared_on_other_type(self):
        r = ev.validate_observation(base_obs(severity="high"), make_context())
        self.assertTrue(r.accepted)
        self.assertIsNone(r.observation["severity"])
        self.assertIn("unsupported_severity", r.observation["sensitivity_flags"])

    def test_supported_severity_retained(self):
        context = make_context(answers_by_id={"MVA-1": {"question_id": "Q1",
                                                         "original_answer": "We suffered a significant loss because of this delay."}})
        r = ev.validate_observation(
            base_obs(source_excerpt="significant loss because of this delay",
                    normalized_statement="Merchant suffered a significant financial loss.",
                    severity="high"), context)
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["severity"], "high")

    def test_unsupported_severity_observation_rejected(self):
        r = ev.validate_observation(
            base_obs(observation_type="severity", severity="high"), make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "unsupported_severity_observation")


class AggregateClaimTests(unittest.TestCase):
    def test_aggregate_claim_from_one_response_rejected(self):
        r = ev.validate_observation(
            base_obs(normalized_statement="Most merchants experience this every week"), make_context())
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "single_response_aggregate_claim")

    def test_singular_statement_not_rejected(self):
        r = ev.validate_observation(base_obs(), make_context())
        self.assertTrue(r.accepted)


class LinkValidationTests(unittest.TestCase):
    def test_invalid_segment_link_removed(self):
        r = ev.validate_observation(
            base_obs(linked_segments=["SEG-uae-importers", "SEG-bogus"]), make_context())
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["linked_segments"], ["SEG-uae-importers"])
        self.assertIn("invalid_link_removed", r.observation["sensitivity_flags"])

    def test_invalid_opportunity_link_removed(self):
        r = ev.validate_observation(
            base_obs(linked_opportunities=["OPP-013", "OPP-999"]), make_context())
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["linked_opportunities"], ["OPP-013"])
        self.assertIn("invalid_link_removed", r.observation["sensitivity_flags"])

    def test_invalid_assumption_link_removed(self):
        r = ev.validate_observation(
            base_obs(linked_assumptions=["ASM-OPP-013-willingness_to_pay", "ASM-OPP-999-bogus"]),
            make_context())
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["linked_assumptions"], ["ASM-OPP-013-willingness_to_pay"])
        self.assertIn("invalid_link_removed", r.observation["sensitivity_flags"])

    def test_no_invented_replacement_links(self):
        r = ev.validate_observation(base_obs(linked_segments=["SEG-totally-invented"]), make_context())
        self.assertEqual(r.observation["linked_segments"], [])

    def test_contradiction_target_removed_when_unknown(self):
        r = ev.validate_observation(base_obs(contradiction_target="MVO-unknown"), make_context())
        self.assertTrue(r.accepted)
        self.assertIsNone(r.observation["contradiction_target"])
        self.assertIn("contradiction_target_removed", r.observation["sensitivity_flags"])

    def test_contradiction_preserved_when_valid(self):
        r = ev.validate_observation(base_obs(contradiction_target="MVO-existing1"), make_context())
        self.assertTrue(r.accepted)
        self.assertEqual(r.observation["contradiction_target"], "MVO-existing1")
        self.assertNotIn("contradiction_target_removed", r.observation["sensitivity_flags"])


class BatchValidationTests(unittest.TestCase):
    def test_validate_observations_partitions_accepted_and_rejected(self):
        raw = [base_obs(), base_obs(observation_type="not_real")]
        accepted, rejected = ev.validate_observations(raw, make_context())
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reason"], "invalid_observation_type")

    def test_non_list_raw_output_rejected_wholesale(self):
        accepted, rejected = ev.validate_observations({"not": "a list"}, make_context())
        self.assertEqual(accepted, [])
        self.assertEqual(rejected, [{"reason": "invalid_provider_output"}])

    def test_non_dict_item_rejected(self):
        accepted, rejected = ev.validate_observations(["not a dict"], make_context())
        self.assertEqual(accepted, [])
        self.assertEqual(rejected[0]["reason"], "invalid_provider_output")


if __name__ == "__main__":
    unittest.main(verbosity=2)
