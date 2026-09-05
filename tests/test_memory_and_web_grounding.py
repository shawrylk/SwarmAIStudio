"""
Unit Tests for Disk Memory Engine and Live Web Scout Grounding
Ensures facts are grounded on disk filesystem and live web citations, avoiding fuzzy hallucinated memory.
"""

import os
import tempfile
import unittest
from pathlib import Path
from swarm.memory_engine import (
    read_disk_memory_files,
    format_disk_memory_prompt_block,
    extract_ast_symbol_summary
)
from swarm.web_scout import search_web_live, format_web_scout_prompt_block

class TestMemoryAndWebGrounding(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.temp_dir.name
        
        # Create mock rules and memory files
        swarm_dir = Path(self.repo_path) / ".swarm"
        swarm_dir.mkdir(parents=True, exist_ok=True)
        
        rules_file = swarm_dir / "global_rules.md"
        rules_file.write_text("# Global Rules\n1. Enforce small functions <= 35 lines.\n2. Use DI.", encoding="utf-8")

        memory_file = Path(self.repo_path) / "MEMORY.md"
        memory_file.write_text("# Project Memory\n- Uses Liquid LFM 2.5 on port 8034.\n- Continuous GPU batching enabled.", encoding="utf-8")

        pyproject = Path(self.repo_path) / "pyproject.toml"
        pyproject.write_text('[project]\nname = "mock-app"\nversion = "1.0.0"', encoding="utf-8")

        mock_src = Path(self.repo_path) / "main.py"
        mock_src.write_text('class AppService:\n    def execute(self):\n        pass\n\ndef bootstrap():\n    pass\n', encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_read_disk_memory_files_finds_all_on_disk(self):
        mem = read_disk_memory_files(self.repo_path)
        self.assertTrue(mem["has_disk_rules"])
        self.assertTrue(mem["has_repo_memory"])
        self.assertIn("mock-app", mem["manifest_config"])
        self.assertGreater(len(mem["ast_symbols"]), 0)
        self.assertTrue(any(s["name"] == "AppService" for s in mem["ast_symbols"]))

    def test_format_disk_memory_prompt_block(self):
        mem = read_disk_memory_files(self.repo_path)
        block = format_disk_memory_prompt_block(mem)
        self.assertIn("VERIFIED DISK MEMORY & GROUNDED FACTS", block)
        self.assertIn("AppService", block)

    def test_extract_ast_symbols(self):
        symbols = extract_ast_symbol_summary(self.repo_path)
        names = [s["name"] for s in symbols]
        self.assertIn("AppService", names)
        self.assertIn("bootstrap", names)

    def test_web_scout_search_and_formatting(self):
        res = search_web_live("FastAPI dependency injection")
        self.assertIsInstance(res, list)
        self.assertGreater(len(res), 0)
        self.assertIn("url", res[0])
        block = format_web_scout_prompt_block("FastAPI dependency injection", res)
        self.assertIn("LIVE WEB & DOCUMENTATION GROUNDING", block)

if __name__ == "__main__":
    unittest.main()
