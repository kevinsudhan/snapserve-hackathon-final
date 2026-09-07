"""Guardrail auditing over agent turns.

Two independent detectors:

* **rules** — deterministic multilingual regexes (Latin transliteration *and*
  native script) for payout / approval / timeline promises and out-of-scope
  advice.  Sentence-scoped with negation and duty-marker exemptions so that a
  correct refusal ("I cannot promise an amount, a reviewer will confirm") and a
  legitimate scheme deadline ("intimate within 72 hours") never trip.
* **llm** — a Gemini judge (``prompts/audit.md``) returning quotes, mapped back
  onto turn indices.

Only turns with ``role == "agent"`` are ever inspected: the farmer may say
whatever they like.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

from app.schemas import AuditResult, GuardrailIncident, TranscriptTurn

logger = logging.getLogger(__name__)

MAX_QUOTE = 240

# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------
_CURRENCY = re.compile(
    r"(₹|\bRs\.?\b|\brupees?\b|\blakhs?\b|\blaksh\b|\bcrores?\b|\bthousands?\b"
    r"|\bhaz+a+r\b|\bhajar\b|\bpaisa\b|\bpaise\b|\bamount\b|\bcompensation\b|\bpayout\b"
    r"|\bpanam\b|\bkaasu\b|\bkasu\b|\bdabbu\b|\bhana\b|\brupay\b|\brubai\b"
    r"|ரூபாய்|ரூபா|रुपये|रुपए|रुपया|రూపాయ|ರೂಪಾಯಿ|രൂപ|പണം|पैसा|డబ్బు|ಹಣ|பணம்)",
    re.IGNORECASE | re.UNICODE,
)

_GET_VERB = re.compile(
    r"(\bwill get\b|\byou get\b|\bgets?\b|\bgetting\b|\breceiv\w*\b|\bwill come\b"
    r"|\bcredit\w*\b|\bpaid\b|\bpay you\b|\bsanction\w*\b|\bdisburs\w*\b"
    r"|kidaikkum|kedaikkum|kidaikum|kittum|milega|milegi|milenge|milta hai"
    r"|vastundi|vasthundi|siguttade|sigutthade|kittum"
    r"|கிடைக்கும்|வரும்|मिलेगा|मिलेगी|मिलेंगे|వస్తుంది|ಸಿಗುತ್ತದೆ|കിട്ടും)",
    re.IGNORECASE | re.UNICODE,
)

# amounts written as digits next to a currency marker, e.g. "₹50,000", "50000 rupees"
_AMOUNT_FIGURE = re.compile(
    r"(₹\s?\d[\d,\.]*|\b\d[\d,\.]*\s?(rupees?|rs\.?|lakhs?|thousand|hazaar|crores?)\b)",
    re.IGNORECASE | re.UNICODE,
)

_APPROVAL_STRONG = re.compile(
    r"(\bapproved\b|\bapproval is\b|\bguarantee\w*\b|\bassure\w*\b|\bpromise\b"
    r"|\bpakka\b|\bpucca\b|\bkandippa\w*\b|\bkandipaa\w*\b|\bnichayam\w*\b"
    r"|\bzaroor\b|\bzarur\b|\btappakunda\b|\bkhandita\w*\b|\burappu\w*\b"
    r"|\bnishchit\w*\b|\byaqeen\b"
    r"|கண்டிப்பா|நிச்சயம்|உறுப்பு|உறுதி|மறுக்காம|ज़रूर|जरूर|पक्का|निश्चित"
    r"|తప్పకుండా|ఖచ్చితంగా|ಖಂಡಿತ|ഉറപ്പ്|തീർച്ചയായും)",
    re.IGNORECASE | re.UNICODE,
)

# weak words that only matter next to an outcome word
_APPROVAL_WEAK = re.compile(
    r"(\bsure\b|\bsurely\b|\bdefinitely\b|\bcertainly\b|\bfor sure\b|\bno doubt\b)",
    re.IGNORECASE | re.UNICODE,
)

_OUTCOME_WORD = re.compile(
    r"(\bclaim\b|\bapprov\w*\b|\bmoney\b|\bamount\b|\bcompensation\b|\binsurance\b"
    r"|\bsettle\w*\b|\bpayment\b|\bpayout\b|\bpass\b|\bsanction\w*\b|\beligib\w*\b"
    r"|\bsurvey\b|₹|\bcredit\w*\b)",
    re.IGNORECASE | re.UNICODE,
)

_TIMELINE = re.compile(
    r"(\bwithin\s+\w+\s*(day|days|week|weeks|month|months|hour|hours)\b"
    r"|\bin\s+(a|one|two|three|four|five|\d+)\s*(day|days|week|weeks|month|months)\b"
    r"|\bby\s+(next|this)\s+(week|month|monday|friday)\b"
    r"|\bnext\s+week\b|\bnext\s+month\b|\btomorrow\b|\bin a week\b"
    r"|naal+a?-?la\b|naatkalil|dinam|din\s+me(in)?\b|dino\s+me(in)?\b"
    r"|rojullo|rojula|dinagalalli|dinagala\b|divasam|divasathinu"
    r"|நாட்களில்|நாளில்|நாளைக்கு|दिन में|दिनों में|सप्ताह में|రోజుల్లో|రోజులలో"
    r"|ದಿನಗಳಲ್ಲಿ|ദിവസത്തിനുള്ളിൽ|ദിവസത്തിൽ)",
    re.IGNORECASE | re.UNICODE,
)

# farmer-side deadlines are legitimate scheme facts, not promises
_DUTY_MARKER = re.compile(
    r"(intimat\w*|\breport\b|\breporting\b|\binform\b|\bapply\b|\bapplication\b"
    r"|\bsubmit\b|\benrol\w*\b|\bregistration\b|\bdeadline\b|cut-?off|\b14447\b"
    r"|\b72\s*hour|\bhelpline\b|\byou must\b|\byou have to\b|\byou should\b"
    r"|\blast date\b|\bbefore\b)",
    re.IGNORECASE | re.UNICODE,
)

_OUT_OF_SCOPE = re.compile(
    r"(\b(take|get|apply for|avail|arrange)\s+(a\s+|another\s+)?loan\b|\bloan\s+(vaang\w*|edu\w*|lelo|le lo|lena)\b|\bborrow money\b|\bmortgage\w*\b|\bsell (your )?land\b"
    r"|\bsell the land\b|\bpledge\b|\bpesticide\b|\binsecticide\b|\bfungicide\b"
    r"|\bspray\s+\w+\s*(ml|litre|liter|gram|kg)\b|\bdosage\b|\bdose\b|\bmedicine\b"
    r"|\btablet\b|\binjection\b|\blawyer\b|\badvocate\b|\bcourt case\b|\bfile a case\b"
    r"|\bkadan\b|कर्ज|कर्जा|கடன்)",
    re.IGNORECASE | re.UNICODE,
)

_NEGATION = re.compile(
    r"(\bcannot\b|\bcan'?t\b|\bcan not\b|\bnot able\b|\bunable\b|\bwon'?t\b"
    r"|\bwill not\b|\bdo not\b|\bdon'?t\b|\bdoes not\b|\bdoesn'?t\b|\bnever\b"
    r"|\bno one can\b|\bnobody can\b|\bnot possible\b|\bnot decide\b|\bnot say\b"
    r"|\bnot tell\b|\bnot know\b|\bnot promise\b|\bno promise\b|\bwithout\b"
    r"|\bonly a reviewer\b|\bi am not\b|\bnot allowed\b|\bnot guarantee\w*\b"
    r"|mudiyath?u|mudiyaadhu|theriyath?u|theriyaadhu|\billa\b|\billai\b|\bille\b"
    r"|nahi+n?\b|nahee?n\b|\bledu\b|\bkaadu\b|\bkadu\b|\balla\b|\billa\b"
    r"|sollamudiyathu|\bmaaf\b"
    r"|இல்லை|இல்ல|முடியாது|தெரியாது|சொல்ல முடியாது"
    r"|नहीं|नही|सकता नहीं|पता नहीं|लేదు|కాదు|తెలియదు|ಇಲ್ಲ|ಗೊತ್ತಿಲ್ಲ|ഇല്ല|അല്ല|അറിയില്ല)",
    re.IGNORECASE | re.UNICODE,
)

_SENTENCE_SPLIT = re.compile(r"[.!?;\n]+|।|॥")


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text or "") if part.strip()]


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_QUOTE else text[: MAX_QUOTE - 1] + "…"


# --------------------------------------------------------------------------
# deterministic rules
# --------------------------------------------------------------------------
def scan_sentence(sentence: str) -> list[tuple[str, str]]:
    """Return ``[(category, severity)]`` triggered by one agent sentence."""
    if _NEGATION.search(sentence):
        return []

    hits: list[tuple[str, str]] = []

    money = bool(_CURRENCY.search(sentence))
    figure = bool(_AMOUNT_FIGURE.search(sentence))
    getting = bool(_GET_VERB.search(sentence))
    outcome = bool(_OUTCOME_WORD.search(sentence))

    if figure and (getting or outcome):
        hits.append(("payout_promise", "high"))
    elif money and getting:
        hits.append(("payout_promise", "high"))

    if _APPROVAL_STRONG.search(sentence) and outcome:
        hits.append(("approval_promise", "high"))
    elif _APPROVAL_STRONG.search(sentence) and getting:
        hits.append(("approval_promise", "high"))
    elif _APPROVAL_WEAK.search(sentence) and outcome and getting:
        hits.append(("approval_promise", "medium"))

    if _TIMELINE.search(sentence) and not _DUTY_MARKER.search(sentence):
        if outcome or getting:
            hits.append(("timeline_promise", "high" if outcome and getting else "medium"))

    if _OUT_OF_SCOPE.search(sentence):
        hits.append(("out_of_scope_advice", "medium"))

    return hits


def scan_turns(turns: Iterable[TranscriptTurn]) -> list[GuardrailIncident]:
    """Deterministic pass over agent turns only."""
    incidents: list[GuardrailIncident] = []
    for turn in turns:
        if turn.role != "agent" or not turn.text:
            continue
        seen: set[str] = set()
        for sentence in _sentences(turn.text):
            for category, severity in scan_sentence(sentence):
                if category in seen:
                    continue
                seen.add(category)
                incidents.append(
                    GuardrailIncident(
                        turn_index=turn.i,
                        category=category,  # type: ignore[arg-type]
                        text=_clip(sentence),
                        severity=severity,  # type: ignore[arg-type]
                        detector="rules",
                    )
                )
    return incidents


# --------------------------------------------------------------------------
# LLM judge
# --------------------------------------------------------------------------
def _agent_block(turns: Iterable[TranscriptTurn]) -> str:
    lines = [f"[{turn.i}] {turn.text}" for turn in turns if turn.role == "agent" and turn.text]
    return "\n".join(lines)


def _locate_quote(quote: str, turns: list[TranscriptTurn]) -> int:
    """Map a judge quote back to a turn index (substring, then token overlap)."""
    needle = " ".join(quote.split()).lower()
    if not needle:
        return -1
    for turn in turns:
        if turn.role == "agent" and needle in " ".join(turn.text.split()).lower():
            return turn.i
    tokens = {token for token in re.findall(r"\w+", needle) if len(token) > 3}
    best_index, best_score = -1, 0.0
    for turn in turns:
        if turn.role != "agent":
            continue
        turn_tokens = {t for t in re.findall(r"\w+", turn.text.lower()) if len(t) > 3}
        if not tokens or not turn_tokens:
            continue
        score = len(tokens & turn_tokens) / len(tokens)
        if score > best_score:
            best_index, best_score = turn.i, score
    return best_index if best_score >= 0.5 else -1


async def judge_turns(turns: list[TranscriptTurn]) -> list[GuardrailIncident]:
    """Gemini judge pass. Returns [] when Gemini is disabled/unavailable."""
    from services import gemini

    if not gemini.is_available():
        return []
    block = _agent_block(turns)
    if not block.strip():
        return []

    template = gemini.load_prompt("audit.md")
    if not template:
        return []
    prompt = template.replace("{{AGENT_TURNS}}", block)

    result = await gemini.generate_json(prompt, AuditResult)
    if result is None:
        return []

    incidents: list[GuardrailIncident] = []
    for item in result.incidents:
        quote = (item.quote or "").strip()
        if not quote:
            continue
        incidents.append(
            GuardrailIncident(
                turn_index=_locate_quote(quote, turns),
                category=item.category,
                text=_clip(quote),
                severity=item.severity,
                detector="llm",
            )
        )
    return incidents


# --------------------------------------------------------------------------
# merge
# --------------------------------------------------------------------------
_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def merge_incidents(*groups: Iterable[GuardrailIncident]) -> list[GuardrailIncident]:
    """Dedupe by (turn_index, category); rules win, highest severity wins."""
    best: dict[tuple[int, str], GuardrailIncident] = {}
    for group in groups:
        for incident in group:
            key = (incident.turn_index, incident.category)
            current = best.get(key)
            if current is None:
                best[key] = incident
                continue
            if _SEVERITY_ORDER[incident.severity] > _SEVERITY_ORDER[current.severity]:
                best[key] = incident
            elif current.detector == "llm" and incident.detector == "rules":
                best[key] = incident
    return sorted(best.values(), key=lambda inc: (inc.turn_index, inc.category))


async def audit(
    turns: list[TranscriptTurn], *, use_llm: bool = True
) -> list[GuardrailIncident]:
    """Full audit: deterministic rules plus (optionally) the Gemini judge."""
    rules = scan_turns(turns)
    llm: list[GuardrailIncident] = []
    if use_llm:
        try:
            llm = await judge_turns(turns)
        except Exception as exc:  # pragma: no cover - judge must never break ingest
            logger.warning("guardrail judge failed: %s", exc.__class__.__name__)
    merged = merge_incidents(rules, llm)
    if merged:
        logger.info("guardrail: %d incident(s) (%d rules, %d llm)", len(merged), len(rules), len(llm))
    return merged


def fabricated_scheme_incident(
    turn_index: int, quoted: str, citation_id: Optional[str] = None
) -> GuardrailIncident:
    """Built by the ingest pipeline when the agent quotes an unknown fact."""
    detail = f"{quoted} (unknown citation {citation_id})" if citation_id else quoted
    return GuardrailIncident(
        turn_index=turn_index,
        category="fabricated_scheme",
        text=_clip(detail),
        severity="high",
        detector="rules",
    )


def missed_escalation_incident(turn_index: int, reason: str) -> GuardrailIncident:
    return GuardrailIncident(
        turn_index=turn_index,
        category="missed_escalation",
        text=_clip(reason),
        severity="high",
        detector="rules",
    )
