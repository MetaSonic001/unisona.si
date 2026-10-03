"""Unit tests for compliance, emotion, flows and voice-eval helpers (no network, no DB)."""
import pytest

from unisona.brain import emotion, flows
from unisona.brain.agent_config import normalize
from unisona.evals.voice_sim import _script, wer
from unisona.services.compliance import is_opt_out, normalize as norm_addr
from unisona.voice.session import _MEANINGFUL, _VOICEMAIL


@pytest.mark.parametrize("text", ["STOP", "Please stop messaging me", "don't call me again", "call mat karo", "message band karo please",
                                  "मुझे कॉल मत करो", "remove my number from your list"])
def test_opt_out_detected(text):
    assert is_opt_out(text)


@pytest.mark.parametrize("text", ["Can you stop by tomorrow?", "What time do you close?", "Please call me back at 5", "band ka naam kya hai"])
def test_not_opt_out(text):
    assert not is_opt_out(text)


def test_address_normalization():
    assert norm_addr("+91 98765 43210") == norm_addr("098765-43210") == "9876543210"
    assert norm_addr("A@B.com ") == "a@b.com"


def test_emotion_and_escalation():
    assert emotion.score("This is the worst service, total scam!!!")["label"] == "angry"
    assert emotion.score("Thank you so much, very helpful")["label"] == "happy"
    assert emotion.score("What are your timings?")["label"] == "neutral"
    hist, esc = emotion.trend([], emotion.score("kitni baar bolu, still not working"))
    hist, esc = emotion.trend(hist, emotion.score("third time asking, nobody replied"))
    assert esc


def _flow_cfg():
    cfg = normalize({})
    cfg["flow"] = {"enabled": True, "start": "a", "nodes": [
        {"id": "a", "title": "Qualify", "instructions": "Ask budget", "collect": [{"name": "budget", "description": "", "required": True}],
         "transitions": [{"to": "b", "when": "budget known"}]},
        {"id": "b", "title": "Book", "instructions": "Book", "transitions": [], "action": "end"}]}
    return cfg


def test_flow_requires_collection_then_advances():
    cfg = _flow_cfg()
    st = flows.initial_state(cfg)
    assert "Qualify" in flows.prompt_section(cfg, st)
    st2, msg = flows.goto(cfg, st, "b")
    assert st2["node"] == "a" and "budget" in msg
    st, _ = flows.save(cfg, st, "budget", "50k")
    st, _ = flows.goto(cfg, st, "b")
    assert st["node"] == "b"
    assert {t["function"]["name"] for t in flows.tool_schemas(_flow_cfg(), flows.initial_state(cfg))} == {"flow_goto", "flow_save"}


def test_flow_rejects_unreachable_step():
    cfg = _flow_cfg()
    st, msg = flows.goto(cfg, flows.initial_state(cfg), "nope")
    assert st["node"] == "a" and "not reachable" in msg


def test_voice_helpers():
    assert wer("रूट कैनाल का खर्चा", "रूट कैनाल का खर्चा") == 0.0
    assert wer("open on saturday", "open on sunday") == pytest.approx(1 / 3, abs=0.01)
    assert _script("Namaste root canal") == "latin" and _script("रूट कैनाल") == "indic"
    assert not _MEANINGFUL.search("।") and _MEANINGFUL.search("हाँ") and _MEANINGFUL.search("ok")
    assert _VOICEMAIL.search("Please leave a message after the beep") and _VOICEMAIL.search("aapka call abhi vyast hai")
    assert not _VOICEMAIL.search("Hello, who is this?")
