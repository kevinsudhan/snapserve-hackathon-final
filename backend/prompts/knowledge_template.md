# Knowledge block layout

How the injected blocks inside `system_prompt.md` are laid out, so that every
worker renders the same shape and every id the agent can quote resolves to a
real source in the CRM.

`services/knowledge.py` (core) substitutes the placeholders. It must not
reformat what the renderers return.

| Placeholder | Rendered by | Owner |
|---|---|---|
| `{{SCHEME_KNOWLEDGE}}` | `services.schemes.render_scheme_knowledge()` | schemes |
| `{{WEATHER_KNOWLEDGE}}` | `services.knowledge_weather.render_weather_knowledge()` | data |
| `{{CROP_CALENDAR}}` | crop-calendar renderer | data |
| `{{EVIDENCE_CHECKLISTS}}` | `services.schemes.render_evidence_checklists()` | schemes |
| `{{SAFE_SCRIPTS}}` | `services.schemes.render_safe_scripts()` | schemes |
| `{{REVIEWER_PHONE}}` | `settings.REVIEWER_PHONE` | core |
| `{{GENERATED_AT}}` | ISO timestamp of the refresh, in IST | core |

## Id conventions

Every quotable fact carries an id in square brackets at the start of its line.
The agent is told, in the prompt, never to speak an id — the id exists so the
post-call auditor can check what the agent claimed, and so the CRM can turn a
spoken fact into a clickable source.

| Prefix | Shape | Example | Resolves through |
|---|---|---|---|
| Scheme | `[S<n>]` | `[S34]` | `schemes.citation_by_id` |
| Weather | `[W-<District>-<YYYY-MM-DD>]` | `[W-Cuddalore-2026-09-02]` | weather/knowledge_weather |
| Crop calendar | `[C-<n>]` | `[C-12]` | crops |
| Gazetteer | `[G-<n>]` | `[G-3]` | gazetteer |
| Disaster | `[D-<gdacs id>]` | `[D-1102345]` | disasters |

`citation_by_id` in each module returns `None` for prefixes it does not own, so
core can try the resolvers in turn without exceptions.

## Block shape

Each block starts with one short instruction paragraph addressed to the agent,
then `##` sub-headings, then one fact per line. Lines are plain sentences a
voice model can speak after light rewording — never tables, never nested
bullets, never anything that reads badly out loud.

```
SCHEME FACTS. Each line is one fact you may state. ...

## What is covered
[S18] (PMFBY) The basic cover protects the standing crop from sowing until harvesting.
[S23] (PMFBY) Post-harvest cover is available only for up to two weeks ...

## Timelines in the guidelines (NEVER promise these)
[S65] (PMFBY) The guidelines set a target for settlement ... [NEVER PROMISE THIS — say the guidelines set a target and the reviewer confirms]
```

Scope is shown in the parenthesis after the scheme name when a fact is not
universal, e.g. `(PMFBY, only Cuddalore/Ranipet, kharif)`. Facts whose
`sensitivity` is `never_promise` carry the inline NEVER PROMISE flag.

The weather block follows the same idea, one line per district-day:

```
[W-Cuddalore-2026-09-12] Cuddalore, twelfth of September: rain about four millimetres, gusts about thirty kilometres an hour.
```

## Ordering inside the prompt

Scheme facts, then weather, then crop calendar, then evidence checklists, then
safe scripts. Safe scripts sit last so that they are the most recent thing in
context when the model is baited near the end of a call.

## Size budget

Scheme block is roughly three thousand tokens. Weather is capped at about
twelve thousand. Crop calendar about two thousand. Evidence and scripts about
two thousand together. `GET /api/knowledge/prompt` reports the real count.
