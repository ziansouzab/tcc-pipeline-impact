import unittest

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


if __name__ == "__main__":
    unittest.main()
