import importlib
import types
import unittest
from unittest.mock import AsyncMock

import test_custom_endpoint as fixtures


collect = importlib.import_module(f"{fixtures.PACKAGE_NAME}.core.forward_refs").collect_forward_images


class ForwardReferencesTest(unittest.IsolatedAsyncioTestCase):
    async def test_reply_resolves_forward_and_nested_records(self):
        async def action(name, **kwargs):
            if name == "get_msg":
                self.assertEqual(kwargs, {"message_id": "42"})
                return {"data": {"message": [{"type": "forward", "data": {"id": "outer"}}]}}
            if kwargs["id"] == "outer":
                return {"messages": [{"content": [
                    {"type": "image", "data": {"url": "https://example.com/a.png"}},
                    {"type": "forward", "data": {"id": "inner"}},
                ]}]}
            return {"data": {"messages": [{"message": [
                {"type": "image", "data": {"url": "https://example.com/b.png"}},
                {"type": "forward", "data": {"id": "outer"}},
            ]}]}}

        call = AsyncMock(side_effect=action)
        event = types.SimpleNamespace(
            bot=types.SimpleNamespace(api=types.SimpleNamespace(call_action=call)),
            message_obj=types.SimpleNamespace(message=[{"type": "reply", "data": {"id": "42"}}]),
        )
        self.assertEqual(await collect(event), ["https://example.com/a.png", "https://example.com/b.png"])
        self.assertEqual(call.await_count, 3)

    async def test_cq_string_and_image_limit(self):
        content = "".join(f"[CQ:image,url=https://example.com/{i}.png]" for i in range(20))
        event = types.SimpleNamespace(message_obj=types.SimpleNamespace(raw_message=content))
        self.assertEqual(len(await collect(event)), 14)

    async def test_failed_forward_keeps_attached_images(self):
        event = types.SimpleNamespace(
            bot=types.SimpleNamespace(call_action=AsyncMock(side_effect=RuntimeError("unsupported"))),
            message_obj=types.SimpleNamespace(message=[
                {"type": "forward", "data": {"id": "missing"}},
                {"type": "image", "data": {"url": "https://example.com/a.png"}},
            ]),
        )
        self.assertEqual(await collect(event), ["https://example.com/a.png"])
