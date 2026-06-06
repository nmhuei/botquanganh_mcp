import os
import shutil
import tempfile
import unittest
from pathlib import Path
from app.tools.agent import (
    agent_list_directory,
    agent_read_file,
    agent_write_file,
    agent_edit_file,
    agent_grep_search,
    agent_run_command,
    resolve_agent_path
)
import app.config

class TestAgentTools(unittest.TestCase):
    def setUp(self):
        # Store old configs
        self.old_dir = app.config.AGENT_WORKSPACE_DIR
        self.old_restrict = app.config.AGENT_RESTRICT_TO_WORKSPACE
        
        # Create temp dir
        self.temp_dir = Path(tempfile.mkdtemp(dir=Path.home())).resolve()
        app.config.AGENT_WORKSPACE_DIR = self.temp_dir
        app.config.AGENT_RESTRICT_TO_WORKSPACE = True

    def tearDown(self):
        # Cleanup
        shutil.rmtree(self.temp_dir)
        app.config.AGENT_WORKSPACE_DIR = self.old_dir
        app.config.AGENT_RESTRICT_TO_WORKSPACE = self.old_restrict

    def test_resolve_agent_path(self):
        # Valid paths inside workspace
        p1 = resolve_agent_path("foo/bar.txt")
        self.assertEqual(p1, self.temp_dir / "foo" / "bar.txt")

        home_relative = self.temp_dir.relative_to(Path.home())
        p2 = resolve_agent_path(f"~/{home_relative}/tilde.txt")
        self.assertEqual(p2, self.temp_dir / "tilde.txt")
        
        # Invalid path outside workspace (restriction is True)
        with self.assertRaises(PermissionError):
            resolve_agent_path("../outside.txt")

    def test_agent_write_and_read_file(self):
        # Test writing a file
        res_write = agent_write_file("test.txt", "hello agent world\nline 2\nline 3")
        self.assertTrue(res_write["ok"])
        
        # Test reading the file
        res_read = agent_read_file("test.txt")
        self.assertTrue(res_read["ok"])
        self.assertEqual(res_read["content"], "hello agent world\nline 2\nline 3")
        self.assertEqual(res_read["total_lines"], 3)
        self.assertFalse(res_read["sliced"])
        
        # Test reading with line range
        res_read_sliced = agent_read_file("test.txt", start_line=2, end_line=3)
        self.assertTrue(res_read_sliced["ok"])
        self.assertEqual(res_read_sliced["content"], "line 2\nline 3")
        self.assertEqual(res_read_sliced["start_line"], 2)
        self.assertEqual(res_read_sliced["end_line"], 3)
        self.assertTrue(res_read_sliced["sliced"])

    def test_agent_list_directory(self):
        # Write some files and directories
        agent_write_file("file1.txt", "content1")
        agent_write_file("subdir/file2.txt", "content2")
        
        res = agent_list_directory(".")
        self.assertTrue(res["ok"])
        items = res["items"]
        names = [i["name"] for i in items]
        self.assertIn("file1.txt", names)
        self.assertIn("subdir", names)
        
        # Check properties
        file1_item = [i for i in items if i["name"] == "file1.txt"][0]
        self.assertFalse(file1_item["is_directory"])
        self.assertEqual(file1_item["size_bytes"], 8)
        
        subdir_item = [i for i in items if i["name"] == "subdir"][0]
        self.assertTrue(subdir_item["is_directory"])

    def test_agent_edit_file(self):
        agent_write_file("edit_test.txt", "line 1\nreplace this line\nline 3")
        
        # Edit non-existent file
        res_err = agent_edit_file("nonexistent.txt", "replace", "with")
        self.assertFalse(res_err["ok"])
        
        # Try editing file with target that doesn't exist
        res_err_target = agent_edit_file("edit_test.txt", "not present", "with")
        self.assertFalse(res_err_target["ok"])
        
        # Edit successfully
        res_edit = agent_edit_file("edit_test.txt", "replace this line", "line 2 is updated")
        self.assertTrue(res_edit["ok"])
        
        res_read = agent_read_file("edit_test.txt")
        self.assertEqual(res_read["content"], "line 1\nline 2 is updated\nline 3")

    def test_agent_grep_search(self):
        agent_write_file("dir1/a.txt", "matching query here")
        agent_write_file("dir2/b.txt", "no match here")
        agent_write_file("dir1/c.txt", "another matching query")
        
        res = agent_grep_search("matching query")
        self.assertTrue(res["ok"])
        results = res["results"]
        self.assertEqual(len(results), 2)
        paths = [r["path"] for r in results]
        self.assertIn("dir1/a.txt", paths)
        self.assertIn("dir1/c.txt", paths)

    def test_agent_run_command(self):
        # Write a small file
        agent_write_file("input.txt", "hello")
        
        # Run echo command
        res = agent_run_command("echo 'it works'")
        self.assertTrue(res["ok"])
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("it works", res["stdout"])
        
        # Run a command listing files
        res_ls = agent_run_command("ls")
        self.assertTrue(res_ls["ok"])
        self.assertIn("input.txt", res_ls["stdout"])

        # Test blocked commands return error responses
        res_blocked2 = agent_run_command("rm -rf /")
        self.assertFalse(res_blocked2["ok"])
        self.assertEqual(res_blocked2["error"]["code"], "SCHEMA_INVALID")

if __name__ == "__main__":
    unittest.main()
