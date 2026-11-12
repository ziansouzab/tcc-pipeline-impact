from pathlib import Path

import yaml

from pipeline_impact.event_context import load_contexts
from pipeline_impact.model import parse


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = {"github.event_name": "push", "github.ref": "refs/heads/main"}
CONTEXT_FIXTURES = load_contexts(ROOT / "cases/contexts.json")


def workflow(jobs):
    configuration = {
        "on": ["push", "pull_request"],
        "jobs": jobs,
    }
    yaml_text = yaml.safe_dump(configuration, sort_keys=False)
    return parse(yaml_text)


def simple(needs=None, **extra):
    data = {
        "runs-on": "ubuntu-latest",
        "steps": [{"run": "echo ok"}],
    }
    for key, value in extra.items():
        data[key] = value

    if needs is not None:
        data["needs"] = needs

    return data


def artifact(upload=True, name="app", **params):
    if upload:
        action_name = "upload"
    else:
        action_name = "download"

    action_parameters = {"name": name}
    for key, value in params.items():
        action_parameters[key] = value

    return {
        "uses": f"actions/{action_name}-artifact@v4",
        "with": action_parameters,
    }


def collect_rules(records):
    rules = set()
    for record in records:
        rules.add(record["rule"])
    return rules


def collect_kinds(findings):
    kinds = set()
    for current_finding in findings:
        kinds.add(current_finding["kind"])
    return kinds
