import unittest
from app.auth import verify_token, require_token

class TestAuth(unittest.TestCase):
    def test_verify_token_always_true(self):
        self.assertTrue(verify_token("any-token"))
        self.assertTrue(verify_token(""))

    def test_require_token_never_raises(self):
        # Should not raise exception for any token
        require_token("any-token")
        require_token("")

if __name__ == "__main__":
    unittest.main()

