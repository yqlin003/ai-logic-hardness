import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gates.verify import GateRunner


class FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class GateRunnerTests(unittest.TestCase):
    @staticmethod
    def fake_secret():
        return "not-" + "a-placeholder-secret"

    def base_config(self):
        return {
            "requirements": ["The change preserves the public API."],
            "ambiguities": [],
            "invariants": ["Existing callers continue to work."],
            "max_changed_files": 3,
            "max_changed_lines": 20,
            "test_command": "python3 -c pass",
            "independent_checks": ["python3 -c pass"],
            "allowed_dependencies": [],
            "allowed_paths": ["src/**"],
        }

    def runner(self, config=None):
        directory = Path(tempfile.mkdtemp())
        return GateRunner(directory, config or self.base_config())

    def test_requirements_and_invariants_pass(self):
        runner = self.runner()
        self.assertTrue(runner.requirements_gate().passed)
        self.assertTrue(runner.invariants_gate().passed)

    def test_missing_requirements_blocks(self):
        config = self.base_config()
        config["requirements"] = []
        self.assertEqual(self.runner(config).requirements_gate().status, "blocked")

    def test_ambiguity_blocks(self):
        config = self.base_config()
        config["ambiguities"] = ["Should the endpoint be backwards compatible?"]
        result = self.runner(config).requirements_gate()
        self.assertEqual(result.status, "blocked")

    @patch.object(GateRunner, "_diff_text", return_value="+x = 1\n+API" + "_KEY = '" + "not-" + "a-placeholder-secret" + "'\n")
    def test_security_gate_fails_on_secret_pattern(self, _diff):
        result = self.runner().security_gate()
        self.assertEqual(result.status, "fail")
        self.assertIn("generic_secret_assignment", result.evidence["findings"])

    @patch.object(GateRunner, "_git")
    @patch.object(GateRunner, "_changed_files", return_value=["src/a.py", "src/b.py", "src/c.py", "src/d.py"])
    def test_small_change_gate_fails_when_too_many_files(self, _files, git):
        git.return_value = FakeCompleted(stdout="1\t1\tsrc/a.py\n")
        config = self.base_config()
        config["max_changed_files"] = 3
        result = self.runner(config).small_change_gate()
        self.assertEqual(result.status, "fail")

    @patch.object(GateRunner, "_diff_text", return_value="+import requests\n")
    @patch.object(GateRunner, "_changed_files", return_value=[])
    def test_dependency_gate_rejects_unapproved_import(self, _files, _diff):
        result = self.runner().dependency_gate()
        self.assertEqual(result.status, "fail")
        self.assertIn("requests", result.evidence["packages"])

    def test_full_run_abstains_without_test_evidence(self):
        config = self.base_config()
        config["test_command"] = ""
        config["independent_checks"] = []
        runner = self.runner(config)
        with patch.object(runner, "_git", return_value=FakeCompleted()), patch.object(runner, "_changed_files", return_value=[]):
            report = runner.run()
        self.assertEqual(report["decision"], "abstain")
        self.assertTrue(report["abstain"])
        self.assertIn("tests", report["missing_evidence_gates"])
        self.assertIn("independent_checks", report["missing_evidence_gates"])

    def test_diff_text_strips_ansi_codes(self):
        runner = self.runner()
        ansi_diff = "\x1b[32m+API_KEY = 'not-a-placeholder-secret'\x1b[m\n"
        with patch.object(runner, "_git", return_value=FakeCompleted(stdout=ansi_diff)), patch.object(runner, "_changed_files", return_value=[]):
            result = runner._diff_text()
        self.assertNotIn("\x1b", result)
        self.assertIn("API_KEY", result)

    @patch.object(GateRunner, "_diff_text", return_value="-API_KEY = '" + "not-" + "a-placeholder-secret" + "'\n+value = 1\n")
    def test_removed_secret_is_not_flagged(self, _diff):
        result = self.runner().security_gate()
        self.assertEqual(result.status, "pass")

    def test_untracked_secret_is_detected(self):
        runner = self.runner()
        secret_file = runner.root / "new.py"
        secret_file.write_text("API" + "_KEY = " + repr(self.fake_secret()) + "\n", encoding="utf-8")
        with patch.object(runner, "_git", side_effect=[FakeCompleted(), FakeCompleted(), FakeCompleted(), FakeCompleted(), FakeCompleted(stdout="new.py\n"), FakeCompleted(), FakeCompleted()]):
            result = runner.security_gate()
        self.assertEqual(result.status, "fail")

    @patch.object(GateRunner, "_diff_text", return_value="+from . import helpers\n+from .sibling import thing\n")
    @patch.object(GateRunner, "_changed_files", return_value=[])
    def test_dependency_gate_ignores_relative_imports(self, _files, _diff):
        result = self.runner().dependency_gate()
        self.assertEqual(result.status, "pass")

    @patch.object(GateRunner, "_diff_text", return_value="+import gates.verify\n+from gates import verify\n")
    @patch.object(GateRunner, "_changed_files", return_value=[])
    def test_dependency_gate_accepts_local_package_import(self, _files, _diff):
        runner = self.runner()
        package = runner.root / "gates"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "verify.py").write_text("", encoding="utf-8")
        result = runner.dependency_gate()
        self.assertEqual(result.status, "pass")

    @patch.object(GateRunner, "_diff_text", return_value="+import requests, flask as f\n")
    @patch.object(GateRunner, "_changed_files", return_value=[])
    def test_dependency_gate_detects_every_comma_separated_import(self, _files, _diff):
        result = self.runner().dependency_gate()
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.evidence["packages"], ["flask", "requests"])

    @patch.object(GateRunner, "_diff_text", return_value="")
    @patch.object(GateRunner, "_changed_files", return_value=["requirements.txt"])
    def test_dependency_gate_flags_unapproved_manifest_entry(self, _files, _diff):
        runner = self.runner()
        (runner.root / "requirements.txt").write_text("requests==2.31.0\n# comment\n", encoding="utf-8")
        result = runner.dependency_gate()
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.evidence["packages"], ["requests"])

    @patch.object(GateRunner, "_diff_text", return_value="")
    @patch.object(GateRunner, "_changed_files", return_value=["requirements.txt"])
    def test_dependency_gate_accepts_approved_manifest_entry_case_insensitively(self, _files, _diff):
        config = self.base_config()
        config["allowed_dependencies"] = ["requests"]
        runner = self.runner(config)
        (runner.root / "requirements.txt").write_text("Requests>=2.0\n", encoding="utf-8")
        result = runner.dependency_gate()
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.evidence["manifest_packages"], {"requirements.txt": ["Requests"]})

    @patch.object(GateRunner, "_diff_text", return_value="")
    @patch.object(GateRunner, "_changed_files", return_value=["pyproject.toml"])
    def test_dependency_gate_flags_unapproved_pyproject_dependency(self, _files, _diff):
        runner = self.runner()
        (runner.root / "pyproject.toml").write_text(
            '[project]\nname = "demo"\ndependencies = ["flask>=2.0"]\n', encoding="utf-8"
        )
        result = runner.dependency_gate()
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.evidence["packages"], ["flask"])

    @patch.object(GateRunner, "_diff_text", return_value="")
    @patch.object(GateRunner, "_changed_files", return_value=["package.json"])
    def test_dependency_gate_flags_unapproved_package_json_dependency(self, _files, _diff):
        runner = self.runner()
        (runner.root / "package.json").write_text('{"dependencies": {"lodash": "^4.17.21"}}\n', encoding="utf-8")
        result = runner.dependency_gate()
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.evidence["packages"], ["lodash"])

    @patch.object(GateRunner, "_diff_text", return_value="")
    @patch.object(GateRunner, "_changed_files", return_value=["package-lock.json"])
    def test_dependency_gate_blocks_unreviewed_lockfile_change(self, _files, _diff):
        result = self.runner().dependency_gate()
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.evidence["files_requiring_review"], ["package-lock.json"])

    @patch.object(GateRunner, "_diff_text", return_value="")
    @patch.object(GateRunner, "_changed_files", return_value=["package-lock.json"])
    def test_dependency_gate_accepts_reviewed_lockfile_change(self, _files, _diff):
        config = self.base_config()
        config["reviewed_dependency_files"] = ["package-lock.json"]
        result = self.runner(config).dependency_gate()
        self.assertEqual(result.status, "pass")

    @patch.object(GateRunner, "_git", return_value=FakeCompleted())
    @patch.object(GateRunner, "_changed_files", return_value=["src/nested/deeper/module.py"])
    def test_diff_audit_allows_nested_paths_under_recursive_pattern(self, _files, _git):
        result = self.runner().diff_audit_gate()
        self.assertEqual(result.status, "pass")

    @patch.object(GateRunner, "_git", return_value=FakeCompleted())
    @patch.object(GateRunner, "_changed_files", return_value=["outside/module.py"])
    def test_diff_audit_rejects_paths_outside_policy(self, _files, _git):
        result = self.runner().diff_audit_gate()
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.evidence["outside_allowed_paths"], ["outside/module.py"])


if __name__ == "__main__":
    unittest.main()
