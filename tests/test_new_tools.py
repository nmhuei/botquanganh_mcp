import unittest
from unittest.mock import patch
from app.tools.health import get_capabilities, get_runner_environments
from app.tools.probe import check_target_allowed
from app.tools.fallback import validate_run_request
from app.schemas import FileEntry, LocalValidation, SandboxFailure

class TestNewTools(unittest.TestCase):
    def test_get_capabilities(self):
        res = get_capabilities()
        self.assertTrue(res["ok"])
        self.assertIn("limits", res)
        self.assertIn("max_timeout_seconds", res["limits"])
        self.assertIn("supported_languages", res)
        self.assertIn("features", res)

    def test_get_runner_environments(self):
        res = get_runner_environments()
        self.assertTrue(res["ok"])
        self.assertIn("environments", res)
        self.assertIn("python", res["environments"])
        self.assertIn("sage", res["environments"])

    @patch("app.security.ALLOWED_TCP_TARGETS", ["1.1.1.1:80"])
    @patch("app.security.BLOCK_PRIVATE_IPS", True)
    def test_check_target_allowed(self):
        # Allowed target
        res = check_target_allowed("1.1.1.1", 80)
        self.assertTrue(res["ok"])
        self.assertTrue(res["allowed"])

        # Disallowed target
        res = check_target_allowed("8.8.8.8", 80)
        self.assertFalse(res["ok"])
        self.assertFalse(res["allowed"])
        self.assertEqual(res["error"]["code"], "TARGET_NOT_ALLOWLISTED")

    @patch("app.security.ALLOWED_TCP_TARGETS", ["1.1.1.1:80"])
    def test_validate_run_request(self):
        # Valid request
        res = validate_run_request(
            target={"host": "1.1.1.1", "port": 80},
            sandbox_failure={"attempted": True, "reason": "connection timed out"},
            local_validation={"solved_locally": True, "summary": "works locally"},
            files=[{"path": "solve.py", "encoding": "text", "content": "print('ok')"}],
            language="python",
            entrypoint="solve.py"
        )
        self.assertTrue(res["ok"])
        self.assertTrue(res["valid"])

        # Invalid due to missing entrypoint
        res = validate_run_request(
            target={"host": "1.1.1.1", "port": 80},
            sandbox_failure={"attempted": True, "reason": "connection timed out"},
            local_validation={"solved_locally": True, "summary": "works locally"},
            files=[{"path": "solve.py", "encoding": "text", "content": "print('ok')"}],
            language="python",
            entrypoint="missing.py"
        )
        self.assertFalse(res["ok"])
        self.assertFalse(res["valid"])
        self.assertEqual(res["error"]["code"], "SCHEMA_INVALID")

    @patch("app.security.ALLOWED_TCP_TARGETS", ["1.1.1.1:80"])
    def test_validate_run_request_accepts_chatgpt_friendly_aliases(self):
        res = validate_run_request(
            target={"host": "1.1.1.1", "port": 80},
            sandbox_failure={"reason": "connection_failed_in_sandbox", "evidence": "sandbox tcp connect failed"},
            local_validation={"status": "validated", "evidence": "solver worked locally"},
            files=[{"name": "solve.py", "content": "print('ok')"}],
            language="python",
            entrypoint="solve.py"
        )
        self.assertTrue(res["ok"])
        self.assertTrue(res["valid"])

    def test_file_entry_accepts_name_and_defaults_text_encoding(self):
        entry = FileEntry(name="solve.py", content="print('ok')\n")
        self.assertEqual(entry.path, "solve.py")
        self.assertEqual(entry.encoding, "text")

    def test_validation_models_accept_short_evidence_payloads(self):
        failure = SandboxFailure(reason="connection_failed_in_sandbox", evidence="tcp failed")
        validation = LocalValidation(status="validated", evidence="local solve ok")
        self.assertTrue(failure.attempted)
        self.assertTrue(validation.solved_locally)
        self.assertEqual(validation.summary, "local solve ok")

    def test_upload_artifact(self):
        from app.tools.fallback import upload_artifact
        res = upload_artifact(
            filename="solve.py",
            content="print('Artifact unit test')",
            encoding="text"
        )
        self.assertTrue(res["ok"])
        self.assertIn("artifact_id", res)
        self.assertTrue(res["artifact_id"].startswith("art_"))

    @patch("app.security.ALLOWED_TCP_TARGETS", ["1.1.1.1:80"])
    @patch("app.tools.fallback.execute_fallback_solver")
    def test_rerun_run(self, mock_execute):
        from app.tools.fallback import rerun_run
        from app.config import RUNS_DIR
        import json
        
        # Mock execute_fallback_solver return value
        class DummyResponse:
            def model_dump(self):
                return {"ok": True, "run_id": "new_run_id"}
        mock_execute.return_value = DummyResponse()

        # Set up a mock metadata file for the run to rerun
        run_id = "run_20260604_120000_12345678"
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        input_dir = run_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        
        # Write dummy solver file
        (input_dir / "solve.py").write_text("print('original')", encoding="utf-8")
        
        metadata = {
            "run_id": run_id,
            "target": "1.1.1.1:80",
            "language": "python",
            "entrypoint": "solve.py",
            "timeout_seconds": 30,
            "sandbox_failure": {"attempted": True, "reason": "test failure"},
            "local_validation": {"solved_locally": True, "summary": "test validation"},
            "files": [{"path": "solve.py", "size": 16, "sha256": "123"}]
        }
        (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

        # Rerun and patch it
        res = rerun_run(
            run_id=run_id,
            patch={
                "workspace": {
                    "files": [{"path": "solve.py", "encoding": "text", "content": "print('patched')"}]
                }
            }
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["derived_from"], run_id)
        
        # Clean up mock directories
        import shutil
        shutil.rmtree(run_dir)

    def test_log_tailing_tools(self):
        from app.tools.runs import get_run_stdout, get_run_stderr, get_run_summary, tail_run_output
        from app.config import RUNS_DIR
        import json
        
        # Create a mock run folder with stdout and stderr output
        run_id = "run_20260604_130000_87654321"
        run_dir = RUNS_DIR / run_id
        output_dir = run_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        (output_dir / "stdout.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
        (output_dir / "stderr.txt").write_text("error1\nerror2\n", encoding="utf-8")
        (run_dir / "metadata.json").write_text(json.dumps({
            "run_id": run_id,
            "target": "1.1.1.1:80",
            "language": "python",
            "entrypoint": "solve.py",
            "exit_code": 0,
            "duration_ms": 10,
            "created_at": "2026-06-05T00:00:00+00:00",
            "stdout_sha256": "stdout-hash",
            "stderr_sha256": "stderr-hash",
            "transcript_sha256": "transcript-hash"
        }), encoding="utf-8")

        # Test stdout tailing
        res = get_run_stdout(run_id=run_id, tail_lines=2)
        self.assertTrue(res["ok"])
        self.assertEqual(res["content"], "line2\nline3\n")

        # Test stderr tailing
        res = get_run_stderr(run_id=run_id)
        self.assertTrue(res["ok"])
        self.assertEqual(res["content"], "error1\nerror2\n")

        # Test simultaneous tailing
        res = tail_run_output(run_id=run_id, tail_lines=1)
        self.assertTrue(res["ok"])
        self.assertEqual(res["stdout"], "line3\n")
        self.assertEqual(res["stderr"], "error2\n")

        # Clean up mock directories
        import shutil
        shutil.rmtree(run_dir)

    def test_basic_run_logs_are_readable(self):
        from app.tools.basic_runner import run_basic_python_solver
        from app.tools.runs import get_run_log, get_run_stdout, get_run_summary, tail_run_output
        from app.config import RUNS_DIR
        import shutil

        res = run_basic_python_solver(
            files=[{"name": "solve.py", "content": "print('basic log ok')\n"}],
            entrypoint="solve.py",
            timeout_seconds=10
        )
        self.assertTrue(res["ok"])
        run_id = res["run_id"]

        try:
            stdout_res = get_run_stdout(run_id=run_id)
            self.assertTrue(stdout_res["ok"])
            self.assertIn("basic log ok", stdout_res["content"])

            tail_res = tail_run_output(run_id=run_id, tail_lines=1)
            self.assertTrue(tail_res["ok"])
            self.assertIn("basic log ok", tail_res["stdout"])

            summary_res = get_run_summary(run_id=run_id, tail_lines=1)
            self.assertTrue(summary_res["ok"])
            self.assertEqual(summary_res["type"], "basic_python_solver")
            self.assertIn("basic log ok", summary_res["stdout_tail"])

            log_res = get_run_log(run_id=run_id)
            self.assertTrue(log_res["ok"])
            self.assertEqual(log_res["metadata"]["exit_code"], 0)
        finally:
            shutil.rmtree(RUNS_DIR / run_id, ignore_errors=True)

    def test_run_safe_smoke_test(self):
        from app.tools.smoke import run_safe_smoke_test
        from app.config import RUNS_DIR
        import shutil

        res = run_safe_smoke_test(label="unit")
        self.assertTrue(res["ok"])
        run_ids = [
            test.get("details", {}).get("run_id")
            for test in res["tests"]
            if test["name"] == "run_basic_python_solver"
        ]
        try:
            self.assertEqual(len(run_ids), 1)
            self.assertTrue(run_ids[0].startswith("basic_"))
        finally:
            for run_id in run_ids:
                shutil.rmtree(RUNS_DIR / run_id, ignore_errors=True)

    def test_workspace_lifecycle(self):
        from app.tools.workspace import (
            create_workspace,
            upload_file_to_workspace,
            list_workspace_files,
            read_workspace_file,
            delete_workspace
        )
        
        # 1. Create workspace
        create_res = create_workspace(label="test_ws")
        self.assertTrue(create_res["ok"])
        workspace_id = create_res["workspace_id"]
        
        # 2. Upload text file
        upload_res = upload_file_to_workspace(
            workspace_id=workspace_id,
            filename="hello.txt",
            content="Hello Workspace!",
            encoding="text"
        )
        self.assertTrue(upload_res["ok"])
        self.assertEqual(upload_res["filename"], "hello.txt")
        
        # 3. List files
        list_res = list_workspace_files(workspace_id=workspace_id)
        self.assertTrue(list_res["ok"])
        self.assertEqual(len(list_res["files"]), 1)
        self.assertEqual(list_res["files"][0]["name"], "hello.txt")
        
        # 4. Read file
        read_res = read_workspace_file(
            workspace_id=workspace_id,
            filename="hello.txt",
            encoding="text"
        )
        self.assertTrue(read_res["ok"])
        self.assertEqual(read_res["content"], "Hello Workspace!")
        
        # 5. Delete workspace
        delete_res = delete_workspace(workspace_id=workspace_id)
        self.assertTrue(delete_res["ok"])

    @patch("subprocess.run")
    def test_run_command(self, mock_sub_run):
        from app.tools.shell import run_command
        from app.tools.workspace import create_workspace, delete_workspace
        
        # Setup workspace
        ws_res = create_workspace(label="test_shell")
        ws_id = ws_res["workspace_id"]
        
        # Mock subprocess return value
        class DummyProcess:
            returncode = 0
            stdout = b"mock output\n"
            stderr = b""
        mock_sub_run.return_value = DummyProcess()
        
        res = run_command(
            workspace_id=ws_id,
            command="ls -la",
            language="forensics",
            timeout_seconds=10
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["stdout"], "mock output\n")
        
        # Cleanup
        delete_workspace(ws_id)

    @patch("subprocess.run")
    def test_run_command_without_workspace_uses_host_workspace(self, mock_sub_run):
        from app.tools.shell import run_command

        class DummyProcess:
            returncode = 0
            stdout = b"repo files\n"
            stderr = b""
        mock_sub_run.return_value = DummyProcess()

        res = run_command(command="ls", timeout_seconds=10)
        self.assertTrue(res["ok"])
        self.assertEqual(res["mode"], "host")
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["stdout"], "repo files\n")

    @patch("app.security.ALLOWED_TCP_TARGETS", ["1.1.1.1:80"])
    def test_run_basic_python_solver(self):
        from app.tools.basic_runner import run_basic_python_solver

        res = run_basic_python_solver(
            target={"host": "1.1.1.1", "port": 80},
            files=[{
                "path": "solve.py",
                "encoding": "text",
                "content": "import os\nprint(os.environ['TARGET_HOST'] + ':' + os.environ['TARGET_PORT'])\n"
            }],
            entrypoint="solve.py",
            timeout_seconds=10
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("1.1.1.1:80", res["stdout"])

    def test_run_basic_python_solver_without_target_and_name_alias(self):
        from app.tools.basic_runner import run_basic_python_solver

        res = run_basic_python_solver(
            files=[{
                "name": "solve.py",
                "encoding": "text",
                "content": "print('import-only smoke test')\n"
            }],
            entrypoint="solve.py",
            timeout_seconds=10
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("import-only smoke test", res["stdout"])
        self.assertTrue(res["warnings"])


if __name__ == "__main__":
    unittest.main()
