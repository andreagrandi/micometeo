# Data

- `data/raw/` holds downloads exactly as received.
- `data/processed/` holds files the experiments derive from them.

Neither folder is committed. Every download must be recorded with
`context.add_source`, so the run record shows where the data came from, under
which licence and when it was downloaded.

`p2_layers.csv` lists every map layer of experiment P2 with provider, URL,
licence, version, download date, file format, coordinate system and stated
detail. `uv run micometeo run p2_habitat` rewrites it.

See `docs/data_formats.md` for file formats, IDs and date rules.
