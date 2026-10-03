"""Agent configuration: defaults, merge and validation.

An agent's config is one JSON document shared by every channel. Channel differences
are *rendering* concerns (see render.py), never separate configs.
"""
from __future__ import annotations

import copy
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "persona": {
        "name": "Aria",
        "role": "customer support assistant",
        "prompt": "",
        "greeting": "Hi! I'm {{agent_name}} from {{business_name}}. How can I help you today?",
        "tone": 60,          # 0 = formal/professional, 100 = warm/friendly
        "verbosity": 35,     # 0 = very concise, 100 = detailed
        "goals": [],
        "style_notes": "",
    },
    "business": {"name": "", "description": "", "website": "", "hours": "", "phone": "", "email": "", "address": ""},
    "languages": {"primary": "en-IN", "supported": ["en-IN", "hi-IN"], "auto_detect": True, "mirror_user": True},
    "llm": {"provider": None, "model": None, "voice_model": None, "temperature": 0.3},
    "voice": {
        "voice_id": "edge:en-IN-NeerjaExpressiveNeural",
        "per_language": {"hi-IN": "edge:hi-IN-SwaraNeural"},
        "speed": 1.0,
        "engine": "cascade",         # cascade (STT→LLM→TTS, full control) | gemini_live | openai_realtime (speech-to-speech)
        "s2s_voice": "Aoede",        # voice for speech-to-speech engines
        "stt_provider": "auto",      # auto | groq | openai | deepgram | deepgram_flux | sarvam | whisper_local
        "noise_filter": True,        # RNNoise background-noise suppression on incoming audio
        "voicemail": {"detect": True, "action": "leave_message", "message": "Hi, this is {{agent_name}} from {{business_name}}. Sorry we missed you. Please call us back or reply to our message. Thank you!"},
        "ivr_navigation": False,     # let the agent press keypad keys when it reaches a phone menu
        "interruptions": True,
        "interruption_min_words": 0,
        "end_of_turn": "smart",      # smart (Smart Turn v3) | vad
        "turn_patience_s": 1.2,      # max wait after the caller pauses mid-thought (smart) / silence before replying (vad)
        "filler_words": True,
        "max_call_minutes": 15,
        "silence_timeout_s": 25,
        "hangup_phrases": [],
        "keywords": [],
        "background": "none",
        "first_speaker": "agent",    # agent | user
    },
    "knowledge": {"kb_ids": [], "k": 5, "mode": "auto", "min_confidence": 0.32, "policies": [], "cite_sources": True},
    "tools": {
        "builtin": ["search_knowledge", "query_table", "handoff_to_human", "capture_lead", "create_task",
                    "check_availability", "book_appointment", "send_message", "end_conversation", "get_datetime"],
        "custom_tool_ids": [],
    },
    "handoff": {
        "enabled": True,
        "explicit_request": True,
        "frustration": True,
        "low_confidence_turns": 2,
        "repeat_question": 3,
        "topics": [],
        "team": "support",
        "message": "I'm connecting you with a member of our team now. They'll be with you shortly.",
        "offline_message": "Our team is offline right now. I've logged your request and someone will get back to you as soon as possible.",
        "sla_minutes": 5,
        "on_frustration": True,      # escalate when live emotion stays negative
        "transfer_targets": [],      # [{name, number, mode: warm|cold, description}] for live phone transfers
    },
    "memory": {"cross_channel": True, "remember_facts": True},
    "analysis": {
        "summary": True,
        "extraction": [],
        "dispositions": ["resolved", "interested", "not_interested", "callback_requested", "escalated", "no_answer"],
        "auto_crm": True,
    },
    "guardrails": {"blocked_topics": [], "injection_threshold": 0.85, "pii_redaction": False, "max_reply_chars": 1200},
    "widget": {"color": "#6D5EF8", "position": "right", "title": "", "subtitle": "Typically replies instantly", "voice": True,
               "launcher": "orb", "allowed_domains": [], "starters": []},
    "variables": {},
    "flow": {"enabled": False, "start": None, "nodes": []},
    "squad": {"members": []},        # [{name, agent_id, when}] specialists this agent can hand over to
    "calendar_id": None,
    "calendar_source": "local",      # local | calcom
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def normalize(config: dict | None) -> dict:
    return deep_merge(DEFAULT_CONFIG, config or {})


def fill_vars(text: str, cfg: dict, extra: dict | None = None) -> str:
    values = {
        "agent_name": cfg["persona"].get("name") or "Assistant",
        "business_name": cfg["business"].get("name") or "our company",
        **{k: str(v) for k, v in (cfg.get("variables") or {}).items()},
        **{k: str(v) for k, v in (extra or {}).items()},
    }
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v).replace("{{ " + k + " }}", v)
    return text
