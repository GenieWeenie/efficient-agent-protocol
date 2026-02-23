# Local ETL Starter Pack

## Goal

Aggregate local JSONL sales data into a compact metrics JSON using:
- `read_local_file`
- custom transform tool: `transform_sales_jsonl`
- `write_local_file`

## Run

```bash
python -m starter_packs.local_etl \
  --input-file docs/starter_packs/fixtures/local_etl_orders.jsonl \
  --output-file artifacts/starter_pack_local_etl/aggregates.json
```

## Expected Result

- Command prints JSON with `metrics`, `run_id`, and `pointer_id`.
- Output file exists at `artifacts/starter_pack_local_etl/aggregates.json`.
- Output JSON includes:
  - `record_count`
  - `total_amount`
  - `region_totals`
