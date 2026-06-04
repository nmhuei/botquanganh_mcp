import unittest
from unittest.mock import patch
from app.tools.health import get_capabilities, get_runner_environments
from app.tools.probe import check_target_allowed
from app.tools.fallback import validate_run_request

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
        self.assertTrue(res["ok"])
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
        from app.tools.runs import get_run_stdout, get_run_stderr, tail_run_output
        from app.config import RUNS_DIR
        
        # Create a mock run folder with stdout and stderr output
        run_id = "run_20260604_130000_87654321"
        run_dir = RUNS_DIR / run_id
        output_dir = run_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        (output_dir / "stdout.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
        (output_dir / "stderr.txt").write_text("error1\nerror2\n", encoding="utf-8")

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

if __name__ == "__main__":
    unittest.main()
