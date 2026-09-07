# `tn_districts.geojson`

Tamil Nadu district polygons for the dashboard map (`GET /api/knowledge/geo`).

| | |
|---|---|
| Source | <https://raw.githubusercontent.com/udit-001/india-maps-data/main/geojson/states/tamil-nadu.geojson> |
| Upstream basis | Census of India 2011 district boundaries, updated by the maintainer for the post-2019 Tamil Nadu district splits |
| Licence | MIT (upstream repository) |
| Downloaded | 2026-09-05 |
| Features | 37 |
| Size | ~105 KB (no simplification needed; already well under the 1.5 MB budget) |

Each feature carries:

* `name` — rewritten to match `name` in `backend/data/tn_districts.json` exactly,
  so the map can join to the weather snapshot without a lookup table;
* `source_district` — the spelling as published upstream;
* `dt_code` — the upstream district code;
* `st_nm` — always `"Tamil Nadu"`.

## Name rewrites applied

| Upstream `district` | `name` used here |
|---|---|
| Thiruvallur | Tiruvallur |
| Kanyakumari | Kanniyakumari |
| Nilgiris | The Nilgiris |
| Thoothukkudi | Thoothukudi |
| Thiruvarur | Tiruvarur |

All other upstream names already matched the official list on
<https://www.tn.gov.in/district_list.php>.

## Known gap: Mayiladuthurai

The official list has **38** districts; this file has **37**.
**Mayiladuthurai** was carved out of Nagapattinam in March 2020 and is not a
separate polygon upstream — its area is still inside the `Nagapattinam` polygon.

Consequences, and how the rest of the system stays honest about it:

* `backend/data/tn_districts.json` and the weather snapshot **do** include
  Mayiladuthurai with its own centroid and its own Open-Meteo series, so
  `check_weather` and `check_disasters` work normally for it.
* Only the *map* cannot draw it separately. A map colouring districts by rainfall
  will shade the combined Nagapattinam + Mayiladuthurai area using Nagapattinam's
  figures. Consumers that need to be precise should label that polygon
  "Nagapattinam (includes Mayiladuthurai)".
* No polygon was invented or split by hand — a guessed boundary would be worse
  than a documented gap.

The Tamil Nadu crop calendar has the same gap for a different reason: Table X of
the Season and Crop Report predates the split and carries no Mayiladuthurai row,
so `check_crop_window` returns `in_window = null` there rather than borrowing
Nagapattinam's windows.
