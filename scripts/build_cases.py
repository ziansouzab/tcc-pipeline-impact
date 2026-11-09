from copy import deepcopy
import json
from pathlib import Path

import yaml


def create_job(needs=None, upload_artifact=None, download_artifact=None):
    steps = []
    steps.append({"run": "echo etapa experimental"})

    if upload_artifact:
        prepare_artifact_step = {
            "run": "mkdir -p dist && echo exemplo > dist/app.txt",
        }
        upload_step = {
            "uses": "actions/upload-artifact@v4",
            "with": {
                "name": upload_artifact,
                "path": "dist/app.txt",
            },
        }
        steps.append(prepare_artifact_step)
        steps.append(upload_step)

    if download_artifact:
        download_step = {
            "uses": "actions/download-artifact@v4",
            "with": {
                "name": download_artifact,
            },
        }
        steps.append(download_step)

    job_data = {
        "runs-on": "ubuntu-latest",
        "steps": steps,
    }

    if needs is not None:
        job_data["needs"] = needs

    return job_data


def create_workflow(jobs):
    configuration = {
        "name": "Experimento de pipeline",
        "on": ["push", "pull_request"],
        "permissions": {"contents": "read"},
        "jobs": jobs,
    }
    return configuration


def create_case(
    case_id,
    title,
    plan_rule,
    before_workflow,
    after_workflow,
    *,
    change_rules=(),
    after_rules=(),
    absent_rules=(),
    unordered_pairs=None,
):
    expected = {
        "change_rules": list(change_rules),
        "after_rules": list(after_rules),
        "absent_warning_rules": list(absent_rules),
        "unordered_pairs": unordered_pairs,
    }
    case = {
        "id": case_id,
        "title": title,
        "plan_rule": plan_rule,
        "before": before_workflow,
        "after": after_workflow,
        "expected": expected,
    }
    return case


def dependency_added_case():
    jobs = {}
    jobs["build"] = create_job()
    jobs["lint"] = create_job()
    jobs["verify"] = create_job(needs="build")

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["jobs"]["lint"]["needs"] = "build"

    return create_case(
        "01-dependencia-adicionada",
        "Dependência nova afeta ordem, sem provar defeito",
        "R01",
        before_workflow,
        after_workflow,
        change_rules=["R01_DEPENDENCY_CHANGE", "R01_REACHABILITY_CHANGE"],
    )


def dependency_list_reordered_case():
    jobs = {}
    jobs["a"] = create_job()
    jobs["b"] = create_job()
    jobs["c"] = create_job(needs=["a", "b"])

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["name"] = "Outro nome de apresentação"
    after_workflow["jobs"]["c"]["needs"] = ["b", "a"]

    return create_case(
        "02-ordem-da-lista",
        "Reordenar a lista de needs não muda precedência",
        "R01",
        before_workflow,
        after_workflow,
        absent_rules=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"],
    )


def artifact_without_order_case():
    jobs = {}
    jobs["build"] = create_job(upload_artifact="app")
    jobs["verify"] = create_job(needs="build", download_artifact="app")

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    del after_workflow["jobs"]["verify"]["needs"]

    return create_case(
        "03-artefato-sem-ordem",
        "Remoção de needs perde a garantia de ordem do artefato",
        "R02",
        before_workflow,
        after_workflow,
        change_rules=["R01_DEPENDENCY_CHANGE"],
        after_rules=["R02_ARTIFACT_ORDER"],
    )


def transitive_precedence_case():
    jobs = {}
    jobs["build"] = create_job(upload_artifact="app")
    jobs["middle"] = create_job(needs="build")
    jobs["verify"] = create_job(
        needs=["build", "middle"],
        download_artifact="app",
    )

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["jobs"]["verify"]["needs"] = ["middle"]

    return create_case(
        "04-precedencia-transitiva",
        "Remover aresta redundante preserva entrega e ordem transitiva",
        "R02",
        before_workflow,
        after_workflow,
        change_rules=["R01_DEPENDENCY_CHANGE"],
        absent_rules=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"],
    )


def conditional_upload_case():
    jobs = {}
    jobs["build"] = create_job(upload_artifact="app")
    jobs["verify"] = create_job(needs="build", download_artifact="app")

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    upload_step = after_workflow["jobs"]["build"]["steps"][-1]
    upload_step["if"] = "github.ref == 'refs/heads/main'"

    return create_case(
        "05-upload-condicional",
        "Upload só na main, download continua ativo em outros contextos",
        "R03",
        before_workflow,
        after_workflow,
        change_rules=["STEP_CHANGE"],
        after_rules=["R03_ARTIFACT_CONDITION"],
    )


def protected_consumption_case():
    jobs = {}
    jobs["build"] = create_job(upload_artifact="app")
    jobs["verify"] = create_job(needs="build", download_artifact="app")

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    upload_step = after_workflow["jobs"]["build"]["steps"][-1]
    upload_step["if"] = "github.ref == 'refs/heads/main'"
    after_workflow["jobs"]["verify"]["if"] = "github.ref == 'refs/heads/main'"

    return create_case(
        "06-consumo-protegido",
        "Condição compatível impede download quando upload é pulado",
        "R03",
        before_workflow,
        after_workflow,
        change_rules=["R04_CONDITION_CHANGE"],
        absent_rules=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"],
    )


def changed_condition_case():
    jobs = {}
    jobs["build"] = create_job()
    jobs["notify"] = create_job(needs="build")

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["jobs"]["notify"]["if"] = "${{ always() }}"

    return create_case(
        "07-condicao-alterada",
        "Always em notificação é impacto a revisar, não defeito comprovado",
        "R04",
        before_workflow,
        after_workflow,
        change_rules=["R04_CONDITION_CHANGE"],
        absent_rules=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"],
    )


def preserved_failure_policy_case():
    build_job = create_job()
    build_job["continue-on-error"] = False
    jobs = {"build": build_job}

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["name"] = "Apenas nome diferente"

    return create_case(
        "08-politica-preservada",
        "Sem mudança de política de falha",
        "R04",
        before_workflow,
        after_workflow,
        absent_rules=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"],
    )


def parallelism_review_case():
    jobs = {}
    jobs["lint"] = create_job()
    jobs["verify"] = create_job()

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["jobs"]["verify"]["needs"] = "lint"

    return create_case(
        "09-revisar-paralelismo",
        "Serialização sem relação de dados reconhecida: revisão condicional",
        "R05",
        before_workflow,
        after_workflow,
        change_rules=["R01_DEPENDENCY_CHANGE"],
        after_rules=["R05_PARALLEL_REVIEW"],
        unordered_pairs=[],
    )


def required_dependency_case():
    jobs = {}
    jobs["build"] = create_job(upload_artifact="app")
    jobs["verify"] = create_job(needs="build", download_artifact="app")

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["name"] = "Relação de dados preservada"

    return create_case(
        "10-dependencia-necessaria",
        "Transferência de artefato bloqueia sugestão de remover dependência",
        "R05",
        before_workflow,
        after_workflow,
        absent_rules=[
            "R02_ARTIFACT_ORDER",
            "R03_ARTIFACT_CONDITION",
            "R05_PARALLEL_REVIEW",
        ],
        unordered_pairs=[],
    )


def already_unordered_case():
    jobs = {}
    jobs["lint"] = create_job()
    jobs["verify"] = create_job()

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["name"] = "Já sem ordem imposta"

    return create_case(
        "11-ja-sem-ordem",
        "Jobs sem needs já estão livres de ordem estrutural; sem economia estimada",
        "R06",
        before_workflow,
        after_workflow,
        absent_rules=[
            "R02_ARTIFACT_ORDER",
            "R03_ARTIFACT_CONDITION",
            "R05_PARALLEL_REVIEW",
        ],
        unordered_pairs=[["lint", "verify"]],
    )


def preserved_sequence_case():
    jobs = {}
    jobs["build"] = create_job(upload_artifact="app")
    jobs["verify"] = create_job(needs="build", download_artifact="app")

    before_workflow = create_workflow(jobs)
    after_workflow = deepcopy(before_workflow)
    after_workflow["name"] = "Sequência necessária"

    return create_case(
        "12-sequencia-preservada",
        "Ordem necessária não é paralelismo já existente",
        "R06",
        before_workflow,
        after_workflow,
        absent_rules=[
            "R02_ARTIFACT_ORDER",
            "R03_ARTIFACT_CONDITION",
            "R05_PARALLEL_REVIEW",
        ],
        unordered_pairs=[],
    )


def definitions():
    cases = []
    cases.append(dependency_added_case())
    cases.append(dependency_list_reordered_case())
    cases.append(artifact_without_order_case())
    cases.append(transitive_precedence_case())
    cases.append(conditional_upload_case())
    cases.append(protected_consumption_case())
    cases.append(changed_condition_case())
    cases.append(preserved_failure_policy_case())
    cases.append(parallelism_review_case())
    cases.append(required_dependency_case())
    cases.append(already_unordered_case())
    cases.append(preserved_sequence_case())
    return cases


def main():
    cases_directory = Path(__file__).resolve().parents[1] / "cases"
    catalog = []

    for case in definitions():
        case_directory = cases_directory / case["id"]
        case_directory.mkdir(parents=True, exist_ok=True)

        for side in ("before", "after"):
            workflow_path = case_directory / f"{side}.yml"
            workflow_text = yaml.safe_dump(
                case[side],
                allow_unicode=True,
                sort_keys=False,
            )
            workflow_path.write_text(workflow_text, encoding="utf-8")

        case_metadata = {}
        for key, value in case.items():
            if key not in ("before", "after"):
                case_metadata[key] = value

        case_metadata["origin"] = "synthetic"
        case_metadata["split"] = "development"
        case_metadata["github_execution_verified"] = False

        metadata_path = case_directory / "case.json"
        metadata_text = json.dumps(case_metadata, ensure_ascii=False, indent=2)
        metadata_path.write_text(metadata_text + "\n", encoding="utf-8")
        catalog.append(case_metadata)

    catalog_path = cases_directory / "catalog.json"
    catalog_text = json.dumps(catalog, ensure_ascii=False, indent=2)
    catalog_path.write_text(catalog_text + "\n", encoding="utf-8")

    print(f"{len(catalog)} pares de desenvolvimento materializados em {cases_directory}.")


if __name__ == "__main__":
    main()
