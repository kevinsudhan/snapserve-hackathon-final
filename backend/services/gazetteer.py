"""Offline Tamil Nadu gazetteer: district centroids, aliases and a town table.

There is no geocoding call anywhere in this module. Everything resolves against
``backend/data/tn_districts.json`` plus the alias and town tables below, using
rapidfuzz for transliteration variants ("Kovai" -> Coimbatore, "Trichy" ->
Tiruchirappalli). Unknown places come back with low confidence rather than a
guessed coordinate.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from .models import Citation, Location

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DISTRICTS_PATH = DATA_DIR / "tn_districts.json"

#: rapidfuzz WRatio floor for accepting a fuzzy name match.
MATCH_THRESHOLD = 80

CONFIDENCE_DISTRICT = 0.9
CONFIDENCE_TALUK = 0.8
CONFIDENCE_VILLAGE_UNKNOWN = 0.5
CONFIDENCE_NONE = 0.0

__all__ = [
    "resolve_location",
    "list_districts",
    "gazetteer_citation",
    "district_slug",
    "DISTRICT_ALIASES",
    "TOWN_TO_DISTRICT",
]

# --------------------------------------------------------------------------- #
# alias table: transliteration and colloquial variants -> official name
# --------------------------------------------------------------------------- #
DISTRICT_ALIASES: dict[str, str] = {
    # Coimbatore
    "kovai": "Coimbatore", "koyamputhur": "Coimbatore", "koimbatore": "Coimbatore",
    # Tiruchirappalli
    "trichy": "Tiruchirappalli", "tiruchi": "Tiruchirappalli",
    "thiruchirappalli": "Tiruchirappalli", "tiruchirapalli": "Tiruchirappalli",
    "trichinopoly": "Tiruchirappalli",
    # Thoothukudi
    "tuticorin": "Thoothukudi", "thoothukkudi": "Thoothukudi", "tuticorn": "Thoothukudi",
    # Nagapattinam
    "nagai": "Nagapattinam", "nagapattinam district": "Nagapattinam",
    "nagappattinam": "Nagapattinam", "negapatam": "Nagapattinam",
    # Kanniyakumari
    "kanyakumari": "Kanniyakumari", "kanniyakumari": "Kanniyakumari",
    "nagercoil": "Kanniyakumari", "cape comorin": "Kanniyakumari",
    "kumari": "Kanniyakumari",
    # Thanjavur
    "thanjai": "Thanjavur", "tanjore": "Thanjavur", "tanjavur": "Thanjavur",
    # Tirunelveli
    "nellai": "Tirunelveli", "thirunelveli": "Tirunelveli", "tinnevelly": "Tirunelveli",
    "palayamkottai": "Tirunelveli",
    # Madurai
    "mathurai": "Madurai", "madura": "Madurai",
    # Vellore
    "velur": "Vellore", "vellor": "Vellore",
    # Cuddalore
    "kadalur": "Cuddalore", "cuddalur": "Cuddalore", "kadaloor": "Cuddalore",
    # Viluppuram
    "villupuram": "Viluppuram", "vizhupuram": "Viluppuram", "vilupuram": "Viluppuram",
    # The Nilgiris
    "ooty": "The Nilgiris", "nilgiris": "The Nilgiris", "nilgiri": "The Nilgiris",
    "udhagamandalam": "The Nilgiris", "ootacamund": "The Nilgiris",
    "neelagiri": "The Nilgiris",
    # Pudukkottai
    "pudukottai": "Pudukkottai", "puthukottai": "Pudukkottai",
    # Sivaganga
    "sivagangai": "Sivaganga", "sivaganga district": "Sivaganga",
    # Virudhunagar
    "virudunagar": "Virudhunagar", "virudhunagar district": "Virudhunagar",
    # Ramanathapuram
    "ramnad": "Ramanathapuram", "ramanathapura": "Ramanathapuram",
    "ramanad": "Ramanathapuram",
    # Chennai
    "madras": "Chennai", "chennai city": "Chennai",
    # Kancheepuram
    "kanchipuram": "Kancheepuram", "kanchi": "Kancheepuram",
    "conjeevaram": "Kancheepuram",
    # Tiruvannamalai
    "thiruvannamalai": "Tiruvannamalai", "tiruvanamalai": "Tiruvannamalai",
    "thiruvanamalai": "Tiruvannamalai", "annamalai": "Tiruvannamalai",
    # Tiruvallur
    "thiruvallur": "Tiruvallur", "tiruvalur": "Tiruvallur", "tiruvellore": "Tiruvallur",
    # Tiruvarur
    "thiruvarur": "Tiruvarur", "tiruvaroor": "Tiruvarur",
    # Tiruppur
    "tirupur": "Tiruppur", "thiruppur": "Tiruppur", "tiruppur district": "Tiruppur",
    # Tirupathur
    "tirupattur": "Tirupathur", "thirupathur": "Tirupathur",
    "tirupattur district": "Tirupathur",
    # Others
    "dharmapuri district": "Dharmapuri", "dharampuri": "Dharmapuri",
    "erodu": "Erode", "salem district": "Salem", "selam": "Salem",
    "dhindigul": "Dindigul", "dindukkal": "Dindigul", "dindukal": "Dindigul",
    "theni district": "Theni", "thanjavur district": "Thanjavur",
    "mayiladuthurai district": "Mayiladuthurai", "mayavaram": "Mayiladuthurai",
    "kallakkurichi": "Kallakurichi", "chengalpet": "Chengalpattu",
    "chingleput": "Chengalpattu", "ranipettai": "Ranipet",
    "tenkashi": "Tenkasi", "thenkasi": "Tenkasi",
    "krishnagiri district": "Krishnagiri", "namakkal district": "Namakkal",
    "ariyalur district": "Ariyalur", "perambalur district": "Perambalur",
    "karur district": "Karur",
}

# --------------------------------------------------------------------------- #
# town / taluk -> district
# --------------------------------------------------------------------------- #
#: Well-known towns and taluk headquarters mapped to their district. Compiled
#: offline from general knowledge of Tamil Nadu administrative geography and
#: cross-checked against the official district list; ambiguous or uncertain
#: names were deliberately left out rather than guessed.
TOWN_TO_DISTRICT: dict[str, str] = {}


def _add_towns(district: str, towns: list[str]) -> None:
    for town in towns:
        TOWN_TO_DISTRICT[town.strip().lower()] = district


_add_towns("Ariyalur", ["Ariyalur", "Udayarpalayam", "Jayankondam", "Sendurai", "Andimadam"])
_add_towns("Chengalpattu", [
    "Chengalpattu", "Tambaram", "Pallavaram", "Maduranthakam", "Thirukalukundram",
    "Cheyyur", "Thiruporur", "Vandalur", "Guduvancheri", "Kelambakkam", "Mamallapuram",
    "Mahabalipuram", "Chromepet",
])
_add_towns("Chennai", [
    "Chennai", "Madras", "Egmore", "Mylapore", "Guindy", "Ambattur", "Adyar",
    "Perambur", "Tondiarpet", "Anna Nagar", "Velachery", "Saidapet", "Aminjikarai",
])
_add_towns("Coimbatore", [
    "Coimbatore", "Pollachi", "Mettupalayam", "Sulur", "Annur", "Kinathukadavu",
    "Valparai", "Madukkarai", "Perur", "Thondamuthur", "Anaimalai", "Karamadai",
])
_add_towns("Cuddalore", [
    "Cuddalore", "Chidambaram", "Virudhachalam", "Panruti", "Kattumannarkoil",
    "Bhuvanagiri", "Kurinjipadi", "Tittakudi", "Neyveli", "Srimushnam", "Parangipettai",
])
_add_towns("Dharmapuri", [
    "Dharmapuri", "Palacode", "Pennagaram", "Harur", "Pappireddipatti",
    "Karimangalam", "Nallampalli",
])
_add_towns("Dindigul", [
    "Dindigul", "Palani", "Oddanchatram", "Vedasandur", "Natham", "Nilakottai",
    "Kodaikanal", "Athoor", "Guziliamparai", "Batlagundu", "Reddiarchatram",
])
_add_towns("Erode", [
    "Erode", "Gobichettipalayam", "Bhavani", "Sathyamangalam", "Perundurai",
    "Kodumudi", "Anthiyur", "Modakurichi", "Nambiyur", "Chennimalai", "Thalavadi",
])
_add_towns("Kallakurichi", [
    "Kallakurichi", "Chinnasalem", "Sankarapuram", "Ulundurpet", "Tirukoilur",
    "Rishivandiyam",
])
_add_towns("Kancheepuram", [
    "Kancheepuram", "Kanchipuram", "Uthiramerur", "Walajabad", "Sriperumbudur",
    "Kundrathur",
])
_add_towns("Kanniyakumari", [
    "Nagercoil", "Kanyakumari", "Padmanabhapuram", "Thovalai", "Agastheeswaram",
    "Kalkulam", "Vilavancode", "Colachel", "Marthandam", "Thuckalay", "Kuzhithurai",
])
_add_towns("Karur", [
    "Karur", "Kulithalai", "Krishnarayapuram", "Aravakurichi", "Kadavur",
    "Manmangalam", "Pugalur",
])
_add_towns("Krishnagiri", [
    "Krishnagiri", "Hosur", "Denkanikottai", "Pochampalli", "Uthangarai", "Bargur",
    "Anchetty", "Shoolagiri", "Kelamangalam",
])
_add_towns("Madurai", [
    "Madurai", "Melur", "Vadipatti", "Usilampatti", "Peraiyur", "Thirumangalam",
    "Sholavandan", "Kalligudi", "Tirupparankundram", "Alanganallur",
])
_add_towns("Mayiladuthurai", [
    "Mayiladuthurai", "Sirkazhi", "Kuthalam", "Tharangambadi", "Poompuhar",
    "Tranquebar",
])
_add_towns("Nagapattinam", [
    "Nagapattinam", "Vedaranyam", "Kilvelur", "Thirukkuvalai", "Velankanni",
])
_add_towns("Namakkal", [
    "Namakkal", "Rasipuram", "Tiruchengode", "Paramathi Velur", "Kolli Hills",
    "Mohanur", "Kumarapalayam", "Sendamangalam",
])
_add_towns("Perambalur", ["Perambalur", "Kunnam", "Veppanthattai", "Alathur"])
_add_towns("Pudukkottai", [
    "Pudukkottai", "Aranthangi", "Alangudi", "Illuppur", "Karambakudi",
    "Gandarvakottai", "Manamelkudi", "Ponnamaravathi", "Thirumayam",
    "Avudaiyarkoil", "Viralimalai",
])
_add_towns("Ramanathapuram", [
    "Ramanathapuram", "Rameswaram", "Paramakudi", "Kamuthi", "Mudukulathur",
    "Tiruvadanai", "Kadaladi", "Keelakarai", "Rajasingamangalam",
])
_add_towns("Ranipet", [
    "Ranipet", "Arakkonam", "Arcot", "Walajapet", "Sholinghur", "Nemili", "Kalavai",
])
_add_towns("Salem", [
    "Salem", "Mettur", "Attur", "Omalur", "Sankagiri", "Edappadi", "Gangavalli",
    "Yercaud", "Vazhapadi", "Kadayampatti", "Pethanaickenpalayam",
])
_add_towns("Sivaganga", [
    "Sivaganga", "Sivagangai", "Karaikudi", "Devakottai", "Manamadurai",
    "Ilayangudi", "Singampunari", "Kalayarkoil",
])
_add_towns("Tenkasi", [
    "Tenkasi", "Sankarankovil", "Shencottai", "Kadayanallur", "Alangulam",
    "Veerakeralampudur", "Thiruvengadam", "Sivagiri", "Courtallam", "Puliyangudi",
])
_add_towns("Thanjavur", [
    "Thanjavur", "Kumbakonam", "Papanasam", "Orathanadu", "Pattukkottai",
    "Peravurani", "Thiruvaiyaru", "Thiruvidaimarudur", "Budalur", "Ammapettai",
])
_add_towns("Theni", [
    "Theni", "Bodinayakanur", "Periyakulam", "Uthamapalayam", "Andipatti",
    "Cumbum", "Chinnamanur", "Kambam",
])
_add_towns("The Nilgiris", [
    "Udhagamandalam", "Ooty", "Ootacamund", "Coonoor", "Kotagiri", "Gudalur",
    "Pandalur", "Kundah",
])
_add_towns("Thoothukudi", [
    "Thoothukudi", "Tuticorin", "Kovilpatti", "Tiruchendur", "Srivaikuntam",
    "Ottapidaram", "Vilathikulam", "Sattankulam", "Ettayapuram", "Kayathar",
])
_add_towns("Tiruchirappalli", [
    "Tiruchirappalli", "Trichy", "Srirangam", "Lalgudi", "Manapparai", "Musiri",
    "Thuraiyur", "Thottiyam", "Manachanallur", "Marungapuri", "Tiruverumbur",
    "Samayapuram",
])
_add_towns("Tirunelveli", [
    "Tirunelveli", "Palayamkottai", "Ambasamudram", "Nanguneri", "Radhapuram",
    "Cheranmahadevi", "Manur", "Valliyoor", "Tisaiyanvilai",
])
_add_towns("Tirupathur", [
    "Tirupathur", "Vaniyambadi", "Ambur", "Natrampalli", "Jolarpettai",
])
_add_towns("Tiruppur", [
    "Tiruppur", "Udumalaipettai", "Dharapuram", "Palladam", "Avinashi", "Kangeyam",
    "Madathukulam", "Uthukuli",
])
_add_towns("Tiruvallur", [
    "Tiruvallur", "Ponneri", "Gummidipoondi", "Poonamallee", "Avadi", "Pallipattu",
    "Uthukottai", "Tiruttani", "Minjur", "Red Hills",
])
_add_towns("Tiruvannamalai", [
    "Tiruvannamalai", "Arani", "Cheyyar", "Polur", "Chengam", "Vandavasi",
    "Kalasapakkam", "Thandarampet", "Jamunamarathur", "Kilpennathur",
])
_add_towns("Tiruvarur", [
    "Tiruvarur", "Mannargudi", "Needamangalam", "Thiruthuraipoondi", "Kodavasal",
    "Nannilam", "Valangaiman", "Muthupet",
])
_add_towns("Vellore", [
    "Vellore", "Katpadi", "Gudiyatham", "Anaicut", "Pernambut", "K V Kuppam",
])
_add_towns("Viluppuram", [
    "Viluppuram", "Villupuram", "Tindivanam", "Gingee", "Vanur", "Marakkanam",
    "Vikravandi", "Melmalaiyanur", "Kandachipuram", "Auroville",
])
_add_towns("Virudhunagar", [
    "Virudhunagar", "Sivakasi", "Rajapalayam", "Srivilliputhur", "Aruppukkottai",
    "Sattur", "Tiruchuli", "Watrap", "Kariapatti", "Vembakottai",
])

#: Source note for the compiled town table (reviewers can audit it against LGD).
TOWN_TABLE_AS_OF = "2026-09-05"


# --------------------------------------------------------------------------- #
# district table
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _districts_payload() -> dict:
    """Cached read of ``backend/data/tn_districts.json``."""
    with DISTRICTS_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def list_districts() -> list[dict]:
    """All 38 Tamil Nadu districts as ``{name, lat, lon}``."""
    return [
        {"name": d["name"], "lat": d["lat"], "lon": d["lon"]}
        for d in _districts_payload()["districts"]
    ]


def district_slug(name: str) -> str:
    """``"The Nilgiris"`` -> ``"the-nilgiris"`` for gazetteer citation ids."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


@lru_cache(maxsize=1)
def _district_index() -> dict[str, dict]:
    """Lower-cased official name -> district record."""
    return {d["name"].lower(): d for d in _districts_payload()["districts"]}


def _normalise(text: str | None) -> str:
    """Lower-case, strip punctuation and drop the word 'district'."""
    if not text:
        return ""
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", text.strip().lower())
    cleaned = re.sub(r"\b(district|dist|taluk|taluka|tk|village|vill)\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _match(name: str, choices: list[str]) -> str | None:
    """Best rapidfuzz WRatio match at or above :data:`MATCH_THRESHOLD`."""
    if not name:
        return None
    hit = process.extractOne(name, choices, scorer=fuzz.WRatio)
    if hit and hit[1] >= MATCH_THRESHOLD:
        return hit[0]
    return None


def _resolve_district_name(text: str | None) -> str | None:
    """Map any spelling of a district name to its official name."""
    key = _normalise(text)
    if not key:
        return None
    index = _district_index()
    if key in index:
        return index[key]["name"]
    if key in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[key]
    alias_hit = _match(key, list(DISTRICT_ALIASES))
    official_hit = _match(key, list(index))
    # Prefer whichever scored, favouring the official list on a tie.
    if official_hit:
        return index[official_hit]["name"]
    if alias_hit:
        return DISTRICT_ALIASES[alias_hit]
    return None


def _resolve_town(text: str | None) -> str | None:
    """Map a town or taluk name to its district."""
    key = _normalise(text)
    if not key:
        return None
    if key in TOWN_TO_DISTRICT:
        return TOWN_TO_DISTRICT[key]
    hit = _match(key, list(TOWN_TO_DISTRICT))
    return TOWN_TO_DISTRICT[hit] if hit else None


# --------------------------------------------------------------------------- #
# citations
# --------------------------------------------------------------------------- #
def gazetteer_citation(cid: str) -> Citation | None:
    """Resolve a ``G-<district-slug>`` citation id to its source reference."""
    payload = _districts_payload()
    base = payload["citation"]
    if cid == base["id"]:
        return Citation(**base)
    if not cid.startswith("G-"):
        return None
    slug = cid[2:]
    for district in payload["districts"]:
        if district_slug(district["name"]) != slug:
            continue
        return Citation(
            id=cid,
            title=f"{district['name']} district, Tamil Nadu (centroid used: {district['hq']})",
            url=base["url"],
            publisher=base["publisher"],
            as_of=base["as_of"],
            quote=(
                f"{district['name']}: {district['lat']}, {district['lon']} "
                f"({payload['centroid_basis']})"
            ),
            kind="gazetteer",
        )
    return None


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #
def resolve_location(
    village: str | None,
    taluk: str | None,
    district: str | None,
    state: str = "Tamil Nadu",
) -> Location:
    """Resolve a spoken place to a Tamil Nadu district centroid, offline.

    The ladder is district -> taluk -> village-as-town. Coordinates are always
    the district centroid, so ``resolution_confidence`` says how coarse that is:

    * ``0.9`` a district name matched;
    * ``0.8`` a taluk or well-known town matched and its district was inferred;
    * ``0.5`` only a village name was given and it is not in our tables - the
      name is kept for a human, but no coordinates are invented;
    * ``0.0`` nothing usable was given or matched.

    Args:
        village: Village or hamlet name as heard.
        taluk: Taluk / block name as heard.
        district: District name as heard, in any transliteration.
        state: State name; anything other than Tamil Nadu resolves to 0.0.

    Returns:
        A :class:`~services.models.Location`.
    """
    if _normalise(state) not in {"tamil nadu", "tamilnadu", "tn", ""}:
        logger.info("State %r is outside Tamil Nadu; not resolving", state)
        return Location(
            village=village,
            taluk=taluk,
            district=district,
            state=state,
            resolution_confidence=CONFIDENCE_NONE,
            resolved_by="outside_tamil_nadu",
        )

    resolved: str | None = None
    resolved_by: str | None = None
    confidence = CONFIDENCE_NONE

    resolved = _resolve_district_name(district)
    if resolved:
        resolved_by, confidence = "district", CONFIDENCE_DISTRICT
    else:
        for value, label in ((taluk, "taluk"), (village, "town")):
            hit = _resolve_town(value) or _resolve_district_name(value)
            if hit:
                resolved, resolved_by, confidence = hit, label, CONFIDENCE_TALUK
                break

    if not resolved:
        if village or taluk:
            logger.info(
                "Unknown place: village=%r taluk=%r district=%r", village, taluk, district
            )
            return Location(
                village=village,
                taluk=taluk,
                district=district,
                state="Tamil Nadu",
                resolution_confidence=CONFIDENCE_VILLAGE_UNKNOWN,
                resolved_by="unresolved_village",
            )
        return Location(
            village=village,
            taluk=taluk,
            district=district,
            state="Tamil Nadu",
            resolution_confidence=CONFIDENCE_NONE,
            resolved_by=None,
        )

    record = _district_index()[resolved.lower()]
    return Location(
        village=village,
        taluk=taluk,
        district=resolved,
        state="Tamil Nadu",
        lat=record["lat"],
        lon=record["lon"],
        resolution_confidence=confidence,
        resolved_by=resolved_by,
        citation_id=f"G-{district_slug(resolved)}",
    )
