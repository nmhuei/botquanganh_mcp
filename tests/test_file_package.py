import unittest
import base64
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
from app.schemas import FileEntry
from app.file_package import (
    validate_and_decode_file,
    check_total_size_and_validate,
    write_files,
)

class TestFilePackage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_decode_text_file(self):
        entry = FileEntry(path="solve.py", encoding="text", content="print('hello')")
        data = validate_and_decode_file(entry)
        self.assertEqual(data, b"print('hello')")

    def test_decode_base64_file(self):
        raw_bytes = b"\x7fELFbinarystuff"
        b64_content = base64.b64encode(raw_bytes).decode("utf-8")
        entry = FileEntry(path="chall", encoding="base64", content=b64_content)
        data = validate_and_decode_file(entry)
        self.assertEqual(data, raw_bytes)

    @patch("app.file_package.MAX_SINGLE_FILE_BYTES", 10)
    def test_single_file_size_exceeded(self):
        entry = FileEntry(path="solve.py", encoding="text", content="too-long-text-payload")
        with self.assertRaises(ValueError):
            validate_and_decode_file(entry)

    @patch("app.file_package.MAX_CODE_BYTES", 15)
    def test_total_package_size_exceeded(self):
        entries = [
            FileEntry(path="a.py", encoding="text", content="12345678"),
            FileEntry(path="b.py", encoding="text", content="12345678")
        ]
        with self.assertRaises(ValueError):
            check_total_size_and_validate(entries)

    def test_duplicate_file_paths(self):
        entries = [
            FileEntry(path="solve.py", encoding="text", content="123"),
            FileEntry(path="solve.py", encoding="text", content="456")
        ]
        with self.assertRaises(ValueError):
            check_total_size_and_validate(entries)

    def test_write_files_and_prevent_escape(self):
        decoded = [
            ("solve.py", b"print('hello')"),
            ("utils/helper.py", b"def helper(): pass")
        ]
        write_files(self.temp_dir, decoded)
        
        self.assertTrue((self.temp_dir / "solve.py").exists())
        self.assertTrue((self.temp_dir / "utils" / "helper.py").exists())
        self.assertEqual((self.temp_dir / "solve.py").read_bytes(), b"print('hello')")
        
        # Test directory traversal escape rejection
        # This will normally be caught at path validation stage
        with self.assertRaises(ValueError):
            check_total_size_and_validate([
                FileEntry(path="../outside.py", encoding="text", content="test")
            ])
            
        # Directly call write_files to verify fail-safe checks inside write_files
        with self.assertRaises(PermissionError):
            write_files(self.temp_dir, [("../outside.py", b"test")])

if __name__ == "__main__":
    unittest.main()
