from copy import deepcopy
import json
from pathlib import Path

import yaml


def job(needs=None, artifact=None, download=None, **extra):
    steps = [{"run": "echo etapa experimental"}]
    if artifact:
        steps.extend([
            {"run": "mkdir -p dist && echo exemplo > dist/app.txt"},
            {"uses": "actions/upload-artifact@v4", "with": {"name": artifact, "path": "dist/app.txt"}},
        ])
    if download:
        steps.append({"uses": "actions/download-artifact@v4", "with": {"name": download}})
    value = {
        "runs-on": "ubuntu-latest",
        "steps": steps,
    }
    for key, parameter_value in extra.items():
        value[key] = parameter_value
    if needs is not None:
        value["needs"] = needs
    return value


def workflow(jobs):
    return {
        "name": "Experimento de pipeline",
        "on": ["push", "pull_request"],
        "permissions": {"contents": "read"},
        "jobs": jobs,
    }


def definitions():
    cases = []

    def add(case_id, title, rule, before, after, *, changes=(), after_rules=(), absent=(), pairs=None):
        expected = {
            "change_rules": list(changes),
            "after_rules": list(after_rules),
            "absent_warning_rules": list(absent),
            "unordered_pairs": pairs,
        }
        case = {
            "id": case_id,
            "title": title,
            "plan_rule": rule,
            "before": before,
            "after": after,
            "expected": expected,
        }
        cases.append(case)

    old = workflow({"build": job(), "lint": job(), "verify": job(needs="build")})
    new = deepcopy(old)
    new["jobs"]["lint"]["needs"] = "build"
    add("01-dependencia-adicionada", "Dependência nova afeta ordem, sem provar defeito", "R01", old, new,
        changes=["R01_DEPENDENCY_CHANGE", "R01_REACHABILITY_CHANGE"])

    old = workflow({"a": job(), "b": job(), "c": job(needs=["a", "b"])})
    new = deepcopy(old)
    new["name"] = "Outro nome de apresentação"
    new["jobs"]["c"]["needs"] = ["b", "a"]
    add("02-ordem-da-lista", "Reordenar a lista de needs não muda precedência", "R01", old, new,
        absent=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"])

    old = workflow({"build": job(artifact="app"), "verify": job(needs="build", download="app")})
    new = deepcopy(old)
    del new["jobs"]["verify"]["needs"]
    add("03-artefato-sem-ordem", "Remoção de needs perde a garantia de ordem do artefato", "R02", old, new,
        changes=["R01_DEPENDENCY_CHANGE"], after_rules=["R02_ARTIFACT_ORDER"])

    old = workflow({"build": job(artifact="app"), "middle": job(needs="build"),
                    "verify": job(needs=["build", "middle"], download="app")})
    new = deepcopy(old)
    new["jobs"]["verify"]["needs"] = ["middle"]
    add("04-precedencia-transitiva", "Remover aresta redundante preserva entrega e ordem transitiva", "R02", old, new,
        changes=["R01_DEPENDENCY_CHANGE"], absent=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"])

    old = workflow({"build": job(artifact="app"), "verify": job(needs="build", download="app")})
    new = deepcopy(old)
    new["jobs"]["build"]["steps"][-1]["if"] = "github.ref == 'refs/heads/main'"
    add("05-upload-condicional", "Upload só na main, download continua ativo em outros contextos", "R03", old, new,
        changes=["STEP_CHANGE"], after_rules=["R03_ARTIFACT_CONDITION"])

    old = workflow({"build": job(artifact="app"), "verify": job(needs="build", download="app")})
    new = deepcopy(old)
    new["jobs"]["build"]["steps"][-1]["if"] = "github.ref == 'refs/heads/main'"
    new["jobs"]["verify"]["if"] = "github.ref == 'refs/heads/main'"
    add("06-consumo-protegido", "Condição compatível impede download quando upload é pulado", "R03", old, new,
        changes=["R04_CONDITION_CHANGE"], absent=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"])

    old = workflow({"build": job(), "notify": job(needs="build")})
    new = deepcopy(old)
    new["jobs"]["notify"]["if"] = "${{ always() }}"
    add("07-condicao-alterada", "Always em notificação é impacto a revisar, não defeito comprovado", "R04", old, new,
        changes=["R04_CONDITION_CHANGE"], absent=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"])

    old = workflow({"build": job(**{"continue-on-error": False})})
    new = deepcopy(old)
    new["name"] = "Apenas nome diferente"
    add("08-politica-preservada", "Sem mudança de política de falha", "R04", old, new,
        absent=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION"])

    old = workflow({"lint": job(), "verify": job()})
    new = deepcopy(old)
    new["jobs"]["verify"]["needs"] = "lint"
    add("09-revisar-paralelismo", "Serialização sem relação de dados reconhecida: revisão condicional", "R05", old, new,
        changes=["R01_DEPENDENCY_CHANGE"], after_rules=["R05_PARALLEL_REVIEW"], pairs=[])

    old = workflow({"build": job(artifact="app"), "verify": job(needs="build", download="app")})
    new = deepcopy(old)
    new["name"] = "Relação de dados preservada"
    add("10-dependencia-necessaria", "Transferência de artefato bloqueia sugestão de remover dependência", "R05", old, new,
        absent=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION", "R05_PARALLEL_REVIEW"], pairs=[])

    old = workflow({"lint": job(), "verify": job()})
    new = deepcopy(old)
    new["name"] = "Já sem ordem imposta"
    add("11-ja-sem-ordem", "Jobs sem needs já estão livres de ordem estrutural; sem economia estimada", "R06", old, new,
        absent=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION", "R05_PARALLEL_REVIEW"], pairs=[["lint", "verify"]])

    old = workflow({"build": job(artifact="app"), "verify": job(needs="build", download="app")})
    new = deepcopy(old)
    new["name"] = "Sequência necessária"
    add("12-sequencia-preservada", "Ordem necessária não é paralelismo já existente", "R06", old, new,
        absent=["R02_ARTIFACT_ORDER", "R03_ARTIFACT_CONDITION", "R05_PARALLEL_REVIEW"], pairs=[])
    return cases


def main():
    root = Path(__file__).resolve().parents[1] / "cases"
    catalog = []
    for case in definitions():
        folder = root / case["id"]
        folder.mkdir(parents=True, exist_ok=True)
        for side in ("before", "after"):
            workflow_path = folder / f"{side}.yml"
            workflow_text = yaml.safe_dump(
                case[side],
                allow_unicode=True,
                sort_keys=False,
            )
            workflow_path.write_text(workflow_text, encoding="utf-8")

        record = {}
        for key, value in case.items():
            if key not in ("before", "after"):
                record[key] = value

        record["origin"] = "synthetic"
        record["split"] = "development"
        record["github_execution_verified"] = False

        metadata_path = folder / "case.json"
        metadata_text = json.dumps(record, ensure_ascii=False, indent=2)
        metadata_path.write_text(metadata_text + "\n", encoding="utf-8")
        catalog.append(record)

    catalog_path = root / "catalog.json"
    catalog_text = json.dumps(catalog, ensure_ascii=False, indent=2)
    catalog_path.write_text(catalog_text + "\n", encoding="utf-8")
    print(f"{len(catalog)} pares de desenvolvimento materializados em {root}.")


if __name__ == "__main__":
    main()
