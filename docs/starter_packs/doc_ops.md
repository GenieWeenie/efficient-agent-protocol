# Doc Ops Starter Pack

## Goal

Turn local notes into a concise report/action summary using:
- `read_local_file`
- `analyze_data`
- `write_local_file`

## Run

```bash
python -m starter_packs.doc_ops \
  --input-file docs/starter_packs/fixtures/doc_ops_notes.md \
  --output-file artifacts/starter_pack_doc_ops/report.md \
  --focus "summarize risks and next actions"
```

## Expected Result

- Command prints JSON with `output_file`, `report`, `run_id`, and `pointer_id`.
- Output file exists at `artifacts/starter_pack_doc_ops/report.md`.
- Output report contains `Analysis complete.`
