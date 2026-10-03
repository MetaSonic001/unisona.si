"""Voice simulations: real calls to an agent with synthetic callers (accents, background noise, barge-in).

Each scenario synthesizes caller lines with an accent voice, mixes in noise, places a WebRTC call to the
agent exactly like a browser would, then scores:
  - transcription accuracy (word error rate of what the agent heard vs what was said)
  - latency (silence after the caller stops, from the call's own measurements)
  - conversation quality (LLM judge on the real transcript)
This tests the whole stack (VAD, turn detection, STT, RAG, LLM, TTS) the way customers experience it.
"""
from __future__ import annotations

import asyncio
import io
import re
import tempfile
import uuid
import wave
from pathlib import Path

import numpy as np
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal, utcnow
from ..log import get_logger
from ..models import Agent, Call, Conversation, EvalRun, EvalSuite, Message, Workspace
from ..providers.llm import get_llm

log = get_logger("voice-eval")
SR = 48000
ACCENTS = {"indian_english": "en-IN-PrabhatNeural", "indian_english_f": "en-IN-NeerjaNeural", "hindi": "hi-IN-MadhurNeural",
           "us_english": "en-US-GuyNeural", "uk_english": "en-GB-RyanNeural", "tamil": "ta-IN-ValluvarNeural", "australian": "en-AU-WilliamNeural"}
DEFAULT_SCENARIOS = [
    {"name": "Indian English, quiet room", "accent": "indian_english", "noise": 0.0, "barge_in": False,
     "lines": ["Hi, what are your opening hours on Saturday?", "Okay, and do you have parking nearby?"]},
    {"name": "Hindi caller, street noise", "accent": "hindi", "noise": 0.08, "barge_in": False,
     "lines": ["नमस्ते, रूट कैनाल का खर्चा कितना है?", "ठीक है, धन्यवाद।"]},
    {"name": "Impatient caller interrupts the greeting", "accent": "us_english", "noise": 0.03, "barge_in": True,
     "lines": ["Sorry to cut in, I need to book a cleaning this week.", "Thursday afternoon works."]},
]
JUDGE = """You grade a phone call between an AI agent and a customer. Return JSON:
{"helpfulness": 0-1, "naturalness": 0-1, "handled_interruptions": 0-1, "understood_caller": 0-1, "summary": "one sentence"}.
understood_caller = how well the transcribed customer lines match what the customer actually said (given below), ignoring script/transliteration differences.
helpfulness = did the agent address each request correctly; naturalness = short, spoken-style replies; handled_interruptions = it recovered gracefully if cut off."""


_TOKEN = re.compile(r"[\w\u0900-\u0DFF]+")


def _script(text: str) -> str:
    return "latin" if re.search(r"[A-Za-z]", text) and not re.search(r"[\u0900-\u0DFF]", text) else "indic" if re.search(r"[\u0900-\u0DFF]", text) else "other"


def wer(ref: str, hyp: str) -> float:
    r, h = _TOKEN.findall(ref.lower()), _TOKEN.findall(hyp.lower())
    if not r:
        return 0.0
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0], d[0, :] = range(len(r) + 1), range(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return round(float(d[-1, -1]) / len(r), 3)


async def _speech(text: str, voice: str) -> np.ndarray:
    import av
    import edge_tts

    buf = io.BytesIO()
    async for ch in edge_tts.Communicate(text, voice).stream():
        if ch["type"] == "audio":
            buf.write(ch["data"])
    buf.seek(0)
    c = av.open(buf)
    rs = av.AudioResampler(format="s16", layout="mono", rate=SR)
    pcm = [r.to_ndarray().flatten() for f in c.decode(audio=0) for r in rs.resample(f)]
    return np.concatenate(pcm).astype(np.int16)


def _noise(n: int, level: float) -> np.ndarray:
    if level <= 0:
        return np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(7)
    babble = np.convolve(rng.standard_normal(n), np.ones(40) / 40, mode="same")  # low-passed "street" rumble
    return (babble / (np.abs(babble).max() or 1) * level * 32767).astype(np.float32)


async def _caller_audio(sc: dict, path: Path) -> list[float]:
    """Build the caller's side of the call as one WAV; returns the start time of each line."""
    voice = ACCENTS.get(sc.get("accent", "indian_english"), sc.get("accent"))
    lead = 1.5 if sc.get("barge_in") else 8.0  # barge-in speaks over the agent's greeting
    sil = lambda secs: np.zeros(int(SR * secs), dtype=np.int16)  # noqa: E731
    parts, starts, t = [sil(lead)], [], lead
    for line in sc["lines"]:
        sp = await _speech(line, voice)
        starts.append(t)
        parts += [sp, sil(11)]
        t += len(sp) / SR + 11
    audio = np.concatenate(parts).astype(np.float32)
    audio = np.clip(audio + _noise(len(audio), float(sc.get("noise", 0))), -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(audio.tobytes())
    return starts


async def _call(public_key: str, wav: Path, seconds: float, session_id: str) -> None:
    import httpx
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaBlackhole, MediaPlayer

    pc = RTCPeerConnection()
    player, sink = MediaPlayer(str(wav)), MediaBlackhole()
    pc.addTrack(player.audio)

    @pc.on("track")
    def on_track(track):
        sink.addTrack(track)

    await pc.setLocalDescription(await pc.createOffer())
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.05)
    base = f"http://127.0.0.1:{settings.api_port}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{base}/public/voice/{public_key}/offer", json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type,
                                                                            "request_data": {"session_id": session_id}})
        r.raise_for_status()
        ans = r.json()
    await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type=ans["type"]))
    await sink.start()
    await asyncio.sleep(seconds)
    await sink.stop()
    await pc.close()


async def run_scenario(ws: Workspace, agent: Agent, sc: dict, judge) -> dict:
    session_id = f"voice-eval-{uuid.uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "caller.wav"
        await _caller_audio(sc, wav)
        with wave.open(str(wav)) as w:
            seconds = w.getnframes() / w.getframerate() + 4
        await _call(agent.public_key, wav, seconds, session_id)
    await asyncio.sleep(6)  # let the call finalize and transcripts flush
    async with SessionLocal() as db:
        conv = (await db.execute(select(Conversation).where(Conversation.workspace_id == ws.id, Conversation.channel_ref == session_id)
                                 .order_by(Conversation.started_at.desc()))).scalars().first()
        if not conv:
            return {"scenario": sc["name"], "error": "call did not connect", "passed": False}
        msgs = (await db.execute(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at))).scalars().all()
        call = (await db.execute(select(Call).where(Call.conversation_id == conv.id))).scalars().first()
    heard = [m.content for m in msgs if m.role == "user"]
    heard_all = " ".join(heard)
    wers = [min((wer(line, h) for h in heard), default=1.0) if heard else 1.0 for line in sc["lines"]]
    wers_joined = wer(" ".join(sc["lines"]), heard_all) if heard else 1.0
    lat = (call.metrics or {}).get("latencies_ms", []) if call else []
    transcript = "\n".join(f"{'Customer' if m.role == 'user' else 'Agent'}: {m.content}" for m in msgs)
    said = "\n".join(sc["lines"])
    verdict = await judge.json(JUDGE, f"Caller accent: {sc.get('accent')}, noise: {sc.get('noise')}, barge-in: {sc.get('barge_in')}\n"
                                      f"What the customer actually said:\n{said}\n\nCall transcript (customer lines as the agent heard them):\n{transcript}",
                               purpose="eval") if judge.available else {}
    word_error = round(min(float(np.mean(wers)), wers_joined), 3)
    if heard and _script(said) != _script(heard_all) and "understood_caller" in verdict:
        # e.g. Hindi spoken, transcribed in Latin script: word matching is meaningless, use the judge's comparison
        word_error = round(1 - float(verdict["understood_caller"]), 3)
    avg_lat = int(np.mean(lat)) if lat else None
    passed = word_error <= 0.35 and (avg_lat or 0) <= 3000 and float(verdict.get("helpfulness", 1)) >= 0.6
    return {"scenario": sc["name"], "accent": sc.get("accent"), "noise": sc.get("noise"), "barge_in": sc.get("barge_in"),
            "word_error_rate": word_error, "avg_latency_ms": avg_lat, "p95_latency_ms": int(np.percentile(lat, 95)) if lat else None,
            "scores": {k: v for k, v in verdict.items() if k != "summary"}, "summary": verdict.get("summary", ""),
            "transcript": transcript[:4000], "conversation_id": conv.id, "passed": passed}


async def run_voice_eval(run_id: str) -> dict:
    async with SessionLocal() as db:
        run = await db.get(EvalRun, run_id)
        ws, agent = await db.get(Workspace, run.workspace_id), await db.get(Agent, run.agent_id)
        suite = await db.get(EvalSuite, run.suite_id) if run.suite_id else None
        run.status = "running"
        await db.commit()
        judge = await get_llm(db, ws, feature="voice evaluations")
    scenarios = (suite.cases if suite and suite.cases else None) or DEFAULT_SCENARIOS
    results = []
    for sc in scenarios:
        try:
            results.append(await run_scenario(ws, agent, sc, judge))
        except Exception as e:
            log.warning(f"Voice scenario {sc.get('name')} failed: {e}")
            results.append({"scenario": sc.get("name"), "error": str(e)[:300], "passed": False})
    ok = [r for r in results if "error" not in r]
    summary = {"pass_rate": round(sum(r["passed"] for r in results) / max(1, len(results)), 3),
               "avg_word_error_rate": round(float(np.mean([r["word_error_rate"] for r in ok])), 3) if ok else None,
               "avg_latency_ms": int(np.mean([r["avg_latency_ms"] for r in ok if r["avg_latency_ms"]])) if any(r.get("avg_latency_ms") for r in ok) else None}
    async with SessionLocal() as db:
        run = await db.get(EvalRun, run_id)
        run.results, run.scores, run.status, run.finished_at = results, summary, "completed", utcnow()
        await db.commit()
    log.info(f"Voice eval for {agent.name}: {summary}")
    return summary
