# Data sources — scheme knowledge

Every fact the Araxys Desk agent may state about a crop-insurance scheme lives in
`backend/data/schemes.json`, and every one of them carries a source URL, a
page or section reference, a retrieval date and a verbatim quote of at most
twenty-five words. `backend/tests/test_schemes.py` fails the build if any fact
is missing one of those.

Downloaded copies of every source are kept in `backend/data/sources/` so that a
citation can still be checked if a site is down on judging day.

Facts as of this pass: **83**, from **five** sources.

---

## 1. PMFBY Revamped Operational Guidelines (primary source)

| | |
|---|---|
| What | The national rulebook for Pradhan Mantri Fasal Bima Yojana — coverage, enrolment, risks, exclusions, intimation, premium shares, loss assessment, timelines, grievance redressal |
| URL | https://pmfby.gov.in/pdf/Revamped%20OGs_Final.pdf |
| Publisher | Department of Agriculture, Cooperation & Farmers Welfare, Ministry of Agriculture & Farmers Welfare, Government of India |
| Document date | Effective from Kharif 2020 |
| Retrieved | 2026-09-05 |
| Local copy | `backend/data/sources/PMFBY_Revamped_OGs_Final.pdf` (1,729,568 bytes, 144 pages) |
| Extraction | `pypdf.PdfReader(...).pages[i].extract_text()`, page by page |
| Facts drawn | S1–S70, S73–S76 (74 facts) |

**Page numbering.** The `page` field cites the **PDF page number** (what a
reader sees in a viewer) plus the paragraph number, for example
`"PDF p.73, para 21.5.4.1 A"`. The document's own printed page numbers run
seven lower than the PDF page (printed page 1 is PDF page 8), so the paragraph
number is included to make either numbering findable.

**Sections covered.** Background and para 1 (purpose); para 2 (portal); para 3
(who can enrol, documents, loanee opt-out); para 4 (crops); para 5 (risks,
add-ons, exclusions, individual vs area assessment); para 12 (sum insured);
para 13 and Table 1 (premium shares); para 16.4 Table 2 (seasonality, enrolment
dates); para 17 (enrolment channels); para 18 (area approach, insurance unit);
para 21.2 (threshold yield, crop cutting experiments); para 21.3 (prevented
sowing); para 21.5 (localized calamities, seventy-two hour intimation);
para 21.6 (post-harvest losses, fourteen days, intimation, survey, timelines);
para 23 (settlement to farmers); para 24–25 (conditions, acreage discrepancy);
para 30 (grievance redressal); para 35.9–35.10 (farmer's own duties and
documents).

**Verbatim check.** Every quote is verified by normalising both the quote and
the full extracted PDF text (lower-cased, all non-alphanumeric characters
removed, which absorbs the extractor's stray spaces and hyphens) and asserting
the quote is a substring. The check lives in `backend/tests/test_schemes.py`
and runs against the local PDF, so it is a real check, not a stored hash.

## 2. PIB press release — grievance helpline

| | |
|---|---|
| What | Confirms the national crop-insurance helpline number 14447 (KrishiRakshak Portal & Helpline) and that it runs round the clock |
| URL | https://www.pib.gov.in/PressReleasePage.aspx?PRID=2197713&reg=3&lang=1 |
| Publisher | Press Information Bureau, Ministry of Agriculture & Farmers Welfare, Government of India |
| Document date | 02 December 2025 |
| Retrieved | 2026-09-05 |
| Local copy | `backend/data/sources/pib_pmfby_og_2197713.html` |
| Extraction | `httpx` GET, tags stripped, whitespace normalised |
| Facts drawn | S71, S72 |

Why this and not pmfby.gov.in itself: the portal home page and its `/krph/`
page are JavaScript-rendered and return an empty document body to a plain HTTP
fetch, so nothing on them can be quoted verbatim. The PIB release is an
official Government of India publication that states the number in prose.

## 3. RWBCIS Revised Operational Guidelines

| | |
|---|---|
| What | The weather-index scheme that sits alongside PMFBY — one-liner on what it is and which weather perils it covers |
| URL | https://pmfby.gov.in/pdf/RWBCIS_Revised_Guidelines_1.pdf |
| Publisher | Department of Agriculture, Cooperation & Farmers Welfare, Government of India |
| Retrieved | 2026-09-05 |
| Local copy | `backend/data/sources/RWBCIS_Revised_Guidelines.pdf` (353,021 bytes, 19 pages) |
| Extraction | pypdf, same method |
| Facts drawn | S82, S83 |

## 4. Tamil Nadu Kharif 2026 — press coverage of the state notification

| | |
|---|---|
| What | Which company implements PMFBY in Ranipet and Cuddalore for Kharif 2026, the notified crop list, the cut-off date window, and the enrolment channels |
| URL | https://www.businessminutes.in/2026/07/hdfc-ergo-rolls-out-pmfby-for-tamil-nadu-farmers.html |
| Publisher | Business Minutes — **press coverage, not the state notification itself** |
| Article date | 08 July 2026 |
| Retrieved | 2026-09-05 |
| Local copy | `backend/data/sources/tn_kharif2026_hdfcergo_press.html` |
| Facts drawn | S77–S80 |

**Confidence note.** This is the weakest source in the set and is labelled as
such in the citation's `publisher` field, which the CRM shows. It is used
because the Tamil Nadu Kharif 2026 notification itself was not reachable in a
quotable form (see gaps below). Consequently:

- the crop list (S78) is stated as the crops *named for that season*, not as an
  exhaustive legal list;
- the cut-off window (S79) is marked `sensitivity: "never_promise"` so the
  agent must not tell a farmer their deadline;
- no sum insured, indemnity level or per-crop date is claimed anywhere. Those
  come back from `lookup_scheme` as spoken unknowns instead.

## 5. Department of Economics and Statistics, Tamil Nadu — PMFBY page

| | |
|---|---|
| What | Who conducts the crop cutting experiments that decide average yield in Tamil Nadu |
| URL | https://des.tn.gov.in/en/node/15 |
| Publisher | Department of Economics and Statistics, Government of Tamil Nadu |
| Retrieved | 2026-09-05 |
| Local copy | `backend/data/sources/des_tn_pmfby.html` |
| Facts drawn | S81 |

---

## Known gaps — deliberately left out rather than guessed

These were looked for and not found in a quotable, official form. None of them
is invented anywhere in the data. Each is returned by `lookup_scheme` as an
unknown sentence the agent speaks out loud.

1. **Sum insured per hectare** for any crop, district or season. Set by the
   state notification; not published in a form we could quote.
2. **Indemnity level and threshold yield** for any insurance unit. The
   guidelines explicitly say threshold yield is not public information before
   claims are paid for that season (para 23.2).
3. **Per-crop enrolment cut-off dates** for Cuddalore and Ranipet, Kharif 2026.
   Only the window "15 July to 15 September 2026" is sourced, and only from
   press coverage.
4. **The Tamil Nadu Kharif 2026 notification PDF itself.**
   `tnhorticulture.tn.gov.in/pmfby` returns 404 and the Cuddalore district site
   publishes collector press notes as scanned PDFs that were not machine
   readable in this pass.
5. **Which add-on covers (prevented sowing, mid-season, localized, post-harvest)
   Tamil Nadu notified for Kharif 2026.** The guidelines say each add-on exists
   only if the state notified it (S28), so the agent says exactly that.
6. **Whether a given caller is enrolled**, and whether their premium was
   debited. There is no lookup for this; the agent says so.
7. **Claim settlement performance** — how long settlements actually take in
   practice. Only the guideline targets exist, and they are all marked
   `never_promise`.

## Refresh procedure

1. `backend/.venv/Scripts/python -c "import httpx; open('backend/data/sources/PMFBY_Revamped_OGs_Final.pdf','wb').write(httpx.get('https://pmfby.gov.in/pdf/Revamped%20OGs_Final.pdf', timeout=90, follow_redirects=True).content)"`
   (the site's certificate chain has needed `verify=False` from some networks).
2. Re-run `backend/.venv/Scripts/python -m pytest backend/tests/test_schemes.py`.
   The verbatim test re-extracts the PDF and will fail on any quote whose text
   or paragraph moved in a new edition.
3. If a quote fails, open the PDF at the cited paragraph, re-quote, and update
   `page` to the new PDF page. Do not weaken a quote to make a test pass.
4. Re-check the Tamil Nadu notification each season. When the official state
   notification becomes available, replace S77–S80 with facts cited to it and
   move the press article to a secondary reference.
5. `POST /api/knowledge/refresh` re-renders the prompt and pushes it to the
   SnapServe agent.

## Cadence

- PMFBY Operational Guidelines: check once a season; they change rarely.
- Helpline and grievance details: check once a season.
- State notification facts: **every season**, and before any demo.
- Everything else in the prompt (weather, disasters) is refreshed on every
  `POST /api/knowledge/refresh` and is owned by the data worker.
