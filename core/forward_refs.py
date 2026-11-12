"""Bounded traversal of OneBot reply and merged-forward message references."""

import asyncio
import html
import re
from typing import Any

from astrbot.api import logger


async def collect_forward_images(event: Any) -> list[str]:
    bot = getattr(event, "bot", None)
    call = getattr(bot, "call_action", None)
    if not callable(call):
        api = getattr(bot, "api", None)
        call = getattr(api, "call_action", None)

    images: list[str] = []
    visited: set[int] = set()
    retained: list[Any] = []
    fetched: set[tuple[str, str]] = set()
    remaining = 2000

    async def fetch(action: str, key: str, value: Any, depth: int) -> None:
        token = (action, str(value))
        if not callable(call) or not value or token in fetched or len(fetched) >= 12:
            return
        fetched.add(token)
        try:
            result = await asyncio.wait_for(call(action, **{key: value}), timeout=8)
            await walk(result, depth + 1)
        except Exception as exc:
            # A failed record must not discard directly attached reference images.
            logger.warning(f"[OmniDraw] 读取引用/合并转发失败 ({action}, {type(exc).__name__})")

    async def walk(obj: Any, depth: int = 0) -> None:
        nonlocal remaining
        if obj is None or depth > 24 or remaining <= 0 or len(images) >= 14:
            return
        remaining -= 1
        if isinstance(obj, str):
            # OneBot may return CQ strings instead of message-segment arrays.
            for match in re.finditer(r"\[CQ:(image|forward|reply),([^\]]*)\]", obj):
                data = {}
                for pair in match.group(2).split(","):
                    key, sep, value = pair.partition("=")
                    if sep:
                        data[key] = html.unescape(value)
                await walk({"type": match.group(1), "data": data}, depth + 1)
            return
        if id(obj) in visited:
            return
        visited.add(id(obj))
        retained.append(obj)  # Keep temporary CQ segments alive to prevent id reuse.
        if isinstance(obj, (list, tuple)):
            for item in obj:
                await walk(item, depth + 1)
            return
        if isinstance(obj, dict):
            kind = str(obj.get("type", "")).lower()
            data = obj.get("data", obj)
        else:
            kind = type(obj).__name__.lower()
            data = vars(obj) if hasattr(obj, "__dict__") else {}
        if not isinstance(data, dict):
            data = {}
        if kind == "image":
            ref = data.get("url") or data.get("file")
            if isinstance(ref, str) and ref.startswith(("https://", "http://", "data:image/")):
                if ref not in images:
                    images.append(ref)
            return
        if kind in {"forward", "reply"}:
            await fetch(
                "get_forward_msg" if kind == "forward" else "get_msg",
                "id" if kind == "forward" else "message_id",
                data.get("id") or data.get("message_id"),
                depth,
            )
        # Traverse only message-bearing fields, never the bot/context object graph.
        for key in ("message", "messages", "content", "data", "nodes", "quote", "chain", "raw_message"):
            value = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
            if value is not None and value is not obj:
                await walk(value, depth + 1)

    try:
        await asyncio.wait_for(walk(getattr(event, "message_obj", None)), timeout=20)
    except asyncio.TimeoutError:
        logger.warning("[OmniDraw] 合并转发解析超时，使用已提取的参考图")
    return images
