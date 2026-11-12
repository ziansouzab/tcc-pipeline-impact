import json
import unittest

from pipeline_impact.step_comparison import compare_job_steps


class StepComparisonTests(unittest.TestCase):
    def test_compares_condition_and_failure_policy_by_name(self):
        before = [{"name": "Auditoria", "run": "npm audit"}]
        after = [{
            "name": "Auditoria",
            "run": "npm audit",
            "if": "github.event_name == 'pull_request'",
            "continue-on-error": True,
        }]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(1, len(changes))
        change = changes[0]
        self.assertEqual("modified", change["change"])
        self.assertEqual("ci", change["job"])
        self.assertEqual(1, change["before_step"])
        self.assertEqual(1, change["after_step"])
        self.assertEqual("Auditoria", change["after_name"])
        self.assertEqual(
            {"before": False, "after": True},
            change["fields"]["continue-on-error"],
        )
        self.assertEqual(
            {"before": None, "after": "github.event_name == 'pull_request'"},
            change["fields"]["if"],
        )
        self.assertNotIn("npm audit", json.dumps(changes))

    def test_rename_preserves_step_identity(self):
        before = [{"name": "Validar", "run": "npm test"}]
        after = [{"name": "Testes", "run": "npm test"}]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(1, len(changes))
        self.assertEqual("modified", changes[0]["change"])
        self.assertEqual(
            {"name": {"before": "Validar", "after": "Testes"}},
            changes[0]["fields"],
        )

    def test_inserted_step_does_not_change_relative_order(self):
        first = {"name": "Instalar", "run": "npm ci"}
        second = {"name": "Testar", "run": "npm test"}
        inserted = {"name": "Lint", "run": "npm run lint"}

        changes = compare_job_steps("ci", [first, second], [first, inserted, second])

        self.assertEqual(1, len(changes))
        self.assertEqual("added", changes[0]["change"])
        self.assertIsNone(changes[0]["before_step"])
        self.assertEqual(2, changes[0]["after_step"])
        self.assertEqual("Lint", changes[0]["after_name"])

    def test_removed_step_has_original_position(self):
        first = {"name": "Instalar", "run": "npm ci"}
        removed = {"name": "Auditar", "run": "npm audit"}
        last = {"name": "Testar", "run": "npm test"}

        changes = compare_job_steps("ci", [first, removed, last], [first, last])

        self.assertEqual(1, len(changes))
        self.assertEqual("removed", changes[0]["change"])
        self.assertEqual(2, changes[0]["before_step"])
        self.assertIsNone(changes[0]["after_step"])
        self.assertEqual("Auditar", changes[0]["before_name"])

    def test_detects_relative_order_of_matched_steps(self):
        setup = {"id": "setup", "run": "npm ci"}
        audit = {"id": "audit", "run": "npm audit"}
        tests = {"id": "tests", "run": "npm test"}

        changes = compare_job_steps("ci", [setup, audit, tests], [setup, tests, audit])

        observed = []
        for change in changes:
            observed.append((change["change"], change["before_step"], change["after_step"]))
        self.assertEqual([("reordered", 2, 3), ("reordered", 3, 2)], observed)

    def test_concurrent_job_retains_field_changes_without_reorder(self):
        first = {"id": "setup", "run": "npm ci", "background": True}
        second = {"id": "audit", "run": "npm audit"}
        modified = {"id": "audit", "run": "npm audit", "continue-on-error": True}

        changes = compare_job_steps("ci", [first, second], [modified, first], sequential=False)

        self.assertEqual(1, len(changes))
        self.assertEqual("modified", changes[0]["change"])
        self.assertEqual(2, changes[0]["before_step"])
        self.assertEqual(1, changes[0]["after_step"])

    def test_duplicate_ids_are_reported_as_uncertain(self):
        before = [
            {"id": "audit", "name": "Primeira", "run": "npm audit"},
            {"id": "AUDIT", "name": "Segunda", "run": "npm audit --json"},
        ]
        after = [{"id": "audit", "name": "Primeira", "run": "npm audit"}]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(3, len(changes))
        for change in changes:
            self.assertEqual("unmatched", change["change"])
            self.assertNotEqual(change["before_step"] is None, change["after_step"] is None)

    def test_duplicate_names_without_unique_bodies_are_uncertain(self):
        before = [{"name": "Testar", "run": "npm test"}]
        after = [
            {"name": "Testar", "run": "npm test -- a"},
            {"name": "Testar", "run": "npm test -- b"},
        ]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(3, len(changes))
        for change in changes:
            self.assertEqual("unmatched", change["change"])

    def test_distinct_ids_do_not_pair_even_when_commands_match(self):
        before = [{"id": "audit", "name": "Auditoria", "run": "npm audit"}]
        after = [{"id": "audit_prod", "name": "Auditoria", "run": "npm audit"}]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(2, len(changes))
        self.assertEqual("removed", changes[0]["change"])
        self.assertEqual("added", changes[1]["change"])

    def test_unknown_identity_does_not_use_position_to_pair(self):
        before = [{"run": "primeiro comando privado"}]
        after = [{"run": "segundo comando privado"}]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(2, len(changes))
        self.assertEqual("unmatched", changes[0]["change"])
        self.assertEqual("unmatched", changes[1]["change"])
        self.assertNotIn("comando privado", json.dumps(changes))

    def test_unnamed_unique_action_records_parameter_key_without_value(self):
        before = [{"uses": "actions/checkout@v4", "with": {"private": "segredo antigo"}}]
        after = [{"uses": "actions/checkout@v4", "with": {"private": "segredo novo"}}]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(1, len(changes))
        self.assertEqual("modified", changes[0]["change"])
        self.assertEqual({}, changes[0]["fields"])
        self.assertEqual(["with"], changes[0]["other_fields"])
        self.assertNotIn("segredo", json.dumps(changes))

    def test_explicit_false_matches_default_failure_policy(self):
        before = [{"name": "Auditoria", "run": "npm audit"}]
        after = [{"name": "Auditoria", "run": "npm audit", "continue-on-error": False}]

        self.assertEqual([], compare_job_steps("ci", before, after))

    def test_unnamed_unique_action_version_is_reported_as_an_edit(self):
        before = [{"uses": "actions/checkout@v4"}]
        after = [{"uses": "actions/checkout@v5"}]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(1, len(changes))
        self.assertEqual("modified", changes[0]["change"])
        self.assertEqual(
            {"before": "actions/checkout@v4", "after": "actions/checkout@v5"},
            changes[0]["fields"]["uses"],
        )

    def test_unchanged_unique_command_matches_unnamed_step_with_new_condition(self):
        before = [{"run": "echo comando privado"}]
        after = [{"run": "echo comando privado", "if": "github.event_name == 'push'"}]

        changes = compare_job_steps("ci", before, after)

        self.assertEqual(1, len(changes))
        self.assertEqual("modified", changes[0]["change"])
        self.assertEqual(
            {"before": None, "after": "github.event_name == 'push'"},
            changes[0]["fields"]["if"],
        )
        self.assertNotIn("comando privado", json.dumps(changes))
