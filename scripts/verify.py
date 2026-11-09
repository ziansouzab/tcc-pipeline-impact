from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import yaml


def verification_commands():
    test_command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-v",
    ]
    dependency_command = [
        sys.executable,
        "-m",
        "pip",
        "check",
    ]
    cases_command = [
        sys.executable,
        "scripts/run_cases.py",
    ]
    demonstration_command = [
        sys.executable,
        "-m",
        "pipeline_impact",
        "--before",
        "cases/05-upload-condicional/before.yml",
        "--after",
        "cases/05-upload-condicional/after.yml",
        "--output",
        "reports/demo",
    ]

    commands = []
    commands.append(test_command)
    commands.append(dependency_command)
    commands.append(cases_command)
    commands.append(demonstration_command)
    return commands


def run_checks(project_directory, commands):
    process_environment = os.environ.copy()
    process_environment["PYTHONIOENCODING"] = "utf-8"
    process_environment["PYTHONUTF8"] = "1"
    results = []

    for command in commands:
        process_result = subprocess.run(
            command,
            cwd=project_directory,
            env=process_environment,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

        recorded_command = ["python"]
        for argument in command[1:]:
            recorded_command.append(argument)

        check_result = {
            "command": recorded_command,
            "returncode": process_result.returncode,
            "stdout": process_result.stdout,
            "stderr": process_result.stderr,
        }
        results.append(check_result)

        if process_result.returncode == 0:
            status = "OK"
        else:
            status = "FAIL"

        command_text = " ".join(command[1:])
        print(f"{status}: {command_text}")

    return results


def collect_source_hashes(project_directory):
    source_files = []
    for directory_name in ("src/pipeline_impact", "tests", "scripts"):
        source_directory = project_directory / directory_name
        for source_path in source_directory.rglob("*.py"):
            source_files.append(source_path)

    source_hashes = {}
    for source_path in sorted(source_files):
        relative_path = source_path.relative_to(project_directory)
        relative_name = str(relative_path).replace("\\", "/")
        source_bytes = source_path.read_bytes()
        source_hash = sha256(source_bytes).hexdigest()
        source_hashes[relative_name] = source_hash

    return source_hashes


def checks_passed(results):
    for check_result in results:
        if check_result["returncode"] != 0:
            return False

    return True


def write_verification(project_directory, results, source_hashes):
    recorded_at = datetime.now(timezone.utc).isoformat()
    record = {
        "recorded_at": recorded_at,
        "python": platform.python_version(),
        "pyyaml": yaml.__version__,
        "platform": platform.platform(),
        "checks": results,
        "source_sha256": source_hashes,
        "all_checks_passed": checks_passed(results),
        "github_execution_verified": False,
        "external_comparators_executed": False,
        "research_effectiveness_measured": False,
    }

    verification_path = project_directory / "verification.json"
    verification_text = json.dumps(record, ensure_ascii=False, indent=2)
    verification_path.write_text(verification_text + "\n", encoding="utf-8")


def main():
    project_directory = Path(__file__).resolve().parents[1]
    commands = verification_commands()
    results = run_checks(project_directory, commands)
    source_hashes = collect_source_hashes(project_directory)
    write_verification(project_directory, results, source_hashes)

    if checks_passed(results):
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
