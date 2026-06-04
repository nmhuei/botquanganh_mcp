import unittest
from unittest.mock import patch
from app.security import (
    validate_target_allowlisted,
    block_private_or_local_host,
    validate_timeout,
    validate_language,
    validate_args,
    validate_relative_path,
)

class TestSecurity(unittest.TestCase):
    @patch("app.security.ALLOWED_TCP_TARGETS", ["1.1.1.1:80", "13.238.150.105:36970"])
    def test_allowlisted_target_passes(self):
        # Should execute without raising
        validate_target_allowlisted("1.1.1.1", 80)
        validate_target_allowlisted("13.238.150.105", 36970)

    @patch("app.security.ALLOWED_TCP_TARGETS", ["1.1.1.1:80"])
    def test_non_allowlisted_target_rejected(self):
        with self.assertRaises(PermissionError):
            validate_target_allowlisted("1.1.1.1", 8080)
        with self.assertRaises(PermissionError):
            validate_target_allowlisted("8.8.8.8", 80)

    @patch("app.security.ALLOWED_TCP_TARGETS", ["*"])
    def test_wildcard_allowlist_passes_any_target(self):
        # Any target should pass when wildcard "*" is in allowlist
        validate_target_allowlisted("1.1.1.1", 80)
        validate_target_allowlisted("8.8.8.8", 443)
        validate_target_allowlisted("any-remote-host.com", 12345)


    @patch("app.security.BLOCK_PRIVATE_IPS", True)
    @patch("app.security.ALLOWED_TCP_TARGETS", ["1.1.1.1:80"])
    def test_private_ips_rejected(self):
        with self.assertRaises(PermissionError):
            block_private_or_local_host("localhost", 80)
        with self.assertRaises(PermissionError):
            block_private_or_local_host("127.0.0.1", 80)
        with self.assertRaises(PermissionError):
            block_private_or_local_host("192.168.1.5", 80)
        with self.assertRaises(PermissionError):
            block_private_or_local_host("169.254.169.254", 80)

    @patch("app.security.BLOCK_PRIVATE_IPS", True)
    @patch("app.security.ALLOWED_TCP_TARGETS", ["localhost:31337"])
    def test_private_ips_bypass_if_allowlisted(self):
        # If explicitly added to allowlist, it should bypass block
        block_private_or_local_host("localhost", 31337)

    @patch("app.security.MAX_TIMEOUT_SECONDS", 60)
    def test_validate_timeout(self):
        validate_timeout(30)
        with self.assertRaises(ValueError):
            validate_timeout(61)
        with self.assertRaises(ValueError):
            validate_timeout(0)
        with self.assertRaises(ValueError):
            validate_timeout(-10)

    def test_validate_language(self):
        validate_language("python")
        validate_language("pwn")
        validate_language("sage")
        with self.assertRaises(ValueError):
            validate_language("bash")
        with self.assertRaises(ValueError):
            validate_language("javascript")

    @patch("app.security.MAX_ARGS", 5)
    @patch("app.security.MAX_ARG_LENGTH", 10)
    def test_validate_args(self):
        validate_args(["a", "b", "c"])
        with self.assertRaises(ValueError):
            validate_args(["a", "b", "c", "d", "e", "f"])  # Exceeds limit count
        with self.assertRaises(ValueError):
            validate_args(["too-long-argument-string"])   # Exceeds max length

    def test_validate_relative_path(self):
        validate_relative_path("solve.py")
        validate_relative_path("lib/helper.py")
        with self.assertRaises(ValueError):
            validate_relative_path("/etc/passwd")
        with self.assertRaises(ValueError):
            validate_relative_path("../solve.py")
        with self.assertRaises(ValueError):
            validate_relative_path("a/../../b")
        with self.assertRaises(ValueError):
            validate_relative_path("")
        with self.assertRaises(ValueError):
            validate_relative_path(".")

    def test_format_error_response(self):
        from app.security import format_error_response
        
        # Test permission error targets
        err = format_error_response(PermissionError("not in the allowed_tcp_targets"))
        self.assertEqual(err["error"]["code"], "TARGET_NOT_ALLOWLISTED")
        
        # Test private IP blocking permission error
        err = format_error_response(PermissionError("blocked private ip"))
        self.assertEqual(err["error"]["code"], "POLICY_BLOCKED")
        
        # Test timeout value error
        err = format_error_response(ValueError("timeout exceeds max"))
        self.assertEqual(err["error"]["code"], "TIMEOUT_INVALID")
        
        # Test unsupported language
        err = format_error_response(ValueError("language not supported"))
        self.assertEqual(err["error"]["code"], "UNSUPPORTED_LANGUAGE")

if __name__ == "__main__":
    unittest.main()
