import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class AuditError(Exception):
    pass


def write_github_file(variable, text):
    filename = os.environ.get(variable)
    if filename:
        with Path(filename).open("a", encoding="utf-8") as output_file:
            output_file.write(text + "\n")
    elif variable == "GITHUB_STEP_SUMMARY":
        print(text)


def inline_code(value):
    line = value.replace("\r", "\\r").replace("\n", "\\n")
    delimiter = "`"
    while delimiter in line:
        delimiter += "`"
    return f"{delimiter} {line} {delimiter}"


def git_output(command, arguments):
    result = subprocess.run(
        ["git", command] + arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AuditError(f"Git falhou em {command}, código {result.returncode}.")
    return result.stdout


def require_commit_sha(sha):
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) is None:
        raise AuditError("A revisão deve ser identificada pelo SHA completo.")


def workflow_changes(merge_base, head):
    diff = git_output(
        "diff",
        [
            "--name-status",
            "-z",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            merge_base,
            head,
            "--",
            ".github/workflows/",
        ],
    )
    records = diff.split(b"\0")
    records.pop()
    changes = []
    for index in range(0, len(records), 2):
        status = records[index]
        path = records[index + 1]
        if not path.startswith(b".github/workflows/"):
            continue
        if path.count(b"/") != 2:
            continue
        if not path.endswith((b".yml", b".yaml")):
            continue
        if status not in (b"A", b"M", b"T", b"D"):
            raise AuditError("Git retornou um tipo de mudança de workflow inesperado.")
        change = {"status": status.decode("ascii"), "path": path.decode("utf-8")}
        changes.append(change)
    return changes


def read_workflow_blob(head, path):
    entry = git_output("ls-tree", ["-z", head, "--", f":(literal){path}"])
    if not entry or not entry.endswith(b"\0"):
        raise AuditError(f"O arquivo {path} está ausente na revisão do PR.")
    metadata, entry_path = entry[:-1].split(b"\t", 1)
    mode, kind, blob = metadata.split(b" ")
    if entry_path != path.encode("utf-8"):
        raise AuditError(f"Git retornou um caminho diferente de {path}.")
    if kind != b"blob" or mode not in (b"100644", b"100755"):
        raise AuditError(f"O workflow em {path} deve ser um arquivo regular.")
    return git_output("cat-file", ["blob", blob.decode("ascii")])


def prepare(directory, base, head):
    require_commit_sha(base)
    require_commit_sha(head)
    merge_base = git_output("merge-base", [base, head]).decode("ascii").strip()
    require_commit_sha(merge_base)
    changes = workflow_changes(merge_base, head)
    directory.mkdir(parents=True)
    inputs = directory / "inputs"
    inputs.mkdir()
    has_workflows = False
    summary = [
        "## Preparação da auditoria",
        "",
        f"- Revisão base {inline_code(base)}",
        f"- Ancestral comum {inline_code(merge_base)}",
        f"- Revisão do PR {inline_code(head)}",
        "",
    ]
    for index, change in enumerate(changes, start=1):
        path = change["path"]
        display_path = inline_code(path)
        if change["status"] == "D":
            summary.append(f"- Exclusão registrada para {display_path}.")
            continue
        workflow = read_workflow_blob(head, path)
        input_file = inputs / f"{index:03d}.yml"
        input_file.write_bytes(workflow)
        has_workflows = True
        summary.append(f"- Arquivo selecionado para auditoria {display_path}.")

    plan = {"base": base, "merge_base": merge_base, "head": head, "changes": changes}
    plan_text = json.dumps(plan, ensure_ascii=False, indent=2)
    (directory / "plan.json").write_text(plan_text + "\n", encoding="utf-8")
    if has_workflows:
        write_github_file("GITHUB_OUTPUT", "has_workflows=true")
    else:
        write_github_file("GITHUB_OUTPUT", "has_workflows=false")
        summary.append("")
        summary.append("Auditoria dispensada. Nenhum workflow existente no PR precisa ser analisado.")
    write_github_file("GITHUB_STEP_SUMMARY", "\n".join(summary))
    return 0


def read_github_event():
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    ref = os.environ.get("GITHUB_REF", "")
    base_ref = os.environ.get("GITHUB_BASE_REF", "")
    head_ref = os.environ.get("GITHUB_HEAD_REF", "")

    if not event_name.strip():
        raise AuditError("GITHUB_EVENT_NAME é obrigatório para usar o evento do GitHub.")
    if not ref.strip():
        raise AuditError("GITHUB_REF é obrigatório para usar o evento do GitHub.")
    if event_name in ("pull_request", "pull_request_target") and not base_ref.strip():
        raise AuditError("GITHUB_BASE_REF é obrigatório para usar o evento de pull request.")

    context = {
        "github.event_name": event_name,
        "github.ref": ref,
    }
    if base_ref.strip():
        context["github.base_ref"] = base_ref
    if head_ref.strip():
        context["github.head_ref"] = head_ref
    return context


def run_audit(input_file, output_directory, contexts_path=None):
    command = [
        sys.executable,
        "-m",
        "pipeline_impact",
        "audit",
        str(input_file),
        "--output",
        str(output_directory),
    ]
    if contexts_path is not None:
        command.extend(["--contexts", str(contexts_path)])

    return subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode


def audit(directory):
    plan_text = (directory / "plan.json").read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    contexts_path = None
    context = None
    if os.environ.get("PIPELINE_IMPACT_GITHUB_EVENT") == "true":
        context = read_github_event()
        contexts_path = directory / "contexts.json"
        context_text = json.dumps([context], ensure_ascii=False, indent=2)
        contexts_path.write_text(context_text + "\n", encoding="utf-8")

    reports = directory / "reports"
    reports.mkdir()
    summary = [
        "## Resultado da auditoria",
        "",
        f"Revisão auditada {inline_code(plan['head'])}.",
        "",
    ]
    if context is not None:
        event_name = inline_code(context["github.event_name"])
        ref = inline_code(context["github.ref"])
        summary.append(f"- Evento recebido do GitHub {event_name}, com referência {ref}.")
        if "github.base_ref" in context:
            summary.append(f"- Branch de destino {inline_code(context['github.base_ref'])}.")
        if "github.head_ref" in context:
            summary.append(f"- Branch de origem {inline_code(context['github.head_ref'])}.")
        summary.append("- As condições avaliadas descrevem uma execução hipotética nesse contexto.")
        summary.append("")

    failed = False
    for index, change in enumerate(plan["changes"], start=1):
        if change["status"] == "D":
            continue
        report_id = f"{index:03d}"
        display_path = inline_code(change["path"])
        input_file = directory / "inputs" / f"{report_id}.yml"
        output_directory = directory / "outputs" / report_id
        try:
            exit_code = run_audit(input_file, output_directory, contexts_path)
            if exit_code != 0:
                raise AuditError(f"a CLI retornou {exit_code}")
            json_text = (output_directory / "report.json").read_text(encoding="utf-8")
            report = json.loads(json_text)
            warning_count = report["summary"]["warning"]
            if not (output_directory / "report.md").is_file():
                raise AuditError("o relatório Markdown está ausente")
            output_directory.rename(reports / report_id)
        except (AuditError, KeyError, OSError, ValueError) as error:
            failed = True
            summary.append(f"- Erro de auditoria em {display_path} ({inline_code(str(error))}).")
            continue
        summary.append(
            f"- {display_path} com **{warning_count}** alerta(s). Pasta do artefato {inline_code(report_id)}."
        )
    write_github_file("GITHUB_STEP_SUMMARY", "\n".join(summary))
    if failed:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    preparation = subcommands.add_parser("prepare")
    preparation.add_argument("--base", required=True)
    preparation.add_argument("--head", required=True)
    preparation.add_argument("--directory", type=Path, required=True)
    audit_command = subcommands.add_parser("audit")
    audit_command.add_argument("--directory", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "prepare":
            return prepare(arguments.directory, arguments.base, arguments.head)
        return audit(arguments.directory)
    except (AuditError, OSError, ValueError) as error:
        write_github_file(
            "GITHUB_STEP_SUMMARY",
            f"## Erro de {arguments.command}\n\n{inline_code(str(error))}",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
