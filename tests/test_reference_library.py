import importlib
import io
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

import test_custom_endpoint as fixtures


main = importlib.import_module(f"{fixtures.PACKAGE_NAME}.main")


class ReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_replacement_and_preview_do_not_cross_groups(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as root:
            plugin = main.OmniDrawPlugin.__new__(main.OmniDrawPlugin)
            plugin.data_dir = root
            def event(group, sender):
                return types.SimpleNamespace(unified_msg_origin=f"qq:GroupMessage:{group}",
                                             get_group_id=lambda: group, get_self_id=lambda: "999", get_sender_id=lambda: sender)
            first, member, other = event("123", "1"), event("123", "2"), event("456", "1")
            first_scope, private = plugin._reference_scopes(first)
            self.assertEqual(first_scope, plugin._reference_scopes(member)[0])
            self.assertNotEqual(first_scope, plugin._reference_scopes(other)[0])
            library = main.ReferenceLibrary(root)
            library.save(first_scope, "塔菲", [("image/png", b"old"), ("image/png", b"old2")])
            library.save(private, "个人", [("image/png", b"private")])
            png = io.BytesIO()
            Image.new("RGB", (10, 10), "red").save(png, "PNG")
            library.save(first_scope, "塔菲", [("image/png", png.getvalue())])
            self.assertEqual(len(library.images(first_scope, "塔菲")), 1)
            self.assertEqual(list(plugin._reference_catalog(library, plugin._reference_scopes(member))), ["塔菲"])
            self.assertEqual(await plugin._add_named_references(other, [], {}, "塔菲"), [])
            card = main.render_reference_card(library.images(first_scope, "塔菲"))
            with Image.open(io.BytesIO(card)) as preview:
                self.assertEqual(preview.format, "PNG")
                self.assertGreater(preview.width, 248)

    async def test_page_can_preview_and_delete_only_selected_scoped_term(self):
        with tempfile.TemporaryDirectory() as root:
            plugin = main.OmniDrawPlugin.__new__(main.OmniDrawPlugin)
            plugin.data_dir = root
            library = main.ReferenceLibrary(root)
            library.save("one", "塔菲", [("image/png", b"one")])
            library.save("two", "塔菲", [("image/png", b"two")])
            key = {"scope": "one", "name": "塔菲"}
            request = types.SimpleNamespace(args={**key, "position": "0"}, get_json=AsyncMock(return_value=key))
            with patch.object(main, "request", request), patch.object(main, "jsonify", lambda result: result):
                listing = await plugin.list_reference_terms_handler()
                self.assertEqual([entry["scope"] for entry in listing["entries"]], ["one", "two"])
                self.assertEqual((await plugin.preview_reference_term_handler())["data_url"], "data:image/png;base64,b25l")
                self.assertTrue((await plugin.delete_reference_term_handler())["success"])
                self.assertEqual((await plugin.preview_reference_term_handler())[1], 404)
                self.assertEqual((await plugin.list_reference_terms_handler())["entries"], [{"scope": "two", "name": "塔菲", "count": 1}])

    async def test_prompt_resolves_saved_images_alongside_current_images(self):
        with tempfile.TemporaryDirectory() as root:
            plugin = main.OmniDrawPlugin.__new__(main.OmniDrawPlugin)
            plugin.data_dir = root
            event = types.SimpleNamespace(
                unified_msg_origin="qq:GroupMessage:123", get_self_id=lambda: "999", get_sender_id=lambda: "456",
            )
            library = main.ReferenceLibrary(root)
            library.save(plugin._reference_scope(event), "塔菲", [("image/png", b"taffy")])
            library.save(plugin._reference_scope(event), "塔菲猫", [("image/png", b"cat")])
            for prompt in ("塔菲", "塔菲在耕作", "画一张塔菲在耕作的图"):
                self.assertEqual(
                    await plugin._add_named_references(event, ["current.png"], {}, prompt),
                    ["current.png", "data:image/png;base64,dGFmZnk="],
                )
            self.assertEqual(
                await plugin._add_named_references(event, [], {}, "塔菲猫在耕作"),
                ["data:image/png;base64,Y2F0"],
            )
            event.get_sender_id = lambda: "other"
            self.assertEqual(await plugin._add_named_references(event, ["current.png"], {}, "塔菲"), ["current.png"])

    async def test_avatars_follow_message_roles_and_ignore_quoted_mentions(self):
        plugin_type = main.OmniDrawPlugin
        plugin = plugin_type.__new__(plugin_type)
        plugin._command_prefixes = lambda: ["/"]
        actor, target = main.At("123"), main.At("456")
        actor.name = target.name = "同名"
        event = types.SimpleNamespace(
            get_self_id=lambda: "999",
            message_obj=types.SimpleNamespace(
                message=[main.At("999"), main.Plain("/画 "), actor, main.Plain("推倒"), target],
                quote=types.SimpleNamespace(message=[main.At("789")]),
            ),
        )
        command = plugin._mention_command_text(event, "画")
        self.assertRegex(command, r"【人物1】\s*推倒\s*【人物2】")
        refs = await plugin._get_event_reference_images(event, include_at_avatars=True, at_after_command="画")
        self.assertEqual(refs, [plugin._build_qq_avatar_url(uid) for uid in ("123", "456")])
        prompt = plugin._bind_avatar_prompt(event, command, refs, ["a.png", "b.png"], "画")
        self.assertIn("QQ 123），外观使用第 1 张", prompt)
        self.assertIn("QQ 456），外观使用第 2 张", prompt)
        with self.assertRaises(ValueError):
            plugin._bind_avatar_prompt(event, command, refs, ["b.png"], "画")

    async def test_persistent_reference_sets_are_scoped_and_ordered(self):
        with tempfile.TemporaryDirectory() as root:
            main.ReferenceLibrary(root).save("group:user1", "双人", [("image/png", b"a"), ("image/png", b"b")])
            restarted = main.ReferenceLibrary(root)
            self.assertEqual(restarted.names("group:user1"), ["双人"])
            self.assertEqual(restarted.load("group:user1", "双人"), ["data:image/png;base64,YQ==", "data:image/png;base64,Yg=="])
            self.assertEqual(restarted.load("group:user2", "双人"), [])
            with self.assertRaises(ValueError):
                restarted.save("group:user1", "双人", [])
            self.assertEqual(len(restarted.load("group:user1", "双人")), 2)
            self.assertTrue(restarted.delete("group:user1", "双人"))
            self.assertEqual(restarted.names("group:user1"), [])
