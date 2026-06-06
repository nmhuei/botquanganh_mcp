import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.docker_runner import run_in_docker

class TestRunner(unittest.TestCase):
    @patch("app.docker_runner.subprocess.run")
    def test_run_in_docker_success(self, mock_run):
        # 1. Mock first subprocess.run (container creation/launch)
        mock_start = MagicMock()
        mock_start.returncode = 0
        mock_start.stdout = "container_hash_12345\n"
        
        # 2. Mock second subprocess.run (exec solver script)
        mock_exec = MagicMock()
        mock_exec.returncode = 0
        mock_exec.stdout = b"solver flag: FLAG{mocked_success}\n"
        mock_exec.stderr = b"warning: debugger not attached\n"
        
        # side_effect: start, exec, kill, rm
        mock_run.side_effect = [mock_start, mock_exec, MagicMock(), MagicMock()]
        
        exit_code, stdout, stderr, timed_out = run_in_docker(
            container_name="test_fallback_runner",
            run_input_dir=Path("/tmp"),
            entrypoint="solve.py",
            args=["--remote"],
            env={"DEBUG": "1"},
            timeout=30,
            language="python",
            target_host="1.1.1.1",
            target_port=80
        )
        
        self.assertEqual(exit_code, 0)
        self.assertIn("FLAG{mocked_success}", stdout)
        self.assertIn("debugger not attached", stderr)
        self.assertFalse(timed_out)

        docker_run_cmd = mock_run.call_args_list[0].args[0]
        docker_exec_cmd = mock_run.call_args_list[1].args[0]
        self.assertIn("TARGET_HOST=1.1.1.1", docker_run_cmd)
        self.assertIn("TARGET_PORT=80", docker_run_cmd)
        self.assertIn("CTF_HOST=1.1.1.1", docker_run_cmd)
        self.assertIn("CTF_PORT=80", docker_run_cmd)
        self.assertIn("DEBUG=1", docker_run_cmd)
        self.assertIn("TARGET_HOST=1.1.1.1", docker_exec_cmd)
        self.assertIn("TARGET_PORT=80", docker_exec_cmd)
        self.assertIn("CTF_HOST=1.1.1.1", docker_exec_cmd)
        self.assertIn("CTF_PORT=80", docker_exec_cmd)
        self.assertIn("DEBUG=1", docker_exec_cmd)
        
    @patch("app.docker_runner.subprocess.run")
    def test_run_in_docker_timeout(self, mock_run):
        mock_start = MagicMock()
        mock_start.returncode = 0
        
        # Mock TimeoutExpired exception on the 2nd call (exec)
        mock_run.side_effect = [
            mock_start,
            subprocess.TimeoutExpired(
                cmd=["docker", "exec"], 
                timeout=10, 
                output=b"partial output before timeout", 
                stderr=b"runtime logs"
            ),
            MagicMock(),  # kill
            MagicMock()   # rm
        ]
        
        exit_code, stdout, stderr, timed_out = run_in_docker(
            container_name="test_fallback_runner",
            run_input_dir=Path("/tmp"),
            entrypoint="solve.py",
            args=[],
            env={},
            timeout=10,
            language="python",
            target_host="1.1.1.1",
            target_port=80
        )
        
        self.assertEqual(exit_code, -1)
        self.assertTrue(timed_out)
        self.assertIn("partial output before timeout", stdout)
        self.assertIn("Process timed out", stderr)

    @patch("app.runner.subprocess.run")
    def test_run_locally_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = b"local success\n"
        mock_res.stderr = b"local warnings\n"
        mock_run.return_value = mock_res
        
        from app.runner import run_locally
        exit_code, stdout, stderr, timed_out = run_locally(
            run_input_dir=Path("/tmp"),
            entrypoint="solve.py",
            args=["--remote"],
            env={"DEBUG": "1"},
            timeout=30,
            language="python",
            target_host="1.1.1.1",
            target_port=80
        )
        
        self.assertEqual(exit_code, 0)
        self.assertIn("local success", stdout)
        self.assertIn("local warnings", stderr)
        self.assertFalse(timed_out)

    @patch("app.runner.run_locally")
    @patch("app.runner.write_files")
    @patch("app.runner.check_total_size_and_validate")
    @patch("app.runner.USE_DOCKER", False)
    def test_execute_fallback_solver_locally(self, mock_validate, mock_write, mock_run_locally):
        mock_validate.return_value = [("solve.py", b"print('hello')")]
        mock_run_locally.return_value = (0, "output", "errors", False)
        
        from app.runner import execute_fallback_solver
        from app.schemas import FallbackRequest, Target, SandboxFailure, LocalValidation
        
        req = FallbackRequest(
            target=Target(host="1.1.1.1", port=80),
            language="python",
            entrypoint="solve.py",
            args=[],
            env={},
            timeout_seconds=30,
            files=[],
            sandbox_failure=SandboxFailure(reason="mock"),
            local_validation=LocalValidation(solved_locally=True)
        )
        
        res = execute_fallback_solver(req)
        self.assertTrue(res.ok)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.stdout, "output")
        mock_run_locally.assert_called_once()

if __name__ == "__main__":
    unittest.main()
