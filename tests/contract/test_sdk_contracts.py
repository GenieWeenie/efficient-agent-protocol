import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class SDKContractCompatibilityTest(unittest.TestCase):
    def test_sdk_contract_doc_contains_required_operations(self) -> None:
        contract_path = REPO_ROOT / "docs" / "sdk_contract.md"
        self.assertTrue(contract_path.exists(), "docs/sdk_contract.md must exist")
        text = contract_path.read_text(encoding="utf-8")
        self.assertIn("Operation: `chat`", text)
        self.assertIn("Operation: `generate_macro`", text)
        self.assertIn("Operation: `execute_macro`", text)
        self.assertIn("Operation: `resume_run`", text)
        self.assertIn("Authorization: Bearer <api_key>", text)

    def test_typescript_sdk_exposes_required_types_and_methods(self) -> None:
        types_path = REPO_ROOT / "sdk" / "typescript" / "src" / "types.ts"
        client_path = REPO_ROOT / "sdk" / "typescript" / "src" / "client.ts"
        self.assertTrue(types_path.exists(), "TypeScript types.ts must exist")
        self.assertTrue(client_path.exists(), "TypeScript client.ts must exist")

        types_text = types_path.read_text(encoding="utf-8")
        client_text = client_path.read_text(encoding="utf-8")

        for token in [
            "interface ChatRequest",
            "interface GenerateMacroRequest",
            "interface ExecuteMacroRequest",
            "interface BatchedMacroRequest",
            "interface ResumeRunRequest",
        ]:
            self.assertIn(token, types_text)

        for token in [
            "async chat(",
            "async generateMacro(",
            "async executeMacro(",
            "async resumeRun(",
            "/v1/eap/chat",
            "/v1/eap/macro/generate",
            "/v1/eap/macro/execute",
            "/v1/eap/runs/",
        ]:
            self.assertIn(token, client_text)

    def test_go_sdk_exposes_required_structs_and_methods(self) -> None:
        types_path = REPO_ROOT / "sdk" / "go" / "types.go"
        client_path = REPO_ROOT / "sdk" / "go" / "client.go"
        self.assertTrue(types_path.exists(), "Go types.go must exist")
        self.assertTrue(client_path.exists(), "Go client.go must exist")

        types_text = types_path.read_text(encoding="utf-8")
        client_text = client_path.read_text(encoding="utf-8")

        for token in [
            "type ChatRequest struct",
            "type GenerateMacroRequest struct",
            "type ExecuteMacroRequest struct",
            "type BatchedMacroRequest struct",
            "type ResumeRunRequest struct",
            '`json:"request_id"`',
            '`json:"timestamp_utc"`',
        ]:
            self.assertIn(token, types_text)

        for token in [
            "func (c *Client) Chat(",
            "func (c *Client) GenerateMacro(",
            "func (c *Client) ExecuteMacro(",
            "func (c *Client) ResumeRun(",
            '"/v1/eap/chat"',
            '"/v1/eap/macro/generate"',
            '"/v1/eap/macro/execute"',
            '"/v1/eap/runs/"',
        ]:
            self.assertIn(token, client_text)

    def test_endpoint_paths_are_consistent_across_sdks(self) -> None:
        ts_client = (REPO_ROOT / "sdk" / "typescript" / "src" / "client.ts").read_text(
            encoding="utf-8"
        )
        go_client = (REPO_ROOT / "sdk" / "go" / "client.go").read_text(encoding="utf-8")

        ts_paths = set(re.findall(r'"/v1/eap/[^"]+"', ts_client))
        go_paths = set(re.findall(r'"/v1/eap/[^"]+"', go_client))

        expected = {
            '"/v1/eap/chat"',
            '"/v1/eap/macro/generate"',
            '"/v1/eap/macro/execute"',
        }
        self.assertTrue(expected.issubset(ts_paths))
        self.assertTrue(expected.issubset(go_paths))
        self.assertIn("/v1/eap/runs/", ts_client)
        self.assertIn("/v1/eap/runs/", go_client)


if __name__ == "__main__":
    unittest.main()
