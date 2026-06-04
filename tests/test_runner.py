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

if __name__ == "__main__":
    unittest.main()
