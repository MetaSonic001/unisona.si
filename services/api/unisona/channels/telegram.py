"""Telegram channel. Long-polling (getUpdates) means it works on localhost without a public URL."""
from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import select

from ..db import SessionLocal
from ..log import get_logger
from ..models import Agent, Channel, Workspace
from .common import channel_secret

log = get_logger("telegram")
API = "https://api.telegram.org/bot{token}/{method}"
_pollers: dict[str, asyncio.Task] = {}


async def call(token: str, method: str, **params) -> dict:
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(API.format(token=token, method=method), json=params)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data.get('description')}")
        return data["result"]


async def get_me(token: str) -> dict:
    return await call(token, "getMe")


async def send(token: str, chat_id: str | int, text: str, options: list[str] | None = None, ask_phone: bool = False) -> dict:
    params: dict = {"chat_id": chat_id, "text": text[:4096]}
    if ask_phone:
        params["reply_markup"] = {"keyboard": [[{"text": "📱 Share my phone number", "request_contact": True}]],
                                  "one_time_keyboard": True, "resize_keyboard": True}
    elif options:
        params["reply_markup"] = {"inline_keyboard": [[{"text": o[:60], "callback_data": o[:60]}] for o in options[:8]]}
    return await call(token, "sendMessage", **params)


async def _handle_update(ch_id: str, upd: dict) -> None:
    from ..brain.identity import add_identity
    from ..brain.respond import Turn, respond

    msg = upd.get("message") or {}
    cb = upd.get("callback_query")
    if cb:
        msg = {"chat": cb["message"]["chat"], "from": cb["from"], "text": cb.get("data", "")}
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return
    user = msg.get("from") or {}
    name = " ".join(x for x in [user.get("first_name"), user.get("last_name")] if x) or user.get("username")
    async with SessionLocal() as db:
        ch = await db.get(Channel, ch_id)
        if not ch or not ch.enabled:
            return
        ws = await db.get(Workspace, ch.workspace_id)
        agent = await db.get(Agent, ch.agent_id)
        token = channel_secret(ws, ch).get("bot_token", "")
        if cb:
            try:
                await call(token, "answerCallbackQuery", callback_query_id=cb["id"])
            except Exception:
                pass
        if msg.get("contact"):  # user shared their phone → link identities across channels
            from ..brain.identity import resolve_contact

            contact = await resolve_contact(db, ws.id, {"telegram_id": chat_id}, name=name, channel="telegram")
            await add_identity(db, contact, "phone", msg["contact"].get("phone_number", ""), verified=True)
            await db.commit()
            await send(token, chat_id, "Thanks! I've linked your phone number, so I'll remember you on calls and WhatsApp too.")
            return
        text = msg.get("text") or msg.get("caption")
        if not text:
            return
        if text.strip() == "/start":
            from ..brain.respond import greeting

            await send(token, chat_id, await greeting(db, agent))
            return
        if text.strip() == "/phone":
            await send(token, chat_id, "Tap the button below to share your phone number.", ask_phone=True)
            return
        await call(token, "sendChatAction", chat_id=chat_id, action="typing")
        reply = await respond(db, Turn(ws=ws, agent=agent, channel="telegram", text=text, identifiers={"telegram_id": chat_id},
                                       name=name, channel_ref=chat_id, channel_msg_id=str(msg.get("message_id", ""))))
        if reply.get("text"):
            await send(token, chat_id, reply["text"], reply.get("options"))


async def _poll(ch_id: str) -> None:
    offset = 0
    backoff = 2
    while True:
        try:
            async with SessionLocal() as db:
                ch = await db.get(Channel, ch_id)
                if not ch or not ch.enabled:
                    log.info(f"Telegram poller {ch_id} stopped (channel disabled)")
                    return
                ws = await db.get(Workspace, ch.workspace_id)
                token = channel_secret(ws, ch).get("bot_token", "")
            updates = await call(token, "getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
            for upd in updates:
                offset = upd["update_id"] + 1
                asyncio.create_task(_safe(ch_id, upd))
            backoff = 2
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.warning(f"Telegram poll error ({ch_id}): {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


async def _safe(ch_id: str, upd: dict):
    try:
        await _handle_update(ch_id, upd)
    except Exception as e:
        log.error(f"Telegram update failed: {e}")


def start_poller(ch_id: str) -> None:
    if ch_id in _pollers and not _pollers[ch_id].done():
        return
    _pollers[ch_id] = asyncio.create_task(_poll(ch_id))
    log.info(f"Telegram poller started for channel {ch_id}")


def stop_poller(ch_id: str) -> None:
    t = _pollers.pop(ch_id, None)
    if t:
        t.cancel()


async def start_all() -> int:
    async with SessionLocal() as db:
        ids = (await db.execute(select(Channel.id).where(Channel.type == "telegram", Channel.enabled.is_(True)))).scalars().all()
    for cid in ids:
        start_poller(cid)
    return len(ids)
