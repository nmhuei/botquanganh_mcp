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

if __name__ == "__main__":
    unittest.main()
