import json
from pathlib import Path

from pipeline_impact.analyzer import compare
from pipeline_impact.model import load
from pipeline_impact.reporting import markdown


def load_catalog(project_directory):
    catalog_path = project_directory / "cases" / "catalog.json"
    catalog_text = catalog_path.read_text(encoding="utf-8")
    catalog = json.loads(catalog_text)
    return catalog


def analyze_case(project_directory, case_id):
    case_directory = project_directory / "cases" / case_id
    before_workflow = load(case_directory / "before.yml")
    after_workflow = load(case_directory / "after.yml")
    report = compare(before_workflow, after_workflow)
    return report


def write_case_reports(project_directory, case_id, report):
    report_directory = project_directory / "reports" / case_id
    report_directory.mkdir(parents=True, exist_ok=True)

    json_path = report_directory / "report.json"
    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    json_path.write_text(json_text + "\n", encoding="utf-8")

    markdown_path = report_directory / "report.md"
    markdown_text = markdown(report)
    markdown_path.write_text(markdown_text, encoding="utf-8")


def main():
    project_directory = Path(__file__).resolve().parents[1]
    catalog = load_catalog(project_directory)
    summaries = []

    for case in catalog:
        case_id = case["id"]
        report = analyze_case(project_directory, case_id)
        write_case_reports(project_directory, case_id, report)

        case_summary = {"id": case_id}
        for key, value in report["summary"].items():
            case_summary[key] = value

        case_summary["github_execution_verified"] = False
        summaries.append(case_summary)

    summary_path = project_directory / "reports" / "development-results.json"
    summary_text = json.dumps(summaries, ensure_ascii=False, indent=2)
    summary_path.write_text(summary_text + "\n", encoding="utf-8")

    print(f"Relatórios gerados para {len(summaries)} casos de desenvolvimento.")


if __name__ == "__main__":
    main()
