# Contributing to Breath View

Thank you for helping improve a privacy-sensitive, local-first project.

## Before opening a change

- Do not include real SD-card files, screenshots, serial numbers, symptoms,
  exported reports, access tokens or deployment credentials.
- Keep parser changes tied to reproducible format evidence. Update
  [FORMAT.md](FORMAT.md) when a field or boundary changes.
- Preserve the distinction between device data, software estimates and
  unknown values. Do not turn an estimate into a clinical claim without
  evidence from the manufacturer and an appropriate review.

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest -v
node --check web/i18n.js
node --check web/app.js
node --check web/report.js
```

Keep commits focused: public-release hygiene, behavior changes and generated
demo assets should be independently reviewable. Include the exact test command
and any data limitations in the pull request description.

## Pull requests

Explain the user-visible result, the input format assumptions, privacy impact,
and how the change was tested. Changes affecting reports or medical wording
need extra care: describe what remains unknown and avoid diagnostic language.
