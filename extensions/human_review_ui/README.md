# Human Review UI

Standalone Streamlit review surface for Content Studio AI.

Run:

```bash
uv run streamlit run extensions/human_review_ui/app.py
```

The UI loads a canonical `ReviewPackage` JSON and displays:

- final render preview
- Safety findings and modality coverage
- Render QA checks
- review eligibility
- shot IDs available for targeted regeneration
- append-only audit history

Human actions:

- approve
- reject
- regenerate one shot
- regenerate the episode

Approval does **not** publish. Decisions are appended as JSONL under
`output/content_studio/review_audit/` by default. Set
`CONTENT_STUDIO_REVIEW_LOG_DIR` to choose another local audit directory.

The application never calls MoneyPrinterTurbo cross-posting services.
