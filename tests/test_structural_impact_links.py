import unittest

from pipeline_impact.analyzer import audit, compare
from pipeline_impact.model import load
from pipeline_impact.reporting import markdown
from tests.helpers import ROOT, artifact, simple, workflow
from tests.test_coverage import findings_for


ARTIFACT_ORDER_RULE = "R02_ARTIFACT_ORDER"
DIRECT_NEEDS_RULE = "R06_NEEDS_DIRECT_DEPENDENCY"
DEPENDENCY_CHANGE_RULE = "R01_DEPENDENCY_CHANGE"


class StructuralImpactLinkTests(unittest.TestCase):
    def assert_impact_reference(self, report, impact, impact_type, finding):
        self.assertEqual(impact_type, impact["type"])
        self.assertEqual(finding["id"], impact["finding_id"])
        self.assertEqual(finding["location"], impact["location"])
        self.assertGreaterEqual(impact["change_index"], 0)
        self.assertLess(impact["change_index"], len(report["changes"]))
        self.assertIsInstance(impact["evidence"], dict)
        self.assertTrue(impact["evidence"])
        dependency_change = report["changes"][impact["change_index"]]
        self.assertEqual(DEPENDENCY_CHANGE_RULE, dependency_change["rule"])
        return dependency_change

    def test_links_removed_dependency_to_artifact_order_warning(self):
        case_directory = ROOT / "cases/03-artefato-sem-ordem"
        before = load(case_directory / "before.yml")
        after = load(case_directory / "after.yml")

        report = compare(before, after)

        self.assertEqual([], findings_for(report["before"], ARTIFACT_ORDER_RULE))
        findings = findings_for(report["after"], ARTIFACT_ORDER_RULE)
        self.assertEqual(1, len(findings))
        self.assertEqual(1, len(report["impact_links"]))
        impact = report["impact_links"][0]
        change = self.assert_impact_reference(report, impact, "artifact_order_lost", findings[0])
        self.assertEqual("verify", change["job"])
        self.assertEqual(["build"], change["before"])
        self.assertEqual([], change["after"])
        self.assertEqual({"job": "verify", "step": 2}, impact["location"])
        evidence = impact["evidence"]
        self.assertEqual("app", evidence["artifact"])
        self.assertEqual(["build", "verify"], evidence["removed_edge"])
        self.assertIs(evidence["precedence_before"], True)
        self.assertIs(evidence["precedence_after"], False)
        self.assertIs(evidence["precedence_with_restored_edge"], True)
        rendered = markdown(report)
        self.assertIn("## Impactos explicados", rendered)
        self.assertIn(ARTIFACT_ORDER_RULE, rendered)

    def test_does_not_link_removal_when_transitive_order_still_protects_artifact(self):
        case_directory = ROOT / "cases/04-precedencia-transitiva"
        before = load(case_directory / "before.yml")
        after = load(case_directory / "after.yml")

        report = compare(before, after)

        self.assertEqual([], findings_for(report["after"], ARTIFACT_ORDER_RULE))
        self.assertEqual([], report["impact_links"])

    def test_does_not_link_preexisting_warning_to_unrelated_dependency_removal(self):
        before = workflow({
            "build": simple(steps=[artifact()]),
            "lint": simple(),
            "verify": simple("lint", steps=[artifact(False)]),
        })
        after = workflow({
            "build": simple(steps=[artifact()]),
            "lint": simple(),
            "verify": simple(steps=[artifact(False)]),
        })

        report = compare(before, after)

        self.assertEqual(1, len(findings_for(report["before"], ARTIFACT_ORDER_RULE)))
        self.assertEqual(1, len(findings_for(report["after"], ARTIFACT_ORDER_RULE)))
        self.assertEqual([], report["impact_links"])

    def test_does_not_link_when_restoring_one_edge_cannot_recover_precedence(self):
        before = workflow({
            "build": simple(steps=[artifact()]),
            "bridge": simple("build"),
            "verify": simple("bridge", steps=[artifact(False)]),
        })
        after = workflow({
            "build": simple(steps=[artifact()]),
            "bridge": simple(),
            "verify": simple(steps=[artifact(False)]),
        })

        report = compare(before, after)

        self.assertEqual([], findings_for(report["before"], ARTIFACT_ORDER_RULE))
        self.assertEqual(1, len(findings_for(report["after"], ARTIFACT_ORDER_RULE)))
        self.assertEqual([], report["impact_links"])

    def test_does_not_link_restoration_when_the_removed_edge_would_create_a_cycle(self):
        before = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple("build", steps=[artifact(False)]),
        })
        after = workflow({
            "build": simple("verify", steps=[artifact()]),
            "verify": simple(steps=[artifact(False)]),
        })

        report = compare(before, after)

        self.assertEqual(1, len(findings_for(report["after"], ARTIFACT_ORDER_RULE)))
        self.assertEqual([], report["impact_links"])

    def test_links_removed_transitive_edge_when_it_alone_restores_artifact_order(self):
        before = workflow({
            "build": simple(steps=[artifact()]),
            "bridge": simple("build"),
            "verify": simple("bridge", steps=[artifact(False)]),
        })
        after = workflow({
            "build": simple(steps=[artifact()]),
            "bridge": simple(),
            "verify": simple("bridge", steps=[artifact(False)]),
        })

        report = compare(before, after)

        findings = findings_for(report["after"], ARTIFACT_ORDER_RULE)
        self.assertEqual(1, len(findings))
        self.assertEqual(1, len(report["impact_links"]))
        impact = report["impact_links"][0]
        change = self.assert_impact_reference(report, impact, "artifact_order_lost", findings[0])
        self.assertEqual("bridge", change["job"])
        self.assertEqual(["build"], change["before"])
        self.assertEqual("verify", impact["location"]["job"])

    def test_links_lost_output_access_when_a_transitive_path_still_exists(self):
        consumer_step = {"id": "check", "run": "echo ${{ needs.build.outputs.version }}"}
        before = workflow({
            "build": simple(outputs={"version": "1"}),
            "bridge": simple("build"),
            "verify": simple(["build", "bridge"], steps=[consumer_step]),
        })
        after = workflow({
            "build": simple(outputs={"version": "1"}),
            "bridge": simple("build"),
            "verify": simple("bridge", steps=[consumer_step]),
        })

        report = compare(before, after)

        self.assertEqual({"build", "bridge"}, after.ancestors("verify"))
        self.assertEqual([], findings_for(report["before"], DIRECT_NEEDS_RULE))
        findings = findings_for(report["after"], DIRECT_NEEDS_RULE)
        self.assertEqual(1, len(findings))
        self.assertEqual(1, len(report["impact_links"]))
        impact = report["impact_links"][0]
        change = self.assert_impact_reference(report, impact, "direct_needs_lost", findings[0])
        self.assertEqual(["bridge", "build"], change["before"])
        self.assertEqual(["bridge"], change["after"])
        self.assertEqual({"job": "verify", "step": 1, "field": "run"}, impact["location"])
        self.assertEqual(["build", "verify"], impact["evidence"]["removed_edge"])
        self.assertEqual("needs.build.outputs.version", impact["evidence"]["reference"])
        self.assertIs(impact["evidence"]["order_preserved"], True)

    def test_links_removed_job_dependency_to_same_literal_result_reference(self):
        condition = "always() && needs.build.result == 'success'"
        before_consumer = simple("build")
        before_consumer["if"] = condition
        after_consumer = simple()
        after_consumer["if"] = condition
        before = workflow({
            "build": simple(),
            "verify": before_consumer,
        })
        after = workflow({
            "build": simple(),
            "verify": after_consumer,
        })

        report = compare(before, after)

        findings = findings_for(report["after"], DIRECT_NEEDS_RULE)
        self.assertEqual(1, len(findings))
        self.assertEqual(1, len(report["impact_links"]))
        impact = report["impact_links"][0]
        change = self.assert_impact_reference(report, impact, "direct_needs_lost", findings[0])
        self.assertEqual("verify", change["job"])
        self.assertEqual({"job": "verify", "field": "if"}, impact["location"])

    def test_does_not_link_simultaneously_added_needs_reference_to_removed_dependency(self):
        before = workflow({
            "build": simple(outputs={"version": "1"}),
            "verify": simple("build", steps=[{"id": "check", "run": "echo stable"}]),
        })
        after = workflow({
            "build": simple(outputs={"version": "1"}),
            "verify": simple(steps=[{"id": "check", "run": "echo ${{ needs.build.outputs.version }}"}]),
        })

        report = compare(before, after)

        self.assertEqual(1, len(findings_for(report["after"], DIRECT_NEEDS_RULE)))
        self.assertEqual([], report["impact_links"])

    def test_does_not_link_removed_dependency_when_the_producer_was_also_removed(self):
        consumer_step = {"run": "echo ${{ needs.build.outputs.version }}"}
        before = workflow({
            "build": simple(outputs={"version": "1"}),
            "verify": simple("build", steps=[consumer_step]),
        })
        after = workflow({
            "verify": simple(steps=[consumer_step]),
        })

        report = compare(before, after)

        findings = findings_for(report["after"], DIRECT_NEEDS_RULE)
        self.assertEqual(1, len(findings))
        self.assertEqual("build", findings[0]["evidence"]["producer_job"])
        self.assertEqual([], report["impact_links"])

    def test_individual_audit_keeps_its_contract(self):
        after = load(ROOT / "cases/03-artefato-sem-ordem/after.yml")

        report = audit(after)

        self.assertNotIn("impact_links", report)
        self.assertEqual(1, len(findings_for(report["analysis"], ARTIFACT_ORDER_RULE)))


if __name__ == "__main__":
    unittest.main()
