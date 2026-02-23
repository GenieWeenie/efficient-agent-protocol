# Research Assistant Starter Pack

## Goal

Answer a focused question from a source HTML document using:
- `scrape_url`
- `analyze_data`

## Run

```bash
python -m starter_packs.research_assistant \
  --question "What risks are called out in the launch?" \
  --html-file docs/starter_packs/fixtures/research_source.html
```

## Expected Result

Command prints JSON with:
- `question`
- `source_url`
- `answer`
- `run_id`
- `pointer_id`

The `answer` field should include:
- `Analysis complete.`
- the focus question text
