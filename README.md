# Micometeo

This repository holds the Epic 1 validation experiments for Micometeo. The
scope is in [the PRD](Micometeo_PRD_Epic_1_Validation_EN.md) and the status of
each assumption is in [docs/decisions.md](docs/decisions.md).

## Limits

- Each run may take at most 30 minutes. The runner stops it when the time is up
  and writes that in the run record.
- Experiments run on a laptop CPU only. No GPU.
- No purchases of domains, servers, paid APIs or subscriptions.

## Setup

1. Install [uv](https://docs.astral.sh/uv/).
2. Install the environment with `uv sync`.
3. Copy the login template with `cp .envrc.example .envrc`, fill in what an
   experiment needs and run `direnv allow`. Open-Meteo needs no login.
4. Install the secret scanner hook with `uv run pre-commit install`.

## Run an experiment

```
uv run micometeo run example
```

The example downloads one week of daily rain and temperature for Pistoia from
the Open-Meteo Historical Weather API and writes a small CSV file. Open-Meteo
data is licensed CC BY 4.0, and the free API is for non-commercial use only.

- The run record is `reports/runs/example/<run_id>.json`.
- The raw download is in `data/raw/example/`.
- The CSV summary is in `data/processed/example/<run_id>/`.

The command exits with 0 when the run completes and with a non-zero code when
it fails or runs out of time.

## Add an experiment

1. Create `experiments/<name>/`.
2. Add `config.toml` with `description`, `seed` and optionally
   `time_limit_minutes`. The default and the maximum are 30. Put your own
   values in a `[settings]` table.
3. Add `run.py` with `def run(context: RunContext) -> None`.
4. Run `uv run micometeo run <name>`.

The context gives you:

- `config`: the `[settings]` table.
- `seed`, `run_id`, `raw_dir` and `output_dir`. Python `random` is already
  seeded.
- `add_source(name, url, licence, version, downloaded_at, query)`: record every
  download.
- `add_input(path)`: record a file you read, with its hash and size.
- `add_output(path)`: record a file you wrote.

The record is also kept if the run is stopped, because each call saves to disk.

## Tests

```
uv run pytest
```

The tests use no network.
