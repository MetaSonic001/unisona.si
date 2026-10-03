"""Voice E2E smoke test (API must be running).

    cd services/api && uv run python tests/e2e_voice.py <agent public key pk_...> reply.wav

Synthesizes a spoken question with Edge TTS, calls the agent over WebRTC like a browser would,
records the agent reply to a WAV. Then check the transcript in the Inbox / Calls page."""
import asyncio, io, sys, wave
import av, edge_tts, httpx, numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRecorder

KEY = sys.argv[1]
OUT = sys.argv[2]
BASE = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8000"
QUESTIONS = ["Hi, what time do you open on Saturday?", "Okay. And is there parking near the clinic?"]
SR = 48000


async def speak(text):
    buf = io.BytesIO()
    async for ch in edge_tts.Communicate(text, "en-IN-PrabhatNeural").stream():
        if ch["type"] == "audio":
            buf.write(ch["data"])
    buf.seek(0)
    return buf


async def make_wav(path):
    segs = []
    for q in QUESTIONS:
        segs.append(await speak(q))
    sil = lambda s: np.zeros(int(SR * s), dtype=np.int16)
    parts = [sil(9)]
    for buf in segs:
        c = av.open(buf)
        rs = av.AudioResampler(format="s16", layout="mono", rate=SR)
        pcm = [r.to_ndarray().flatten() for f in c.decode(audio=0) for r in rs.resample(f)]
        parts += [np.concatenate(pcm).astype(np.int16), sil(12)]
    audio = np.concatenate(parts)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(audio.tobytes())


async def main():
    wav = OUT.replace(".wav", "_in.wav")
    await make_wav(wav)
    pc = RTCPeerConnection()
    player = MediaPlayer(wav)
    rec = MediaRecorder(OUT)
    pc.addTrack(player.audio)

    @pc.on("track")
    def on_track(t):
        print("got remote track", t.kind)
        if t.kind == "audio":
            rec.addTrack(t)

    await pc.setLocalDescription(await pc.createOffer())
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.1)
    async with httpx.AsyncClient(timeout=30) as cl:
        r = await cl.post(f"{BASE}/public/voice/{KEY}/offer",
                          json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "request_data": {"session_id": "e2e-test"}})
        print("offer status", r.status_code)
        ans = r.json()
    await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type=ans["type"]))
    await rec.start()
    await asyncio.sleep(9 + 12 * len(QUESTIONS) + 6)
    await rec.stop()
    await pc.close()
    with wave.open(OUT) as w:
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        print(f"recorded {len(frames) / w.getframerate() / w.getnchannels():.1f}s, peak={np.abs(frames).max() if len(frames) else 0}, "
              f"voiced_seconds={(np.abs(frames) > 1000).sum() / w.getframerate() / w.getnchannels():.2f}")


asyncio.run(main())
