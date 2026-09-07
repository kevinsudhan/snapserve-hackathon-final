"""SIMULATED Tamil Nadu Kharif 2026 sum-insured notification.

Kevin's decision (2026-09-05): the real district notification with per-crop sum
insured could not be sourced online, so a clearly labelled *simulated* notification
is generated instead.  Every figure here is synthetic and the document served to the
CRM says so on every page.  The generator is deterministic so citations stay stable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from services.schemes_models import Citation, SchemeMatch

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "sum_insured_simulated.json"
DOC_ID = "tn-kharif-2026-sum-insured"
DOC_URL = f"http://localhost:8010/api/knowledge/documents/{DOC_ID}"
CITATION_ID = "N1"
AS_OF = "2026-07-08"
TITLE = "Tamil Nadu Kharif 2026 crop insurance notification — sum insured per hectare (SIMULATED for demonstration)"
PUBLISHER = "Araxys Desk demo (simulated; not an official notification)"

# Base sum insured per hectare in rupees (synthetic, plausible for Tamil Nadu).
BASE_RATES: dict[str, int] = {
    "paddy": 62000, "groundnut": 46000, "sugarcane": 110000, "cotton": 52000,
    "maize": 38000, "black_gram": 26000, "green_gram": 25000, "red_gram": 32000,
    "banana": 165000, "turmeric": 130000, "chilli": 75000, "tomato": 70000,
    "onion": 65000, "coconut": 90000, "ragi": 28000, "bajra": 24000,
    "jowar": 24000, "sesame": 22000, "tapioca": 80000, "brinjal": 60000,
    "okra": 55000, "mango": 95000,
}
CROP_LABELS: dict[str, str] = {
    "paddy": "Paddy (nel)", "groundnut": "Groundnut (verkadalai)", "sugarcane": "Sugarcane (karumbu)",
    "cotton": "Cotton (paruthi)", "maize": "Maize (makkacholam)", "black_gram": "Black gram (ulundu)",
    "green_gram": "Green gram (pachai payaru)", "red_gram": "Red gram (thuvarai)", "banana": "Banana (vazhai)",
    "turmeric": "Turmeric (manjal)", "chilli": "Chilli (milagai)", "tomato": "Tomato (thakkali)",
    "onion": "Onion (vengayam)", "coconut": "Coconut (thennai)", "ragi": "Ragi (kezhvaragu)",
    "bajra": "Bajra (kambu)", "jowar": "Jowar (cholam)", "sesame": "Sesame (ellu)",
    "tapioca": "Tapioca (maravalli)", "brinjal": "Brinjal (kathirikkai)", "okra": "Okra (vendakkai)",
    "mango": "Mango (maa)",
}
CUT_OFF = {"paddy": "2026-09-15", "sugarcane": "2026-08-31", "banana": "2026-08-31", "turmeric": "2026-08-15"}
DEFAULT_CUT_OFF = "2026-07-31"


def _factor(district: str, crop: str) -> float:
    h = int(hashlib.sha1(f"{district}|{crop}".encode()).hexdigest()[:6], 16)
    return 0.90 + (h % 2001) / 10000.0  # 0.90 .. 1.10


def _round500(x: float) -> int:
    return int(round(x / 500.0) * 500)


def generate(districts: list[str]) -> dict:
    rows = []
    for d in sorted(districts):
        for crop, base in BASE_RATES.items():
            rows.append({
                "district": d,
                "crop": crop,
                "crop_label": CROP_LABELS.get(crop, crop),
                "sum_insured_per_ha": _round500(base * _factor(d, crop)),
                "farmer_premium_pct": 5.0 if crop in {"banana", "turmeric", "chilli", "tomato", "onion", "coconut", "tapioca", "brinjal", "okra", "mango", "sugarcane", "cotton"} else 2.0,
                "enrolment_cut_off": CUT_OFF.get(crop, DEFAULT_CUT_OFF),
            })
    return {
        "simulated": True,
        "title": TITLE,
        "publisher": PUBLISHER,
        "as_of": AS_OF,
        "season": "Kharif 2026",
        "state": "Tamil Nadu",
        "doc_url": DOC_URL,
        "notice": "SIMULATED DOCUMENT. All figures are synthetic placeholders created for the Araxys Desk demonstration. They are not an official notification and must not be relied on for any real claim.",
        "rows": rows,
    }


def _district_names() -> list[str]:
    p = DATA_DIR / "tn_districts.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw["districts"] if isinstance(raw, dict) and "districts" in raw else raw
        return [d["name"] for d in items]
    except Exception:  # pragma: no cover
        logger.warning("tn_districts.json unreadable; using empty district list")
        return []


def ensure_file() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    doc = generate(_district_names())
    DATA_FILE.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return doc


_CACHE: Optional[dict] = None


def load() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = ensure_file()
    return _CACHE


def citation() -> Citation:
    return Citation(id=CITATION_ID, title=TITLE, url=DOC_URL, publisher=PUBLISHER, page="Table 1",
                    as_of=AS_OF, quote="Sum insured per hectare by district and crop (simulated)", kind="scheme")


def lookup(crop: Optional[str], district: Optional[str]) -> Optional[dict]:
    if not crop or not district:
        return None
    crop_l, dist_l = crop.lower().replace(" ", "_"), district.lower()
    for row in load()["rows"]:
        if row["crop"] == crop_l and row["district"].lower() == dist_l:
            return row
    return None


def _inr(n: float) -> str:
    n = int(round(n))
    s = f"{n:,}"
    # Indian grouping
    if n >= 100000:
        head, tail = str(n)[:-3], str(n)[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:]); head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return "₹" + s


def ceiling_match(crop: Optional[str], district: Optional[str], hectares: Optional[float]) -> Optional[SchemeMatch]:
    """SchemeMatch describing the insured-value ceiling — never a payout."""
    row = lookup(crop, district)
    if not row:
        return None
    rate = row["sum_insured_per_ha"]
    text = (f"Under the (simulated) Tamil Nadu Kharif 2026 notification the sum insured for {row['crop_label']} "
            f"in {row['district']} is {_inr(rate)} per hectare")
    if hectares:
        text += f"; for {hectares:.2f} ha the policy ceiling is {_inr(rate * hectares)}"
    text += ". This is the maximum the policy covers, not a payout; the survey decides the loss percentage."
    return SchemeMatch(fact_id=CITATION_ID, scheme="PMFBY", field="sum_insured", text=text, citation=citation())


def render_knowledge() -> str:
    doc = load()
    by_district: dict[str, list[dict]] = {}
    for r in doc["rows"]:
        by_district.setdefault(r["district"], []).append(r)
    lines = [
        "SUM INSURED TABLE — Tamil Nadu Kharif 2026 notification (SIMULATED for this demonstration; say 'according to the district notification' when quoting).",
        "Figures are rupees per hectare. Quote a figure ONLY as the policy ceiling: 'the policy covers up to X per hectare, that is the most it covers, not the amount you will receive; the survey decides the loss percentage'. Never state a payout.",
        "Farmer premium share: two per cent of sum insured for food and oilseed crops, five per cent for commercial and horticultural crops.",
        "",
    ]
    for d, rows in sorted(by_district.items()):
        parts = [f"{r['crop_label'].split(' (')[0]} {r['sum_insured_per_ha']:,}" for r in rows]
        lines.append(f"[N1-{d.replace(' ', '')}] {d}: " + "; ".join(parts) + ".")
    return "\n".join(lines)


def render_html() -> str:
    doc = load()
    by_district: dict[str, list[dict]] = {}
    for r in doc["rows"]:
        by_district.setdefault(r["district"], []).append(r)
    crops = list(BASE_RATES.keys())
    head = "".join(f"<th>{CROP_LABELS[c].split(' (')[0]}</th>" for c in crops)
    body = ""
    for d, rows in sorted(by_district.items()):
        m = {r["crop"]: r for r in rows}
        body += f"<tr><th>{d}</th>" + "".join(f"<td>{m[c]['sum_insured_per_ha']:,}</td>" if c in m else "<td>–</td>" for c in crops) + "</tr>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{TITLE}</title>
<style>body{{font-family:Georgia,serif;margin:40px;color:#111}} .warn{{background:#fff3cd;border:2px solid #d39e00;padding:14px 18px;font-family:sans-serif;font-weight:600}}
table{{border-collapse:collapse;font-size:12px;margin-top:20px}} th,td{{border:1px solid #999;padding:4px 8px;text-align:right}} th:first-child{{text-align:left}} thead th{{background:#eee}}</style></head>
<body><div class="warn">SIMULATED DOCUMENT — {doc['notice']}</div>
<h1>{TITLE}</h1><p><b>Season:</b> {doc['season']} &nbsp; <b>State:</b> {doc['state']} &nbsp; <b>Dated:</b> {doc['as_of']} &nbsp; <b>Publisher:</b> {doc['publisher']}</p>
<h2>Table 1 — Sum insured per hectare (₹) by district and notified crop</h2>
<div style="overflow:auto"><table><thead><tr><th>District</th>{head}</tr></thead><tbody>{body}</tbody></table></div>
<p>Farmer premium share: 2% of sum insured for food and oilseed crops; 5% for commercial and horticultural crops (as per PMFBY guidelines). Enrolment cut-off dates by crop are listed in the machine-readable JSON.</p>
<p><a href="/api/knowledge/documents/{DOC_ID}.json">Machine-readable JSON</a></p></body></html>"""
