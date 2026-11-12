import json
from pathlib import Path
import tempfile
import unittest

from pipeline_impact.event_context import event_eligibility, load_contexts
from pipeline_impact.model import InputError
from tests.helpers import ROOT


class EventContextTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)

    def test_load_contexts_accepts_utf8_bom_and_supported_fields(self):
        contexts = [
            {
                "github.event_name": "pull_request",
                "github.ref": "refs/pull/25/merge",
                "github.base_ref": "master",
                "github.head_ref": "feature",
            },
            {
                "github.event_name": "push",
                "github.ref": "refs/heads/master",
                "github.event.before": "abc123",
                "github.base_ref": None,
            },
        ]
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as folder:
            path = Path(folder) / "contexts.json"
            path.write_text(json.dumps(contexts), encoding="utf-8-sig")
            self.assertEqual(contexts, load_contexts(path))

    def test_load_contexts_rejects_invalid_input(self):
        invalid_inputs = (
            (b"\xff", "UTF-8"),
            (b"[", "JSON"),
            (b'{"github.event_name": "push"}', "lista"),
            (b"[1]", "objeto"),
            (b"[{}]", "github.event_name"),
            (b'[{"github.event_name": " "}]', "github.event_name"),
            (b'[{"github.event_name": "push", "github.ref": 1}]', "github.ref"),
            (br'[{"github.event_name": "push", "github.ref": "\ud800"}]', "Unicode"),
            (b'[{"github.event_name": "push", "github.token": "private"}]', "não suportado"),
            (b'[{"github.event_name": "push", "github.event_name": "pull_request"}]', "repetida"),
            (
                b'[{"github.event_name":"push","github.ref":"x"},{"github.ref":"x","github.event_name":"push"}]',
                "duplicado",
            ),
        )
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as folder:
            path = Path(folder) / "contexts.json"
            for content, error_message in invalid_inputs:
                with self.subTest(error=error_message):
                    path.write_bytes(content)
                    with self.assertRaisesRegex(InputError, error_message):
                        load_contexts(path)

    def test_load_contexts_accepts_empty_list(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as folder:
            path = Path(folder) / "contexts.json"
            path.write_text("[]", encoding="utf-8")
            self.assertEqual([], load_contexts(path))

    def test_event_membership_includes_only_declared_events(self):
        push = {"github.event_name": "push"}
        cases = (
            ("push", True),
            (["push", "pull_request"], True),
            ({"push": None, "pull_request": {"types": ["opened"]}}, True),
            ({"push": {}}, True),
            ("pull_request", False),
            (["pull_request"], False),
            ({"pull_request": {"branches": ["master"]}}, False),
        )
        for triggers, expected in cases:
            with self.subTest(triggers=triggers):
                actual, message = event_eligibility(triggers, push)
                self.assertIs(expected, actual)
                self.assertTrue(message)

    def test_push_filters_use_the_branch_in_the_ref(self):
        master = {"github.event_name": "push", "github.ref": "refs/heads/master"}
        feature = {"github.event_name": "push", "github.ref": "refs/heads/topic/x"}
        tag = {"github.event_name": "push", "github.ref": "refs/tags/master"}
        cases = (
            ({"push": {"branches": ["master"]}}, master, True),
            ({"push": {"branches": ["master"]}}, feature, False),
            ({"push": {"branches": ["topic/x"]}}, feature, True),
            ({"push": {"branches-ignore": ["master"]}}, master, False),
            ({"push": {"branches-ignore": ["master"]}}, feature, True),
            ({"push": {"branches": ["master"]}}, tag, False),
            ({"push": {"branches-ignore": ["topic/x"]}}, tag, False),
            ({"push": {"branches": ["master"]}}, {"github.event_name": "push"}, None),
        )
        for triggers, context, expected in cases:
            with self.subTest(triggers=triggers, context=context):
                actual, _ = event_eligibility(triggers, context)
                self.assertIs(expected, actual)

    def test_pull_request_filters_use_the_base_and_require_it(self):
        context = {
            "github.event_name": "pull_request",
            "github.ref": "refs/pull/99/merge",
            "github.base_ref": "master",
            "github.head_ref": "feature",
        }
        allowed, _ = event_eligibility({"pull_request": {"branches": ["master"]}}, context)
        blocked, _ = event_eligibility({"pull_request": {"branches": ["feature"]}}, context)
        self.assertIs(True, allowed)
        self.assertIs(False, blocked)

        del context["github.base_ref"]
        unknown, _ = event_eligibility({"pull_request": {"branches": ["master"]}}, context)
        self.assertIsNone(unknown)

    def test_filters_outside_scope_are_indeterminate(self):
        context = {"github.event_name": "push", "github.ref": "refs/heads/master"}
        cases = (
            {"branches": ["release/**"]},
            {"branches": ["master", "!master"]},
            {"branches": ["master"], "paths": ["docs/**"]},
            {"branches": ["master"], "branches-ignore": ["topic"]},
            {"branches": ["master"], "tags": ["release"]},
            {"branches": "master"},
            {"branches": []},
            {"branches": [True]},
            {"paths-ignore": ["docs/**"]},
            {"tags": ["release"]},
            False,
            [],
        )
        for configuration in cases:
            with self.subTest(configuration=configuration):
                result, message = event_eligibility({"push": configuration}, context)
                self.assertIsNone(result)
                self.assertTrue(message)


if __name__ == "__main__":
    unittest.main()
