import io
import json
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from alchemist.adapters import N8nAdapter
from alchemist.cli import main
from alchemist.conversion import convert
from alchemist.semantic import LLMConfig, OpenAICompatibleClient, SemanticMapper, SemanticMapperError

ROOT = Path(__file__).parent
SCHEMA = Draft202012Validator(json.loads((ROOT.parent / "schemas/alchemist-ir/v0.1.0/schema.json").read_text()))
CONFIG = LLMConfig(base_url="http://llm.test/v1", model="fake-model")


def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text())


def custom_source():
    source = fixture("n8n_linear.json")
    source["nodes"][1]["type"] = "community.slackSend"
    return source


class FakeClient:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def complete(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def mapper(*replies):
    client = FakeClient(*replies)
    return SemanticMapper(client, model="fake-model"), client


def codes(result):
    return [d.code for d in result.diagnostics]


class SemanticMapperTests(unittest.TestCase):
    def test_deterministic_path_is_the_default(self):
        result = convert(custom_source(), "n8n", "ir")
        self.assertEqual("custom", result.value["nodes"][1]["kind"])
        self.assertNotIn("alchemist", result.value["nodes"][1].get("extensions", {}))
        self.assertNotIn("alchemist", result.value["extensions"])

    def test_maps_unresolved_node_with_provenance_and_valid_ir(self):
        m, client = mapper({"nodes": [{"id": "2", "kind": "tool", "inputs": [{"name": "text", "required": True}], "outputs": [{"name": "message_id"}], "rationale": "posts a Slack message"}]})
        result = convert(custom_source(), "n8n", "ir", semantic_mapper=m)
        self.assertTrue(result.ok, result.diagnostics)
        node = result.value["nodes"][1]
        self.assertEqual("tool", node["kind"])
        self.assertEqual([{"name": "text", "required": True}], node["inputs"])
        self.assertEqual({"source": "llm", "model": "fake-model", "fields": ["kind", "inputs", "outputs"], "previous_kind": "custom", "rationale": "posts a Slack message"}, node["extensions"]["alchemist"]["provenance"])
        self.assertEqual({"source": "rule"}, result.value["nodes"][0]["extensions"]["alchemist"]["provenance"])
        self.assertEqual({"model": "fake-model", "mapped": ["2"], "rejected": []}, result.value["extensions"]["alchemist"]["semantic_mapper"])
        approx = [d for d in result.diagnostics if d.code == "SEMANTIC_APPROXIMATION"]
        self.assertEqual(["/nodes/1"], [d.path for d in approx])
        self.assertEqual("llm", approx[0].details["provenance"])
        self.assertEqual([], list(SCHEMA.iter_errors(result.value)))
        self.assertEqual(1, len(client.calls))
        self.assertIn("community.slackSend", client.calls[0][-1]["content"])

    def test_config_values_are_not_sent_to_the_llm(self):
        source = custom_source()
        source["nodes"][1]["parameters"] = {"token": "s3cr3t-value"}
        m, client = mapper({"nodes": []})
        convert(source, "n8n", "ir", semantic_mapper=m)
        prompt = json.dumps(client.calls[0])
        self.assertIn("token", prompt)
        self.assertNotIn("s3cr3t-value", prompt)

    def test_mapped_node_still_generates_original_vendor_type(self):
        m, _ = mapper({"nodes": [{"id": "2", "kind": "tool"}]})
        result = convert(custom_source(), "n8n", "n8n", semantic_mapper=m)
        self.assertTrue(result.ok)
        self.assertEqual("community.slackSend", result.value["nodes"][1]["type"])

    def test_rejects_invalid_proposals_and_keeps_the_rest(self):
        source = custom_source()
        source["nodes"].append({"id": "3", "name": "Other", "type": "community.other", "parameters": {}})
        source["nodes"].append({"id": "4", "name": "Third", "type": "community.third", "parameters": {}})
        source["nodes"].append({"id": "5", "name": "Fourth", "type": "community.fourth", "parameters": {}})
        proposals = {"nodes": [
            {"id": "2", "kind": "spaceship"},
            {"id": "1", "kind": "tool"},
            {"id": "ghost", "kind": "tool"},
            {"id": "3", "kind": "tool", "inputs": [{"label": "no name"}]},
            {"id": "4", "kind": "tool", "config": {"url": "x"}},
            {"id": "5", "kind": "memory"},
            {"id": "5", "kind": "tool"},
        ]}
        m, _ = mapper(proposals)
        result = convert(source, "n8n", "ir", semantic_mapper=m)
        self.assertTrue(result.ok)
        kinds = {n["id"]: n["kind"] for n in result.value["nodes"]}
        self.assertEqual({"1": "input", "2": "custom", "3": "custom", "4": "custom", "5": "memory"}, kinds)
        rejected = [d for d in result.diagnostics if d.code == "SEMANTIC_MAPPING_REJECTED"]
        self.assertEqual(6, len(rejected))
        self.assertEqual({"model": "fake-model", "mapped": ["5"], "rejected": ["2", "1", "ghost", "3", "4", "5"]}, result.value["extensions"]["alchemist"]["semantic_mapper"])
        self.assertEqual([], list(SCHEMA.iter_errors(result.value)))

    def test_rejects_non_string_ids(self):
        m, _ = mapper({"nodes": [{"id": ["2"], "kind": "tool"}, "junk"]})
        result = convert(custom_source(), "n8n", "ir", semantic_mapper=m)
        self.assertEqual("custom", result.value["nodes"][1]["kind"])
        self.assertEqual(2, codes(result).count("SEMANTIC_MAPPING_REJECTED"))

    def test_rerun_on_ir_keeps_earlier_llm_provenance(self):
        source = custom_source()
        source["nodes"].append({"id": "3", "name": "Other", "type": "community.other", "parameters": {}})
        first, _ = mapper({"nodes": [{"id": "2", "kind": "tool"}]})
        ir = convert(source, "n8n", "ir", semantic_mapper=first).value
        second, _ = mapper({"nodes": [{"id": "3", "kind": "transform"}]})
        result = convert(ir, "ir", "ir", semantic_mapper=second)
        self.assertEqual("llm", result.value["nodes"][1]["extensions"]["alchemist"]["provenance"]["source"])
        self.assertEqual("llm", result.value["nodes"][2]["extensions"]["alchemist"]["provenance"]["source"])
        self.assertEqual("rule", result.value["nodes"][0]["extensions"]["alchemist"]["provenance"]["source"])

    def test_custom_kind_proposal_is_a_no_op(self):
        m, _ = mapper({"nodes": [{"id": "2", "kind": "custom"}]})
        result = convert(custom_source(), "n8n", "ir", semantic_mapper=m)
        self.assertEqual("custom", result.value["nodes"][1]["kind"])
        self.assertNotIn("SEMANTIC_APPROXIMATION", codes(result))
        self.assertNotIn("SEMANTIC_MAPPING_REJECTED", codes(result))

    def test_falls_back_to_deterministic_ir_on_errors(self):
        deterministic = N8nAdapter().parse(custom_source()).value
        for reply in (SemanticMapperError("connection refused"), "not json", '{"nodes": "nope"}', "[]"):
            with self.subTest(reply=reply):
                m, _ = mapper(reply)
                result = convert(custom_source(), "n8n", "ir", semantic_mapper=m)
                self.assertTrue(result.ok)
                self.assertEqual(deterministic, result.value)
                unavailable = [d for d in result.diagnostics if d.code == "SEMANTIC_MAPPER_UNAVAILABLE"]
                self.assertEqual(1, len(unavailable))
                self.assertEqual("warning", unavailable[0].severity.value)

    def test_accepts_fenced_json_reply(self):
        m, _ = mapper('```json\n{"nodes": [{"id": "2", "kind": "tool"}]}\n```')
        result = convert(custom_source(), "n8n", "ir", semantic_mapper=m)
        self.assertEqual("tool", result.value["nodes"][1]["kind"])

    def test_does_not_call_llm_when_rules_resolve_everything(self):
        m, client = mapper()
        result = convert(fixture("n8n_linear.json"), "n8n", "ir", semantic_mapper=m)
        self.assertTrue(result.ok)
        self.assertEqual([], client.calls)
        self.assertNotIn("alchemist", result.value["extensions"])

    def test_invalid_source_skips_mapper(self):
        m, client = mapper()
        result = convert({"nodes": "bad"}, "n8n", "ir", semantic_mapper=m)
        self.assertFalse(result.ok)
        self.assertEqual([], client.calls)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def chat_reply(content):
    return FakeResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


class OpenAICompatibleClientTests(unittest.TestCase):
    def test_posts_chat_completion_with_bearer_key(self):
        config = LLMConfig(base_url="http://llm.test/v1/", model="m", api_key="k", timeout=7)
        with mock.patch("urllib.request.urlopen", return_value=chat_reply("{}")) as urlopen:
            self.assertEqual("{}", OpenAICompatibleClient(config).complete([{"role": "user", "content": "hi"}]))
        request, kwargs = urlopen.call_args.args[0], urlopen.call_args.kwargs
        self.assertEqual("http://llm.test/v1/chat/completions", request.full_url)
        self.assertEqual("Bearer k", request.get_header("Authorization"))
        self.assertEqual(7, kwargs["timeout"])
        body = json.loads(request.data)
        self.assertEqual("m", body["model"])
        self.assertEqual(0, body["temperature"])

    def test_omits_authorization_without_key(self):
        with mock.patch("urllib.request.urlopen", return_value=chat_reply("{}")) as urlopen:
            OpenAICompatibleClient(CONFIG).complete([])
        self.assertIsNone(urlopen.call_args.args[0].get_header("Authorization"))

    def test_transport_and_shape_errors_raise_semantic_mapper_error(self):
        failures = (
            urllib.error.URLError("down"),
            TimeoutError("slow"),
            urllib.error.HTTPError("http://llm.test", 500, "boom", {}, None),
        )
        for failure in failures:
            with self.subTest(failure=failure), mock.patch("urllib.request.urlopen", side_effect=failure):
                with self.assertRaises(SemanticMapperError):
                    OpenAICompatibleClient(CONFIG).complete([])
        for payload in (b"not json", b"{}", b'{"choices": [{"message": {"content": 3}}]}'):
            with self.subTest(payload=payload), mock.patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
                with self.assertRaises(SemanticMapperError):
                    OpenAICompatibleClient(CONFIG).complete([])

    def test_error_message_never_contains_the_key(self):
        config = LLMConfig(base_url="http://llm.test/v1", model="m", api_key="super-secret")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(SemanticMapperError) as ctx:
                OpenAICompatibleClient(config).complete([])
        self.assertNotIn("super-secret", str(ctx.exception))
        self.assertNotIn("super-secret", repr(config))

    def test_config_validation_and_env(self):
        with self.assertRaises(ValueError):
            LLMConfig(base_url="ftp://x", model="m")
        with self.assertRaises(ValueError):
            LLMConfig(base_url="http://x", model="")
        with self.assertRaises(ValueError):
            LLMConfig(base_url="http://x", model="m", timeout=0)
        env = {"ALCHEMIST_LLM_BASE_URL": "http://env.test/v1", "ALCHEMIST_LLM_MODEL": "env-model", "MY_KEY": "abc"}
        config = LLMConfig.resolve(api_key_env="MY_KEY", environ=env)
        self.assertEqual(("http://env.test/v1", "env-model", "abc"), (config.base_url, config.model, config.api_key))
        config = LLMConfig.resolve(base_url="http://flag.test", model="flag-model", environ=env)
        self.assertEqual(("http://flag.test", "flag-model", None), (config.base_url, config.model, config.api_key))
        with self.assertRaises(ValueError):
            LLMConfig.resolve(environ={})


class SemanticCliTests(unittest.TestCase):
    def run_main(self, *args, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", env or {}, clear=True), redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_semantic_flag_requires_endpoint(self):
        code, _, err = self.run_main("convert", "--semantic", "--from", "n8n", "--to", "ir", str(ROOT / "fixtures/n8n_linear.json"))
        self.assertEqual(2, code)
        self.assertIn("ALCHEMIST_LLM_BASE_URL", err)

    def test_semantic_convert_uses_configured_endpoint(self):
        reply = json.dumps({"nodes": [{"id": "2", "kind": "tool"}]})
        path = ROOT / "fixtures/n8n_custom.json"
        env = {"ALCHEMIST_LLM_BASE_URL": "http://llm.test/v1", "ALCHEMIST_LLM_MODEL": "m", "ALCHEMIST_LLM_API_KEY": "k"}
        with mock.patch("urllib.request.urlopen", return_value=chat_reply(reply)) as urlopen:
            code, out, err = self.run_main("convert", "--semantic", "--from", "n8n", "--to", "ir", str(path), env=env)
        self.assertEqual(0, code, err)
        self.assertEqual("tool", json.loads(out)["nodes"][1]["kind"])
        self.assertIn("SEMANTIC_APPROXIMATION", err)
        self.assertEqual("Bearer k", urlopen.call_args.args[0].get_header("Authorization"))

    def test_without_semantic_flag_no_request_is_made(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            code, out, _ = self.run_main("inspect", "--from", "n8n", str(ROOT / "fixtures/n8n_custom.json"), env={"ALCHEMIST_LLM_BASE_URL": "http://llm.test", "ALCHEMIST_LLM_MODEL": "m"})
        self.assertEqual(0, code)
        urlopen.assert_not_called()
        self.assertIn("UNSUPPORTED_NODE_TYPE", out)


if __name__ == "__main__":
    unittest.main()
