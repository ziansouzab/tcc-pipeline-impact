import unittest

from pipeline_impact.analyzer import compare
from pipeline_impact.model import InputError, parse
from tests.helpers import simple, workflow


class ModelTests(unittest.TestCase):
    def test_on_is_preserved_and_false_remains_boolean(self):
        yaml_text = (
            "on: push\n"
            "jobs:\n"
            "  on:\n"
            "    runs-on: ubuntu-latest\n"
            "    if: false\n"
            "    steps: []\n"
        )
        model = parse(yaml_text)
        self.assertEqual("push", model.raw["on"])
        self.assertEqual("false", model.jobs["on"]["if"])

    def test_duplicate_keys_are_rejected(self):
        yaml_text = "on: push\njobs:\n  a: {steps: []}\n  a: {steps: []}\n"
        with self.assertRaisesRegex(InputError, "duplicada"):
            parse(yaml_text)

    def test_missing_job_is_rejected(self):
        with self.assertRaisesRegex(InputError, "inexistente"):
            workflow({"b": simple("missing")})

    def test_cycle_is_rejected(self):
        with self.assertRaisesRegex(InputError, "Ciclo"):
            workflow({"a": simple("b"), "b": simple("a")})

    def test_case_insensitive_dependencies(self):
        model = workflow({"Build": simple(), "verify": simple("build")})
        self.assertEqual({"Build"}, model.ancestors("verify"))

    def test_duplicate_case_insensitive_ids_are_rejected(self):
        with self.assertRaisesRegex(InputError, "maiúsculas"):
            workflow({"a": simple(), "A": simple()})

    def test_order_of_needs_has_no_semantic_change(self):
        old = workflow({
            "a": simple(),
            "b": simple(),
            "c": simple(["a", "b"]),
        })
        new = workflow({
            "a": simple(),
            "b": simple(),
            "c": simple(["b", "a"]),
        })
        report = compare(old, new)
        self.assertEqual([], report["changes"])

    def test_unsupported_yaml_values_are_rejected(self):
        unsupported_values = [
            "2026-11-09",
            "!!binary aGVsbG8=",
            "!!set {item: null}",
            ".nan",
            ".inf",
        ]

        for yaml_value in unsupported_values:
            with self.subTest(value=yaml_value):
                yaml_text = (
                    "on: push\n"
                    "jobs:\n"
                    "  build:\n"
                    "    env:\n"
                    f"      VALUE: {yaml_value}\n"
                    "    steps: []\n"
                )

                with self.assertRaisesRegex(InputError, "valores YAML não suportados"):
                    parse(yaml_text)

    def test_recursive_yaml_values_are_rejected(self):
        yaml_text = (
            "on: push\n"
            "jobs:\n"
            "  build:\n"
            "    env:\n"
            "      VALUES: &values [*values]\n"
            "    steps: []\n"
        )

        with self.assertRaisesRegex(InputError, "valores YAML não suportados"):
            parse(yaml_text)

    def test_quoted_dates_remain_supported_strings(self):
        yaml_text = (
            "on: push\n"
            "jobs:\n"
            "  build:\n"
            "    env:\n"
            "      RELEASE_DATE: '2026-11-09'\n"
            "    steps: []\n"
        )

        model = parse(yaml_text)

        self.assertEqual("2026-11-09", model.jobs["build"]["env"]["RELEASE_DATE"])


if __name__ == "__main__":
    unittest.main()
