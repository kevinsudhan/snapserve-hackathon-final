"""Deterministic guardrail rules across scripts, and the false-positive floor."""

from __future__ import annotations

import asyncio

import pytest

from services import guardrail, ingest


def categories(agent_line: str) -> set[str]:
    turns = ingest.parse_transcript(f"Agent: {agent_line}")
    return {incident.category for incident in guardrail.scan_turns(turns)}


# --------------------------------------------------------------------------
# payout promises
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "You will get twenty thousand rupees for this damage.",
        "The amount of ₹20,000 will come to your account.",
        "Rs 15000 will be credited to you.",
        "Ungaluku panam kidaikkum, kavalai padaatheenga.",          # Tamil (roman)
        "Aapko paisa zaroor milega.",                                # Hindi (roman)
        "உங்களுக்கு பணம் கிடைக்கும்.",                                # Tamil
        "आपको पैसा मिलेगा।",                                          # Hindi
        "మీకు డబ్బు వస్తుంది.",                                       # Telugu
        "ನಿಮಗೆ ಹಣ ಸಿಗುತ್ತದೆ.",                                        # Kannada
        "നിങ്ങൾക്ക് പണം കിട്ടും.",                                     # Malayalam
    ],
)
def test_payout_promises_are_caught(line):
    assert "payout_promise" in categories(line)


# --------------------------------------------------------------------------
# approval promises
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "Your claim is approved.",
        "I guarantee your claim will pass.",
        "Pakka approval, no problem.",
        "Kandippa ungaluku claim kidaikkum.",
        "Aapka claim zaroor approve hoga.",
        "आपका दावा पक्का मंज़ूर होगा, claim approve हो जाएगा।",
        "మీ claim తప్పకుండా approve అవుతుంది.",
    ],
)
def test_approval_promises_are_caught(line):
    assert "approval_promise" in categories(line)


# --------------------------------------------------------------------------
# timeline promises
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "The money will come within ten days.",
        "You will get the amount in a week.",
        "By next month the compensation will reach you.",
        "Pathu naal-la panam kidaikkum.",
        "Das din mein paisa milega.",
        "పది రోజుల్లో డబ్బు వస్తుంది.",
    ],
)
def test_timeline_promises_are_caught(line):
    assert "timeline_promise" in categories(line)


# --------------------------------------------------------------------------
# out-of-scope advice
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "You should take a loan from the bank meanwhile.",
        "Better to sell your land and start again.",
        "Spray 500 ml of pesticide on the affected area.",
        "Go to a lawyer and file a case against the insurer.",
    ],
)
def test_out_of_scope_advice_is_caught(line):
    assert "out_of_scope_advice" in categories(line)


# --------------------------------------------------------------------------
# the false-positive floor — correct behaviour must never be flagged
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        # the exact phrasing from the contract
        "The reviewer will confirm; I cannot promise an amount.",
        "I cannot tell you any amount. The insurance company decides it after a survey.",
        "I am not able to promise approval. A reviewer checks every claim.",
        "I cannot say when it will happen, and I will not guess.",
        "You must intimate the loss within 72 hours through the helpline 14447.",
        "The last date to apply is 31 July; please submit before that.",
        "The rain record for Cuddalore on 12 September shows 4 mm of rain.",
        "Sure, I can note that down for you.",
        "Let me repeat what you told me so far.",
        "Please keep photos of the damaged crop and your land record ready.",
        "எனக்கு தெரியாது, ஒரு அதிகாரி உங்களிடம் பேசுவார்.",
        "मुझे नहीं पता, कोई अधिकारी आपसे बात करेगा।",
        "Enakku sollamudiyathu, reviewer paarpaanga.",
    ],
)
def test_correct_refusals_and_facts_are_not_incidents(line):
    assert categories(line) == set()


def test_caller_turns_are_never_audited():
    """A farmer may say anything; only the agent is audited."""
    turns = ingest.parse_transcript(
        "Caller: They told me I will definitely get fifty thousand rupees within a week!\n"
        "Agent: I cannot confirm any amount or date."
    )
    assert guardrail.scan_turns(turns) == []


def test_negation_is_scoped_to_the_sentence():
    """A refusal in one sentence must not excuse a promise in the next."""
    turns = ingest.parse_transcript(
        "Agent: I cannot tell you the exact figure. You will definitely get "
        "twenty thousand rupees for your claim."
    )
    found = {incident.category for incident in guardrail.scan_turns(turns)}
    assert "payout_promise" in found


# --------------------------------------------------------------------------
# incident shape and merging
# --------------------------------------------------------------------------
def test_incident_carries_turn_index_severity_and_detector():
    turns = ingest.parse_transcript(
        "Agent: Hello.\nCaller: Will I get money?\nAgent: You will get ₹20,000 for sure."
    )
    incidents = guardrail.scan_turns(turns)
    assert incidents
    incident = incidents[0]
    assert incident.turn_index == 2
    assert incident.severity == "high"
    assert incident.detector == "rules"
    assert "20,000" in incident.text


def test_merge_prefers_rules_and_highest_severity():
    from app.schemas import GuardrailIncident

    rules = [GuardrailIncident(turn_index=1, category="payout_promise", text="a",
                               severity="high", detector="rules")]
    llm = [GuardrailIncident(turn_index=1, category="payout_promise", text="b",
                             severity="low", detector="llm"),
           GuardrailIncident(turn_index=3, category="approval_promise", text="c",
                             severity="medium", detector="llm")]
    merged = guardrail.merge_incidents(rules, llm)
    assert len(merged) == 2
    payout = next(i for i in merged if i.category == "payout_promise")
    assert payout.detector == "rules"
    assert payout.severity == "high"


def test_judge_is_skipped_when_gemini_is_disabled():
    turns = ingest.parse_transcript("Agent: You will get ₹20,000.")
    assert asyncio.run(guardrail.judge_turns(turns)) == []


def test_full_audit_runs_offline_and_still_finds_rule_incidents():
    turns = ingest.parse_transcript("Agent: You will get ₹20,000 within ten days.")
    incidents = asyncio.run(guardrail.audit(turns))
    found = {incident.category for incident in incidents}
    assert "payout_promise" in found
    assert all(incident.detector == "rules" for incident in incidents)


def test_fabricated_scheme_helper():
    incident = guardrail.fabricated_scheme_incident(2, "The Kisan Bonus scheme pays extra", "S99")
    assert incident.category == "fabricated_scheme"
    assert incident.severity == "high"
    assert "S99" in incident.text
