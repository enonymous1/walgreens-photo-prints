# Contributing

## Development setup

See `README.md` (Local Development): create a virtual environment,
`pip install -e ".[dev]"`, then `pytest`, `ruff check src tests`,
and `ruff format --check src tests`. All tests use mocked responses;
no test touches the live API.

## Rules for changes

- Never add a credential, a real API key, a SAS URL, or customer
  data to code, tests, fixtures, screenshots, or documentation.
  Fixtures use fictional values such as `example.test`.
- Never sort API collections: their order is meaningful (see the
  models module docstring).
- Never add an automatic retry to `submit_order`: it is not
  idempotent, and retrying after a timeout could place an order
  twice.
- Keep the version in one place only:
  `src/walgreens_photo_prints/_version.py`. `pyproject.toml`
  reads it dynamically; do not duplicate the string.
- Keep `CHANGELOG.md` current: one entry per release, describing
  behaviour changes and any still-unverified live behaviour.

## Release checklist

1. Bump `_version.py` and add a `CHANGELOG.md` entry.
2. Run the full suite and lint from a fresh extraction in a fresh
   virtual environment.
3. Push, confirm the GitHub Actions matrix (Python 3.10–3.13,
   Ubuntu and Windows) is green.
4. Run the sandbox smoke test with a fresh key (credentials,
   products, store search, then submit and status).
5. Tag the release version and create the GitHub Release.

## Visual assets

- `docs/assets/architecture.svg` and `docs/assets/order-flow.svg`
  are the repository diagrams. Keep their labels single-line and
  their text fictional; do not embed keys or real order data.
- A CLI demo GIF (`docs/assets/cli-demo.gif`) may be added only
  from a real terminal recording with fictional values, showing
  `--help`, a redacted submit preview, and the test suite.
- A CI screenshot (`docs/assets/ci.png`) may be added only after
  a real green GitHub Actions run, captioned with the commit it
  ran on. Never fake either asset.
