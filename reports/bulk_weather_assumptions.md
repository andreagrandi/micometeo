# How the Open-Meteo API builds our weather values

Issue #124, part of epic #123.

## Question

How does the Open-Meteo API build the five weather values we use, and can each
of them be built from the files in `s3://openmeteo`?

## Answer

Yes. All five values can be built from the `data/ecmwf_ifs/` files. Four are
stored as they are. Evapotranspiration is calculated at request time from four
stored values and the place's elevation, so we must calculate it ourselves. No
variable is missing, so the epic does not need to stop.

Six findings change how the next issues should work:

1. For past days the app calls the archive API with `best_match`. That model
   reads the same `ecmwf_ifs` files first and fills gaps from ERA5-Land and
   ERA5. File weather for past days should match the API closely.
2. For today and the days ahead, `best_match` in Italy uses German ICON models
   first, not the Italian ICON-2I model. ICON-D2 at 2 km covers only places
   from latitude 43.18 north. Places further south start with ICON-EU at 7 km.
   File weather will differ from the API for rain, temperature and
   evapotranspiration on these days.
3. Soil moisture and soil temperature in `best_match` come from the same IFS
   model as the files on every day, because the ICON models store other soil
   layers.
4. The API does not always pick the nearest grid point. With
   `cell_selection=land`, which the app sends, it looks at the 9 nearest
   points and may pick one whose height is closer to the place.
5. The API corrects temperature, dew point and soil temperature by 0.65 °C per
   100 m between the grid point's height and the place's height. A file reader
   must do the same, or file and API values will differ by more than rounding.
6. Two programs write the `data/ecmwf_ifs/` files: an archive loader and a live
   forecast loader. Recent past hours may change after a day ends. The code
   does not say which program wrote which dates.

Source code read: `open-meteo/open-meteo` at commit
[`b0ff3eb`][commit], 15 October 2026. Documentation read:
`open-meteo/open-data` at commit `4fd52ad`, 25 July 2025. No weather file was
downloaded and no API call was made.

## What the app asks for

The app asks for five hourly values in `src/sporameteo/weather/openmeteo.py`:
`precipitation`, `temperature_2m`, `soil_moisture_0_to_7cm`,
`soil_temperature_0_to_7cm` and `et0_fao_evapotranspiration`.

`apps/application/weather_requests/planning.py` sends every request with
`models=best_match` and `cell_selection=land`, and without an elevation. It
sends the 30 completed days to the archive API and today with the 7 days ahead
to the forecast API.

## AC1: the evapotranspiration formula

The API calculates `et0_fao_evapotranspiration` for each hour with the hourly
FAO-56 formula of the UN Food and Agriculture Organization, equation 53. The
code is in [`FaoEvapotranspiration.swift`, lines 155 to 211][et0-formula]. The
call that feeds it is in [`VariableHourly.swift`, lines 1468 to 1483][et0-call].

Inputs:

| Input | Where it comes from |
|---|---|
| Air temperature at 2 m, °C | stored `temperature_2m`, after the height correction |
| Dew point at 2 m, °C | stored `dew_point_2m`, after the height correction |
| Solar radiation, W/m², average of the past hour | stored `shortwave_radiation` |
| Wind speed at 10 m, m/s | built from `wind_u_component_10m` and `wind_v_component_10m` |
| Elevation, m | the place's height from the Copernicus 90 m elevation model |
| Solar radiation at the top of the atmosphere | calculated for the grid point's latitude and longitude and the hour, in [`Zensun.swift`, line 295][exrad] |
| Time step | 3,600 seconds |

Choices in the code that our own function must copy:

- Wind at 10 m is scaled to 2 m by `4.87 / ln(67.8 z - 5.42)`, which gives a
  factor of about 0.748. See [`Meteorology.swift`, lines 231 to 235][wind-scale].
- Saturation vapour pressure uses 17.27 and 237.3, the FAO values.
- Air pressure comes from the elevation alone: `101.3 * ((293 - 0.0065 z) / 293) ^ 5.26`.
- Albedo is 0.23.
- Clear-sky radiation is `(0.75 + 0.00002 z)` times the top-of-atmosphere
  radiation.
- When the top-of-atmosphere radiation is zero, at night, the ratio of actual to
  clear-sky radiation is guessed from relative humidity as `0.8 - 0.4 * RH`.
  FAO-56 instead carries the ratio from the hours before sunset. See
  [line 14][et0-night].
- Heat going into the soil is 10 percent of net radiation when the sun shines
  and 50 percent when it does not, at [line 204][et0-soil-heat].
- Negative results become 0, at [line 210][et0-clip].

The API calculates evapotranspiration for each model separately and then joins
the models. On a day where `best_match` uses ICON-D2, the evapotranspiration
comes from ICON-D2 temperature, dew point, radiation and wind.

## AC2: how a place is matched to an `ecmwf_ifs` grid point

The `ecmwf_ifs` files use ECMWF's O1280 grid, at [`EcmwfEcpdsDomain.swift`,
line 83][ecpds-grid]. Each latitude row has `20 + 4 y` points, counted from the
pole. The files store the grid as one long list of points, row after row.

### Latitude and longitude of a grid point

[`GaussianGrid.swift`, lines 150 to 157][grid-coords] gives each point:

- row spacing `dy = 180 / (2 * 1280 + 0.5)` degrees
- latitude `(1280 - y - 1) * dy + dy / 2`
- longitude `x * 360 / nx`, moved to minus 180 to 180

These latitudes are evenly spaced. The true O1280 latitudes are not quite
evenly spaced. A reader must use this formula, not a library's exact grid, or
it may pick a different row from the API.

### Choice of grid point

1. The API reads the place's height from the Copernicus 90 m elevation model at
   the requested latitude and longitude, because the app sends no elevation.
   See [`ForecastapiQuery.swift`, lines 652 to 668][dem-default] and
   [`DownloadDem.swift`, lines 52 to 67][dem-read].
2. `cell_selection=land` selects the height-aware search, at
   [`Gridable.swift`, lines 89 to 108][grid-mode].
3. The API lists the 3 by 3 grid points around the place and finds the
   nearest one, at [`GaussianGrid.swift`, lines 214 to 250][grid-3x3].
   Distance is measured in degrees, with no correction for latitude.
4. If the nearest point's height is within 100 m of the place's height, the API
   uses it, at [line 323][grid-close].
5. Otherwise it scores each land point as the height difference plus 30 m for
   each km of distance, with one degree counted as 111 km. It picks the lowest
   score. If every score is above 1,500, it keeps the nearest point. See
   [lines 314 to 357][grid-land].

Grid point heights come from `data/ecmwf_ifs/static/HSURF.om`, at
[`GenericDomain.swift`, line 88][hsurf]. Sea points have a height of -999 or
less and are skipped. Place heights come from
`data/copernicus_dem90/static/lat_<whole degree>.om`.

### Height correction

The API then corrects `temperature_2m`, `dew_point_2m` and
`soil_temperature_0_to_7cm` by `(grid point height - place height) * 0.0065`
°C. See [`GenericReader.swift`, lines 190 to 201][lapse] and the variable lists
in [`Era5Variables.swift`, lines 399 to 403][lapse-era5] and
[`EcmwfEcpdsVariable.swift`, lines 312 to 316][lapse-ecpds].

In step 4 the code records the place's own height as the grid point height. The
correction is then zero. So the correction applies only when the two heights
differ by more than 100 m.

The API answer's `latitude` and `longitude` are those of the grid point it
used. Its `elevation` is the place's height. The app already stores both, as
`returned_latitude`, `returned_longitude` and `elevation_m`.

## AC3: which model `best_match` uses in Italy

Two different `best_match` models exist. The archive API defaults to
`archive_best_match` and the forecast API to `best_match`, in
[`ForecastapiController.swift`, lines 8 to 21][routes].

### Past days, archive API

This is what the app uses for the 30 completed days.
[`ForecastapiController.swift`, lines 1286 to 1294][archive-best] mixes three
stored datasets hour by hour before it calculates anything:

1. `ecmwf_ifs`, 9 km, used first
2. ERA5-Land, reconstructed past weather at about 11 km, for hours `ecmwf_ifs`
   lacks
3. ERA5, reconstructed past weather at about 25 km, for hours both lack

[Lines 1003 to 1052][mix-group] show the mix. The grid point, its height and
the evapotranspiration all use the `ecmwf_ifs` grid. When one dataset hands
over to the next, [`GenericReaderMixerRaw.swift`, lines 143 to 151][smooth]
blends the values over 3 hours.

This holds for all of Italy.

### Past days, forecast API

The app does not use this path. With `past_days`, the forecast API uses the
same model order as for today, described below. It reads the older hours of
the same files.

### Today and the days ahead, forecast API

[`ForecastapiController.swift`, lines 1915 to 2105][forecast-best] picks models
by place. For Italy, two branches apply. The first is used when the place lies
on the ICON-D2 grid, which starts at latitude 43.18 and runs from longitude
-3.94 to 20.34, at [`Icon.swift`, line 215][icon-d2-grid]. The second is used
further south.

North of latitude 43.18, which covers most of Tuscany:

| Days ahead | Rain, temperature, evapotranspiration | Soil moisture and soil temperature |
|---|---|---|
| Today and tomorrow, up to 2 days from the latest run | ICON-D2, 2 km, German | IFS, 9 km |
| Up to 5 days | ICON-EU, 7 km, German | IFS, 9 km |
| Up to 7.5 days | ICON, 11 km, German | IFS, 9 km |
| Later hours, up to day 7 | IFS, 9 km | IFS, 9 km |

South of latitude 43.18, which covers southern Tuscany, the south and the
islands:

| Days ahead | Rain, temperature, evapotranspiration | Soil moisture and soil temperature |
|---|---|---|
| Up to 5 days | ICON-EU, 7 km | IFS, 9 km |
| Up to 7.5 days | ICON, 11 km | IFS, 9 km |
| Later hours, up to day 7 | IFS, 9 km | IFS, 9 km |

The day limits are the forecast lengths in the `open-data` documentation. They
count from each model's latest run, not from midnight. GFS sits below IFS but is
not reached within 7 days.

Rules behind the tables:

- The highest model with a value for an hour wins. When it runs out, the next
  one takes over, blended over 3 hours. See [`GenericReaderMulti.swift`,
  lines 136 to 160][multi].
- ICON models store soil moisture at 0 to 1 cm, 1 to 3 cm and 3 to 9 cm, and
  soil temperature at 0, 6 and 18 cm, in [`IconVariable.swift`, lines 121 to
  132][icon-soil]. They have no 0 to 7 cm layer, and the API does not build one
  from them. So both soil values come from IFS, the model of the
  `ecmwf_ifs` files.
- The Italian ICON-2I model, `italia_meteo_arpae_icon_2i`, appears only as its
  own model. `best_match` never uses it.
- The answer's `latitude` and `longitude` come from the highest model, ICON-D2
  or ICON-EU. They are not the `ecmwf_ifs` grid point.

The southern edge of ICON-D2 comes from its regular grid. The code also loads an
ICON-D2 native grid file that is not in the repository. Its exact edge is
unknown, so places near latitude 43.18 may fall on either side.

## AC4: stored file variables behind each of our values

Both writers of `data/ecmwf_ifs/` store these names. See the forecast loader's
list in [`EcmwfEcpdsVariable.swift`][ecpds-vars] and the archive list in
[`Era5Variables.swift`][era5-vars].

| Our value | Stored file variables | What the API does |
|---|---|---|
| `precipitation` | `precipitation` | reads it as it is, mm in the past hour |
| `temperature_2m` | `temperature_2m` | height correction |
| `soil_moisture_0_to_7cm` | `soil_moisture_0_to_7cm` | reads it as it is, m³/m³ |
| `soil_temperature_0_to_7cm` | `soil_temperature_0_to_7cm` | height correction |
| `et0_fao_evapotranspiration` | `temperature_2m`, `dew_point_2m`, `shortwave_radiation`, `wind_u_component_10m`, `wind_v_component_10m` | FAO-56 hourly formula above, with the place's height and the grid point's latitude and longitude |

Wind speed is `sqrt(u * u + v * v)` at 10 m, in [`Meteorology.swift`, lines 6
to 8][wind-speed], called through [`DerivedMapping.swift`, lines 65 to
79][wind-map] from [`VariableHourly.swift`, line 1236][wind-call].
Radiation is read as stored, because `ecmwf_ifs` has no radiation scale factor
in [`VariableHourly.swift`, lines 703 to 707][ifs-compat].

The files also hold `potential_evapotranspiration`. That is ECMWF's own value,
not the FAO-56 value, and the API does not use it for
`et0_fao_evapotranspiration`.

To match points, a reader also needs two static files:
`data/ecmwf_ifs/static/HSURF.om` and the Copernicus 90 m elevation files.

### Who writes `data/ecmwf_ifs/`

Both programs map to the same folder, through [`DomainRegistry.swift`, line
305][registry] and [`Era5Domain.swift`, line 86][era5-registry]:

- The live forecast loader in [`EcmwfEcpdsDomain.swift`][ecpds-grid] gets 4
  runs a day. The 00 and 12 UTC runs reach 360 hours ahead. The 06 and 18 UTC
  runs reach 144 hours, as [lines 12 to 18][ecpds-steps] show. It updates every
  6 hours.
- The archive loader in [`DownloadEra5Command.swift`, lines 486 to
  496][mars] takes hours 1 to 12 of the 00 and 12 UTC runs from ECMWF's archive.
  It updates every 24 hours.

The `open-data` README still lists `ecmwf_ifs` only as a past-weather model,
2 days behind and updated every 24 hours. It was last changed in July 2025 and
does not describe the forecast loader.

## AC5: assumptions in the other issues of this epic

### Hold

- #123: the files can replace the API for our values. All five can be built
  from stored variables.
- #123: the files do not hold FAO-56 evapotranspiration, so we must calculate
  it.
- #123: `ecmwf_ifs` is hourly, about 9 km, and updated every 6 hours with up to
  15 days ahead. The forecast loader code agrees. The README does not, because
  it is out of date.
- #123: a wrong grid match gives believable values with no error. The
  height-aware choice makes this a real risk.
- #125 step 1: the grid is O1280 with a different number of points per row.
- #125 step 2: every listed variable exists in the files.
- #125 steps 2 and 4: `models=ecmwf_ifs` in the forecast API reads only these
  files, at [`ForecastapiController.swift`, line 1264][ifs-model]. File and API
  values for the 20 cells should agree once the height correction is applied.
- #126: the inputs listed are the ones the API uses.
- #126: the elevation the app stores is the place height the API uses. It is
  the `elevation` field of each answer.
- #127 step 4: ICON-2I has no 0 to 7 cm soil layer, so soil must come from
  `ecmwf_ifs`. `best_match` does the same.

### Fail

- #127: `best_match` does not use an Italian 2 km model. It uses the German
  ICON-D2 at 2 km for about 2 days, and only north of latitude 43.18. South of
  it, the first model is ICON-EU at 7 km. Comparing ICON-2I in step 4 tests an
  option that `best_match` does not use.
- #125 step 1, if read as nearest point: the API picks among 9 points by height
  as well as distance. The match needs the place's height from the Copernicus
  90 m files and the grid heights from `HSURF.om`.
- #125 step 1, if read as exact grid latitudes: the API uses evenly spaced
  latitudes.
- #125 stop rule, without a height correction: temperature, dew point and soil
  temperature will differ from the API by more than rounding whenever the two
  heights differ by more than 100 m. The reader must apply the correction
  before this rule is checked.
- #126 AC1, at night: the API does not follow FAO-56 at night. It guesses the
  radiation ratio from humidity. The function can match the FAO-56 daytime
  examples and the API, but not both at night. It also needs the grid point's
  latitude and longitude for the sun's position.

### Still unknown

- #125 AC4 and #128: which loader wrote which dates in the files, and when a
  past hour stops changing. Hours of a completed day may first hold the start
  of a forecast run. The archive loader may later replace them, about 2 days
  after the day ends. The archive API reads the same files, so yesterday's
  archive values may also change.
- #125 AC4: whether days 6 and 7 ahead are complete after a 06 or 18 UTC run.
  These runs stop at 144 hours. The code does not show whether the later hours
  keep values from the previous 00 or 12 UTC run.
- #127: how large the gap between file and API weather is for days ahead. Soil
  should match. Rain, temperature and evapotranspiration will differ for the
  first 5 to 7 days, because ICON models supply them.
- #128 AC2: whether a file's modification time is available over HTTPS without
  an AWS account. The code does not cover this.
- The exact southern edge of ICON-D2 in Italy.

[commit]: https://github.com/open-meteo/open-meteo/tree/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4
[et0-formula]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/FaoEvapotranspiration.swift#L155-L211
[et0-night]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/FaoEvapotranspiration.swift#L14-L17
[et0-soil-heat]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/FaoEvapotranspiration.swift#L204
[et0-clip]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/FaoEvapotranspiration.swift#L210
[et0-call]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Controllers/VariableHourly.swift#L1468-L1483
[exrad]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/Solar/Zensun.swift#L295
[wind-scale]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/Meteorology.swift#L231-L235
[wind-speed]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/Meteorology.swift#L6-L8
[wind-map]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/Reader/DerivedMapping.swift#L65-L79
[wind-call]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Controllers/VariableHourly.swift#L1235-L1236
[ifs-compat]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Controllers/VariableHourly.swift#L703-L707
[grid-coords]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Domains/GaussianGrid.swift#L150-L157
[grid-3x3]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Domains/GaussianGrid.swift#L214-L250
[grid-close]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Domains/GaussianGrid.swift#L323-L325
[grid-land]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Domains/GaussianGrid.swift#L314-L357
[grid-mode]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Domains/Gridable.swift#L89-L108
[hsurf]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/Reader/GenericDomain.swift#L86-L91
[dem-default]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/ForecastapiQuery.swift#L652-L668
[dem-read]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Dem/DownloadDem.swift#L52-L67
[lapse]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/Reader/GenericReader.swift#L190-L201
[lapse-era5]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Era5/Era5Variables.swift#L399-L403
[lapse-ecpds]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/EcmwfEcpds/EcmwfEcpdsVariable.swift#L312-L316
[routes]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Controllers/ForecastapiController.swift#L8-L21
[ifs-model]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Controllers/ForecastapiController.swift#L1264-L1265
[archive-best]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Controllers/ForecastapiController.swift#L1286-L1294
[mix-group]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Controllers/ForecastapiController.swift#L1003-L1052
[forecast-best]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Controllers/ForecastapiController.swift#L1915-L2105
[smooth]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/Reader/GenericReaderMixerRaw.swift#L143-L151
[multi]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/Reader/GenericReaderMulti.swift#L136-L160
[icon-d2-grid]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Icon/Icon.swift#L214-L215
[icon-soil]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Icon/IconVariable.swift#L121-L132
[ecpds-vars]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/EcmwfEcpds/EcmwfEcpdsVariable.swift#L1-L60
[era5-vars]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Era5/Era5Variables.swift#L1-L60
[ecpds-grid]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/EcmwfEcpds/EcmwfEcpdsDomain.swift#L74-L84
[ecpds-steps]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/EcmwfEcpds/EcmwfEcpdsDomain.swift#L12-L18
[mars]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Era5/DownloadEra5Command.swift#L486-L496
[registry]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Helper/DomainRegistry.swift#L305-L306
[era5-registry]: https://github.com/open-meteo/open-meteo/blob/b0ff3ebbbafa890000ab8bc5f9598a2e4ef64dc4/Sources/App/Era5/Era5Domain.swift#L86-L87
