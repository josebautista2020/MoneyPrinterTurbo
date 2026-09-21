# Content Studio AI — Tool and Connector Boundaries

The Supervisor selects tools by responsibility. Connectors are not part of the Content Studio domain model.

## Required control-plane capabilities

| Capability | Responsibility |
| --- | --- |
| GitHub connector | Repository inspection, branches, commits, issues, pull requests, CI evidence |
| Filesystem / shell | Local source inspection, deterministic scripts, test execution |
| Docker | Reproducible MoneyPrinterTurbo runtime and integration validation |
| Freebuff local executor | Optional local coding/terminal executor on the operator workstation; results require verifiable logs or GitHub evidence |

## Optional design/content capabilities

| Capability | Responsibility |
| --- | --- |
| Google Drive | Approved project documents/assets when needed |
| Figma | Brand/design artifacts when needed |

These tools are optional and must not become runtime dependencies of the reusable Core.

## Future publishing integrations

Publishing must use supported product APIs, for example the YouTube Data API and TikTok Content Posting API, behind a Content Studio publishing boundary.

MoneyPrinterTurbo direct auto-upload must remain disabled when invoked through Content Studio. Publication requires Safety, QA, and Human Review approval first.

## Security and cost rules

- Never commit API keys, OAuth tokens, cookies, or provider credentials.
- Use environment/secret stores appropriate to the execution environment.
- Paid media-generation calls require cost visibility before scale-out.
- Prefer deterministic local/unit validation before paid external generation.
- Do not add a connector merely because one exists; each connector requires a documented responsibility.
