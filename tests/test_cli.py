import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent

class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "alchemist.cli", *args], cwd=ROOT, text=True, capture_output=True, check=False)

    def test_inspect_n8n(self):
        result = self.run_cli("inspect", "--from", "n8n", "tests/fixtures/n8n_linear.json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({"valid": True, "nodes": 2, "edges": 1, "diagnostics": []}, json.loads(result.stdout))

    def test_convert_n8n_to_langflow_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "flow.json"
            result = self.run_cli("convert", "--from", "n8n", "--to", "langflow", "tests/fixtures/n8n_linear.json", "-o", str(output))
            self.assertEqual(0, result.returncode, result.stderr)
            generated = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(2, len(generated["data"]["nodes"]))

if __name__ == "__main__": unittest.main()
