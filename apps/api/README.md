# SporaMeteo demo API

This is a small local API for the phone map page. It serves made-up scores for
500 m grid squares in the Pistoia province and the Apennines. The scores do not
describe real mushrooms or real weather. Every JSON body says so in the fields
`demo_data` and `notice`.

The API uses only the Python standard library. It needs Python 3.14.

## Run locally

```bash
cd apps/api
python3.14 -m sporameteo_api
```

The server listens on `127.0.0.1:8080`. Set `SPORAMETEO_API_HOST` and
`SPORAMETEO_API_PORT` to change this.

## Run in Docker

```bash
docker build -t sporameteo-api:p5 apps/api
docker run --rm -p 8080:8080 sporameteo-api:p5
```

The container listens on `0.0.0.0:8080` and runs as a user without root rights.

## Grid file

`sporameteo_api/demo_grid.json.gz` holds the squares as gzipped JSON. Recreate it with:

```bash
uv run python apps/api/tools/make_demo_grid.py
```

The file has every 500 m square of EPSG:3035 whose centre lies inside the box
west 10.62, south 43.72, east 11.05, north 44.18. That is about 7,000 squares.
Square IDs follow `docs/data_formats.md`, for example `500m_E4371000_N2290500`.

## Headers

Every response carries:

- `Content-Type: application/json; charset=utf-8`
- `X-Demo-Data: true`
- `Access-Control-Allow-Origin: *`
- `Vary: Accept-Encoding`

The body is gzipped when the request header `Accept-Encoding` contains `gzip`.
Then the response also has `Content-Encoding: gzip`. The info and squares
responses have `Cache-Control: public, max-age=300`.

## Addresses

### GET /api/v1/health

Checks that the API answers. No parameters.

```bash
curl http://127.0.0.1:8080/api/v1/health
```

```json
{"demo_data":true,"notice":"Made-up demo data. These scores do not describe real mushrooms or real weather.","status":"ok"}
```

### GET /api/v1/info

Lists the species, the days you can ask for and the limits. No parameters.
The field `assessment_dates` holds the 14 days ending today in Italian time,
newest first.

```bash
curl http://127.0.0.1:8080/api/v1/info
```

```json
{
  "demo_data": true,
  "notice": "Made-up demo data. These scores do not describe real mushrooms or real weather.",
  "species": [
    {"id": "porcini", "name": "Porcini", "scientific_names": ["Boletus edulis", "Boletus aereus", "Boletus reticulatus", "Boletus pinophilus"]},
    {"id": "ovolo", "name": "Ovolo", "scientific_names": ["Amanita caesarea"]}
  ],
  "assessment_dates": ["2026-10-11", "2026-10-10", "...", "2026-09-28"],
  "max_days_ahead": 7,
  "area": {"west": 10.62, "south": 43.72, "east": 11.05, "north": 44.18},
  "max_squares_per_request": 4000,
  "min_zoom": 11
}
```

### GET /api/v1/squares

Returns the squares that overlap a map box, as a GeoJSON FeatureCollection.

| Parameter | Meaning |
|---|---|
| species | `porcini` or `ovolo`. |
| assessment_date | The day the score is made, `YYYY-MM-DD`. It must be one of `assessment_dates` from the info address. |
| target_date | The day the score is for, `YYYY-MM-DD`. It is the assessment date or up to 7 days later. |
| bbox | `west,south,east,north` in WGS84 degrees. A square matches when its bounds overlap the box. |

A request matches at most 4,000 squares. Zoom in if you get more.

```bash
curl "http://127.0.0.1:8080/api/v1/squares?species=porcini&assessment_date=2026-10-11&target_date=2026-10-12&bbox=10.85,43.90,10.98,44.05"
```

The example response below is cut to one square.

```json
{
  "demo_data": true,
  "notice": "Made-up demo data. These scores do not describe real mushrooms or real weather.",
  "type": "FeatureCollection",
  "species": "porcini",
  "assessment_date": "2026-10-11",
  "target_date": "2026-10-12",
  "days_ahead": 1,
  "square_count": 1,
  "features": [
    {
      "type": "Feature",
      "id": "500m_E4371000_N2290500",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[10.61899, 43.72178], [10.62518, 43.72174], [10.62523, 43.72625], [10.61904, 43.72629], [10.61899, 43.72178]]]
      },
      "properties": {
        "cell_id": "500m_E4371000_N2290500",
        "species": "porcini",
        "assessment_date": "2026-10-11",
        "target_date": "2026-10-12",
        "days_ahead": 1,
        "score_type": "forecast",
        "score": 49,
        "reliability": "high",
        "sources": ["Made-up demo weather", "Made-up demo habitat"],
        "demo_data": true
      }
    }
  ]
}
```

Properties:

- `score` is a whole number from 0 to 100. It is made up from the square
  position, the species and the target date. The same request always gives the
  same score. Neighbouring squares get similar scores.
- `score_type` is `conditions_today` when `days_ahead` is 0, otherwise
  `forecast`.
- `reliability` is `high` for 0 to 2 days ahead, `medium` for 3 to 5 and `low`
  for 6 and 7.

## Errors

Errors are JSON with a plain sentence, plus `demo_data` and `notice`.

```json
{"demo_data":true,"notice":"Made-up demo data. These scores do not describe real mushrooms or real weather.","error":"The parameter bbox must be four numbers: west,south,east,north."}
```

| Status | When |
|---|---|
| 400 | A parameter is missing or wrong, or the box matches more than 4,000 squares. |
| 404 | The address does not exist. |
| 405 | The method is not GET or OPTIONS. The `Allow` header lists the methods. |

OPTIONS answers with 204 and the CORS headers `Access-Control-Allow-Methods:
GET, OPTIONS` and `Access-Control-Allow-Headers: Content-Type`.
