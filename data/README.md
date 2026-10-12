# Data

- `data/raw/` holds downloads exactly as received.
- `data/processed/` holds files the experiments derive from them.

Neither folder is committed. Experiment downloads use `context.add_source`,
so the run record shows where the data came from, under which licence and when
it was downloaded. Application builds store the same source information with
their versioned build in PostGIS.

The national grid reads the original ISTAT archive from
`data/raw/mvp_boundaries/`. Its build records the archive checksum, selected
region file, source version, retrieval date, licence and attribution. Product
grid geometry does not use the GADM files retained for historical experiments.

The national terrain command caches Copernicus GLO-30 tiles and checksum
sidecars in `data/raw/mvp_terrain/`. PostGIS stores the terrain values and
links each completed chunk to its source tiles. The committed
`reports/mvp/terrain_coverage.md` records coverage and the required credit.

`p2_layers.csv` lists every map layer of experiment P2 with provider, URL,
licence, version, download date, file format, coordinate system and stated
detail. `uv run micometeo run p2_habitat` rewrites it.

See `docs/data_formats.md` for file formats, IDs and date rules.
