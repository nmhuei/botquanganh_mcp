import unittest
from unittest.mock import patch, MagicMock
from app.egress_firewall import apply_egress_rules, remove_egress_rules

class TestFirewall(unittest.TestCase):
    @patch("app.egress_firewall.ENABLE_EGRESS_FIREWALL", True)
    @patch("app.egress_firewall.resolve_target_ip", return_value="93.184.216.34")
    @patch("app.egress_firewall.subprocess.run")
    def test_apply_egress_rules(self, mock_run, mock_resolve):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        apply_egress_rules("172.17.0.5", "example.com", 80)
        
        # Expect two iptables additions (one for DROP, one for ACCEPT)
        self.assertEqual(mock_run.call_count, 2)
        
        drop_cmd = mock_run.call_args_list[0][0][0]
        accept_cmd = mock_run.call_args_list[1][0][0]
        
        # Verify commands structure
        self.assertIn("DROP", drop_cmd)
        self.assertIn("172.17.0.5", drop_cmd)
        
        self.assertIn("ACCEPT", accept_cmd)
        self.assertIn("172.17.0.5", accept_cmd)
        self.assertIn("93.184.216.34", accept_cmd)
        self.assertIn("80", accept_cmd)

    @patch("app.egress_firewall.ENABLE_EGRESS_FIREWALL", True)
    @patch("app.egress_firewall.resolve_target_ip", return_value="93.184.216.34")
    @patch("app.egress_firewall.subprocess.run")
    def test_remove_egress_rules(self, mock_run, mock_resolve):
        remove_egress_rules("172.17.0.5", "example.com", 80)
        
        # Expect two deletions (one for ACCEPT, one for DROP)
        self.assertEqual(mock_run.call_count, 2)
        
        delete_accept_cmd = mock_run.call_args_list[0][0][0]
        delete_drop_cmd = mock_run.call_args_list[1][0][0]
        
        self.assertIn("-D", delete_accept_cmd)
        self.assertIn("ACCEPT", delete_accept_cmd)
        
        self.assertIn("-D", delete_drop_cmd)
        self.assertIn("DROP", delete_drop_cmd)

if __name__ == "__main__":
    unittest.main()
