import unittest
from app.logging_audit import redact_sensitive_data

class TestLogs(unittest.TestCase):
    def test_redact_sensitive_data_dict(self):
        sensitive_payload = {
            "token": "sensitive_value_123",
            "gateway_token": "secret_gateway",
            "username": "safe_username",
            "nested": {
                "password": "some_password",
                "api_key": "some_api_key"
            },
            "list_of_secrets": [
                {"cookie": "session_cookie_abc"},
                {"public_data": "not_sensitive"}
            ]
        }
        
        redacted = redact_sensitive_data(sensitive_payload)
        
        # Verify secret keys are scrubbed
        self.assertEqual(redacted["token"], "[REDACTED]")
        self.assertEqual(redacted["gateway_token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["password"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["api_key"], "[REDACTED]")
        self.assertEqual(redacted["list_of_secrets"][0]["cookie"], "[REDACTED]")
        
        # Verify non-sensitive keys are preserved
        self.assertEqual(redacted["username"], "safe_username")
        self.assertEqual(redacted["list_of_secrets"][1]["public_data"], "not_sensitive")

    def test_redact_key_materials(self):
        pk_block = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQ...\n-----END PRIVATE KEY-----"
        redacted = redact_sensitive_data(pk_block)
        self.assertEqual(redacted, "[REDACTED KEY MATERIAL]")
        
        ssh_rsa = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQ..."
        redacted_ssh = redact_sensitive_data(ssh_rsa)
        self.assertEqual(redacted_ssh, "[REDACTED KEY MATERIAL]")

if __name__ == "__main__":
    unittest.main()
