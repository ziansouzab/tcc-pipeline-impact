import json
from pathlib import Path

from pipeline_impact.analyzer import compare
from pipeline_impact.model import load
from pipeline_impact.reporting import markdown


def main():
    root = Path(__file__).resolve().parents[1]
    summary = []
    catalog_path = root / "cases/catalog.json"
    catalog_text = catalog_path.read_text(encoding="utf-8")
    catalog = json.loads(catalog_text)

    for case in catalog:
        source = root / "cases" / case["id"]
        before_workflow = load(source / "before.yml")
        after_workflow = load(source / "after.yml")
        report = compare(before_workflow, after_workflow)

        target = root / "reports" / case["id"]
        target.mkdir(parents=True, exist_ok=True)

        json_path = target / "report.json"
        json_text = json.dumps(report, ensure_ascii=False, indent=2)
        json_path.write_text(json_text + "\n", encoding="utf-8")

        markdown_path = target / "report.md"
        markdown_text = markdown(report)
        markdown_path.write_text(markdown_text, encoding="utf-8")

        case_summary = {"id": case["id"]}
        for key, value in report["summary"].items():
            case_summary[key] = value

        case_summary["github_execution_verified"] = False
        summary.append(case_summary)

    summary_path = root / "reports/development-results.json"
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2)
    summary_path.write_text(summary_text + "\n", encoding="utf-8")
    print(f"Relatórios gerados para {len(summary)} casos de desenvolvimento.")


if __name__ == "__main__":
    main()
