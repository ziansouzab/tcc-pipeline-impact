from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys

import yaml


def main():
    root = Path(__file__).resolve().parents[1]
    checks = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-m", "pip", "check"],
        [sys.executable, "scripts/run_cases.py"],
        [sys.executable, "-m", "pipeline_impact", "--before", "cases/05-upload-condicional/before.yml",
         "--after", "cases/05-upload-condicional/after.yml", "--output", "reports/demo"],
    ]
    results = []
    for command in checks:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

        recorded_command = ["python"]
        for argument in command[1:]:
            recorded_command.append(argument)

        results.append({
            "command": recorded_command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })

        if result.returncode == 0:
            status = "OK"
        else:
            status = "FAIL"

        command_text = " ".join(command[1:])
        print(f"{status}: {command_text}")

    files = []
    for directory in ("src/pipeline_impact", "tests", "scripts"):
        source_directory = root / directory
        for source_path in source_directory.rglob("*.py"):
            files.append(source_path)

    source_hashes = {}
    for source_path in sorted(files):
        relative_path = source_path.relative_to(root)
        relative_name = str(relative_path).replace("\\", "/")
        source_bytes = source_path.read_bytes()
        source_hash = sha256(source_bytes).hexdigest()
        source_hashes[relative_name] = source_hash

    all_checks_passed = True
    for result in results:
        if result["returncode"] != 0:
            all_checks_passed = False
            break

    record = {
        "python": platform.python_version(),
        "pyyaml": yaml.__version__,
        "platform": platform.platform(),
        "checks": results,
        "source_sha256": source_hashes,
        "all_checks_passed": all_checks_passed,
        "github_execution_verified": False,
        "external_comparators_executed": False,
        "research_effectiveness_measured": False,
    }
    verification_path = root / "verification.json"
    verification_text = json.dumps(record, ensure_ascii=False, indent=2)
    verification_path.write_text(verification_text + "\n", encoding="utf-8")

    if all_checks_passed:
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
