import json, unittest
from pathlib import Path
from alchemist.adapters import N8nAdapter, LangFlowAdapter
from alchemist.conversion import convert
from alchemist.core import validate_ir

ROOT = Path(__file__).parent
def fixture(name): return json.loads((ROOT / "fixtures" / name).read_text())

class AlchemistTests(unittest.TestCase):
    def test_all_schema_examples_pass_core_validation(self):
        for path in (ROOT.parent / "schemas/alchemist-ir/v0.1.0/examples").glob("*.json"):
            self.assertEqual([], validate_ir(json.loads(path.read_text())), path.name)

    def test_invalid_workflow(self):
        result = N8nAdapter().parse({"nodes": "bad"})
        self.assertFalse(result.ok); self.assertEqual("INVALID_SOURCE_WORKFLOW", result.diagnostics[0].code)

    def test_n8n_round_trip_preserves_nodes_edges_and_settings(self):
        source = fixture("n8n_linear.json"); parsed = N8nAdapter().parse(source); generated = N8nAdapter().generate(parsed.value)
        self.assertTrue(generated.ok); self.assertEqual(2, len(generated.value["nodes"])); self.assertEqual(source["connections"], generated.value["connections"]); self.assertEqual(source["settings"], generated.value["settings"])

    def test_langflow_round_trip_preserves_graph(self):
        source = fixture("langflow_linear.json"); parsed = LangFlowAdapter().parse(source); generated = LangFlowAdapter().generate(parsed.value)
        self.assertTrue(generated.ok); self.assertEqual(source["data"], generated.value["data"])

    def test_unknown_node_is_preserved_and_diagnosed(self):
        source = fixture("n8n_linear.json"); source["nodes"][0]["type"] = "community.magic"
        parsed = N8nAdapter().parse(source)
        self.assertEqual("custom", parsed.value["nodes"][0]["kind"]); self.assertIn("UNSUPPORTED_NODE_TYPE", [d.code for d in parsed.diagnostics])
        self.assertEqual("community.magic", N8nAdapter().generate(parsed.value).value["nodes"][0]["type"])

    def test_n8n_to_langflow(self):
        result = convert(fixture("n8n_linear.json"), "n8n", "langflow")
        self.assertTrue(result.ok); self.assertEqual(2, len(result.value["data"]["nodes"])); self.assertEqual(1, len(result.value["data"]["edges"]))

if __name__ == "__main__": unittest.main()
