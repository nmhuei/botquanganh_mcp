import unittest
from unittest.mock import patch
from app.auth import verify_token, require_token

class TestAuth(unittest.TestCase):
    @patch("app.auth.REQUIRE_AUTH", True)
    @patch("app.auth.GATEWAY_TOKEN", "test-secret-token")
    def test_verify_token(self):
        # Should return True for correct token
        self.assertTrue(verify_token("test-secret-token"))
        # Should return False for incorrect or empty token
        self.assertFalse(verify_token("wrong-token"))
        self.assertFalse(verify_token(""))

    @patch("app.auth.REQUIRE_AUTH", True)
    @patch("app.auth.GATEWAY_TOKEN", "test-secret-token")
    def test_require_token(self):
        # Should not raise exception for correct token
        require_token("test-secret-token")
        
        # Should raise PermissionError for incorrect token
        with self.assertRaises(PermissionError):
            require_token("wrong-token")

if __name__ == "__main__":
    unittest.main()
