"""Verifier-centered gates for AI-assisted coding changes.

The runner is intentionally dependency-free. It treats every gate as evidence,
not as a claim of correctness. A blocked run must be reviewed before merging.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GateResult:
    name: str
    status: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


class GateRunner:
    def __init__(self, root: Path, config: dict[str, Any]) -> None:
        self.root = root.resolve()
        self.config = config
        self.results: list[GateResult] = []

    def run(self) -> dict[str, Any]:
        for gate in (
            self.requirements_gate,
            self.invariants_gate,
            self.small_change_gate,
            self.test_gate,
            self.independent_checks_gate,
            self.security_gate,
            self.dependency_gate,
            self.diff_audit_gate,
        ):
            self.results.append(gate())

        failed = [r.name for r in self.results if not r.passed]
        evidence_missing = [
            r.name for r in self.results if r.status == "blocked"
        ]
        decision = "approve" if not failed else "abstain"
        return {
            "decision": decision,
            "abstain": decision == "abstain",
            "failed_gates": failed,
            "missing_evidence_gates": evidence_missing,
            "gates": [asdict(r) for r in self.results],
        }

    def requirements_gate(self) -> GateResult:
        requirements = self.config.get("requirements", [])
        ambiguities = self.config.get("ambiguities", [])
        if not requirements:
            return GateResult("requirements", "blocked", "No requirements supplied.")
        if ambiguities:
            return GateResult(
                "requirements",
                "blocked",
                "Unresolved ambiguities remain.",
                {"ambiguities": ambiguities},
            )
        invalid = [r for r in requirements if not isinstance(r, str) or not r.strip()]
        if invalid:
            return GateResult("requirements", "fail", "Requirements contain empty entries.")
        return GateResult(
            "requirements", "pass", f"Validated {len(requirements)} requirement(s).",
            {"count": len(requirements)},
        )

    def invariants_gate(self) -> GateResult:
        invariants = self.config.get("invariants", [])
        if not invariants:
            return GateResult("invariants", "blocked", "No invariants supplied.")
        if any(not isinstance(i, str) or not i.strip() for i in invariants):
            return GateResult("invariants", "fail", "Invariants contain empty entries.")
        return GateResult(
            "invariants", "pass", f"Recorded {len(invariants)} invariant(s).",
            {"count": len(invariants)},
        )

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=self.root, text=True, capture_output=True, check=False
        )

    def _changed_files(self) -> list[str]:
        base = self.config.get("base", "HEAD")
        result = self._git("diff", "--name-only", base, "--")
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        staged = self._git("diff", "--cached", "--name-only")
        files.extend(line.strip() for line in staged.stdout.splitlines() if line.strip())
        untracked = self._git("ls-files", "--others", "--exclude-standard")
        files.extend(line.strip() for line in untracked.stdout.splitlines() if line.strip())
        return sorted(set(files))

    def small_change_gate(self) -> GateResult:
        max_files = int(self.config.get("max_changed_files", 10))
        max_lines = int(self.config.get("max_changed_lines", 500))
        base = self.config.get("base", "HEAD")
        stat = self._git("diff", "--numstat", base, "--")
        added = deleted = 0
        for line in stat.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
                added += int(fields[0])
                deleted += int(fields[1])
        files = self._changed_files()
        tracked = set(self._git("diff", "--name-only", base, "--").stdout.splitlines()) | set(self._git("diff", "--cached", "--name-only").stdout.splitlines())
        for path in set(files) - tracked:
            candidate = self.root / path
            try:
                added += len(candidate.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError):
                added += 1
        if len(files) > max_files or added + deleted > max_lines:
            return GateResult(
                "small_change", "fail", "Change exceeds configured review limits.",
                {"files": files, "file_count": len(files), "lines_changed": added + deleted,
                 "limits": {"max_files": max_files, "max_lines": max_lines}},
            )
        return GateResult(
            "small_change", "pass", "Change is within configured review limits.",
            {"files": files, "file_count": len(files), "lines_changed": added + deleted},
        )

    def _run_command(self, command: str, timeout: int = 120) -> tuple[int, str]:
        try:
            result = subprocess.run(
                shlex.split(command), cwd=self.root, text=True, capture_output=True,
                timeout=timeout, check=False,
            )
            output = (result.stdout + result.stderr).strip()
            return result.returncode, output[-4000:]
        except subprocess.TimeoutExpired as exc:
            return 124, f"Timed out after {timeout}s: {exc}"
        except OSError as exc:
            return 127, str(exc)

    def test_gate(self) -> GateResult:
        command = self.config.get("test_command")
        if not command:
            return GateResult("tests", "blocked", "No test command supplied.")
        code, output = self._run_command(command, int(self.config.get("test_timeout", 120)))
        return GateResult(
            "tests", "pass" if code == 0 else "fail",
            "Test command completed successfully." if code == 0 else "Test command failed.",
            {"command": command, "exit_code": code, "output": output},
        )

    def independent_checks_gate(self) -> GateResult:
        commands = self.config.get("independent_checks", [])
        if not commands:
            return GateResult("independent_checks", "blocked", "No independent checks supplied.")
        evidence = []
        for command in commands:
            code, output = self._run_command(command, int(self.config.get("check_timeout", 120)))
            evidence.append({"command": command, "exit_code": code, "output": output})
        failed = [item for item in evidence if item["exit_code"] != 0]
        return GateResult(
            "independent_checks", "fail" if failed else "pass",
            "One or more independent checks failed." if failed else "Independent checks passed.",
            {"checks": evidence},
        )

    def _diff_text(self) -> str:
        base = self.config.get("base", "HEAD")
        result = self._git("diff", base, "--")
        staged = self._git("diff", "--cached", "--")
        raw = result.stdout + "\n" + staged.stdout
        # Include untracked text files because a pre-commit gate must not allow
        # new files to bypass security, dependency, or diff-policy checks.
        tracked = set(self._git("diff", "--name-only", base, "--").stdout.splitlines()) | set(self._git("diff", "--cached", "--name-only").stdout.splitlines())
        for path in set(self._changed_files()) - tracked:
            candidate = self.root / path
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            raw += f"\n+++ untracked/{path}\n" + "\n".join("+" + line for line in content.splitlines())
        # Git may emit ANSI color codes from the user's global configuration;
        # remove them before applying source-text security and dependency rules.
        return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw)

    def security_gate(self) -> GateResult:
        diff = self._diff_text()
        additions = "\\n".join(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        patterns = {
            "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            "aws_access_key": r"\bAKIA[0-9A-Z]{16}\b",
            "generic_secret_assignment": r"\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        }
        findings = [name for name, pattern in patterns.items() if re.search(pattern, additions, flags=re.IGNORECASE)]
        if findings:
            return GateResult("security", "fail", "Potential secret material found in the diff.", {"findings": findings})
        return GateResult("security", "pass", "No configured secret patterns found in the diff.")

    def dependency_gate(self) -> GateResult:
        diff = self._diff_text()
        additions = "\n".join(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        allowed = set(self.config.get("allowed_dependencies", []))
        stdlib = set(getattr(sys, "stdlib_module_names", ()))
        local_modules = set()
        for path in self.root.rglob("*.py"):
            if ".git" in path.parts:
                continue
            local_modules.add(path.stem)
            relative = path.relative_to(self.root)
            local_modules.update(part for part in relative.parts[:-1])
        suspicious = []
        for match in re.finditer(r"(?m)^\s*(?:from|import)\s+([A-Za-z0-9_.-]+)", additions):
            package = match.group(1).split(".")[0]
            if package not in allowed and package not in stdlib and package not in local_modules:
                suspicious.append(package)
        new_dependency_files = [f for f in self._changed_files() if Path(f).name in {"requirements.txt", "pyproject.toml", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}]
        if suspicious:
            return GateResult("dependencies", "fail", "Unapproved imported dependency detected.", {"packages": sorted(set(suspicious))})
        return GateResult("dependencies", "pass", "Dependency changes passed the configured policy.", {"dependency_files": new_dependency_files})

    def diff_audit_gate(self) -> GateResult:
        result = self._git("diff", "--check", self.config.get("base", "HEAD"), "--")
        allowed_paths = self.config.get("allowed_paths", [])
        files = self._changed_files()
        outside = []
        if allowed_paths:
            outside = [f for f in files if not any(Path(f).match(pattern) for pattern in allowed_paths)]
        if result.returncode != 0 or outside:
            return GateResult(
                "diff_audit", "fail", "Diff audit found whitespace or path-policy violations.",
                {"git_diff_check": result.stdout + result.stderr, "outside_allowed_paths": outside},
            )
        return GateResult("diff_audit", "pass", "Diff is clean and within the configured path policy.", {"files": files})


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run verifier-centered coding gates")
    parser.add_argument("--config", default="gates.config.json")
    parser.add_argument("--root", default=".")
    parser.add_argument("--report", default="gate-report.json")
    args = parser.parse_args(argv)
    try:
        report = GateRunner(Path(args.root), load_config(Path(args.config))).run()
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if report["decision"] == "approve" else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"gate runner error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
