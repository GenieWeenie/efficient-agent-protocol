import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from starter_packs.doc_ops import run_doc_ops
from starter_packs.local_etl import run_local_etl
from starter_packs.research_assistant import run_research_assistant


REPO_ROOT = Path(__file__).resolve().parents[2]


class StarterPacksIntegrationTest(unittest.TestCase):
    def test_research_assistant_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-starter-research-") as temp_dir:
            html_path = Path(temp_dir) / "source.html"
            html_path.write_text(
                (
                    "<html><body><h1>Launch Plan</h1>"
                    "<p>Risk: delayed onboarding</p>"
                    "<p>Risk: data quality drift</p>"
                    "</body></html>"
                ),
                encoding="utf-8",
            )
            result = run_research_assistant(
                question="list risks",
                html_file=str(html_path),
            )
            self.assertIn("Analysis complete.", result["answer"])
            self.assertIn("list risks", result["answer"])
            self.assertIn("run_id", result)
            self.assertIn("pointer_id", result)

    def test_doc_ops_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-starter-docops-") as temp_dir:
            input_path = Path(temp_dir) / "notes.md"
            output_path = Path(temp_dir) / "report.md"
            input_path.write_text("- Blockers: access provisioning\n- Next: tighten release checklist\n", encoding="utf-8")
            result = run_doc_ops(
                input_file=str(input_path),
                output_file=str(output_path),
                focus="summarize blockers and next actions",
            )
            self.assertTrue(output_path.exists())
            self.assertIn("Analysis complete.", result["report"])
            self.assertIn("summarize blockers and next actions", result["report"])

    def test_local_etl_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-starter-etl-") as temp_dir:
            input_path = Path(temp_dir) / "orders.jsonl"
            output_path = Path(temp_dir) / "aggregates.json"
            input_path.write_text(
                "\n".join(
                    [
                        '{"order_id":"1","region":"us","amount":100}',
                        '{"order_id":"2","region":"eu","amount":50.5}',
                        '{"order_id":"3","region":"us","amount":25}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = run_local_etl(
                input_file=str(input_path),
                output_file=str(output_path),
            )
            self.assertTrue(output_path.exists())
            self.assertEqual(result["metrics"]["record_count"], 3)
            self.assertEqual(result["metrics"]["total_amount"], 175.5)
            self.assertEqual(result["metrics"]["region_totals"]["us"], 125.0)
            self.assertEqual(result["metrics"]["region_totals"]["eu"], 50.5)

    def test_walkthrough_commands_are_runnable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-starter-cli-") as temp_dir:
            doc_ops_output = Path(temp_dir) / "doc_ops_report.md"
            etl_output = Path(temp_dir) / "etl_output.json"

            commands = [
                [
                    sys.executable,
                    "-m",
                    "starter_packs.research_assistant",
                    "--question",
                    "what risks are in this source?",
                    "--html-file",
                    "docs/starter_packs/fixtures/research_source.html",
                ],
                [
                    sys.executable,
                    "-m",
                    "starter_packs.doc_ops",
                    "--input-file",
                    "docs/starter_packs/fixtures/doc_ops_notes.md",
                    "--output-file",
                    str(doc_ops_output),
                    "--focus",
                    "summarize key actions",
                ],
                [
                    sys.executable,
                    "-m",
                    "starter_packs.local_etl",
                    "--input-file",
                    "docs/starter_packs/fixtures/local_etl_orders.jsonl",
                    "--output-file",
                    str(etl_output),
                ],
            ]

            for command in commands:
                completed = subprocess.run(
                    command,
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stdout + completed.stderr)
                payload = json.loads(completed.stdout)
                self.assertIn("run_id", payload)
                self.assertIn("pointer_id", payload)

            self.assertTrue(doc_ops_output.exists())
            self.assertTrue(etl_output.exists())


if __name__ == "__main__":
    unittest.main()
