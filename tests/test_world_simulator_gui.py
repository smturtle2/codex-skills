from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "world-simulator" / "scripts" / "world_simulator_gui.py"

spec = importlib.util.spec_from_file_location("world_simulator_gui", SCRIPT)
world_simulator_gui = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(world_simulator_gui)


class WorldSimulatorGuiTests(unittest.TestCase):
    def test_omitted_session_generates_pending_session_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)

            session_path = world_simulator_gui.resolve_session(root, None, create_new=True)

            self.assertEqual(session_path.parent, root)
            self.assertRegex(session_path.name, r"^pending-world-\d{8}-\d{6}$")

    def test_rename_session_moves_pending_session_and_updates_active_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            session_path = root / "pending-world-20260621-123456"
            world_simulator_gui.init_session(session_path)
            world_simulator_gui.write_active_session(root, session_path)

            renamed_path = world_simulator_gui.rename_session(root, session_path, "Neon Rain City")

            self.assertEqual(renamed_path, root / "neon-rain-city")
            self.assertFalse(session_path.exists())
            self.assertTrue(renamed_path.exists())
            self.assertEqual(world_simulator_gui.resolve_session(root, None), renamed_path)
            self.assertEqual(
                json.loads((renamed_path / "ui" / "gui_state.json").read_text(encoding="utf-8"))["session_id"],
                "neon-rain-city",
            )

    def test_active_or_launch_session_follows_renamed_active_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            launch_path = root / "pending-world-20260621-123456"
            renamed_path = root / "neon-rain-city"
            world_simulator_gui.write_active_session(root, renamed_path)

            self.assertEqual(world_simulator_gui.active_or_launch_session(root, launch_path, True), renamed_path)
            self.assertEqual(world_simulator_gui.active_or_launch_session(root, launch_path, False), renamed_path)

    def test_active_or_launch_session_keeps_explicit_final_session_fixed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            launch_path = root / "neon-rain-city"
            active_path = root / "other-world"
            world_simulator_gui.write_active_session(root, active_path)

            self.assertEqual(world_simulator_gui.active_or_launch_session(root, launch_path, False), launch_path)

    def test_gui_launch_does_not_overwrite_final_active_with_old_temporary_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            launch_path = root / "pending-world-20260621-123456"
            active_path = root / "neon-rain-city"
            world_simulator_gui.init_session(active_path)
            world_simulator_gui.write_active_session(root, active_path)

            self.assertFalse(world_simulator_gui.should_write_gui_active_session(root, launch_path, True))

    def test_gui_launch_can_mark_temporary_session_active_before_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            launch_path = root / "pending-world-20260621-123456"

            self.assertTrue(world_simulator_gui.should_write_gui_active_session(root, launch_path, True))

    def test_omitted_bridge_session_uses_active_session_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            session_path = root / "world-20260621-123456"

            world_simulator_gui.write_active_session(root, session_path)

            self.assertEqual(world_simulator_gui.resolve_session(root, None), session_path)

    def test_omitted_bridge_session_requires_active_session_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(world_simulator_gui.WorldSimulatorError):
                world_simulator_gui.resolve_session(pathlib.Path(tmpdir), None)

    def test_publish_output_records_history_illustration_for_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"
            asset_path = session_path / "assets" / "map.png"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(b"image")
            payload_path = pathlib.Path(tmpdir) / "payload.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "phase": "play",
                        "turn_id": 3,
                        "language": "en",
                        "status_sections": [],
                        "history_entry": {
                            "blocks": [
                                {
                                    "type": "illustration",
                                    "asset_id": "map-3",
                                    "title": "Known map",
                                    "image_path": "assets/map.png",
                                    "caption": "Player-known paths.",
                                    "source": "user_show",
                                    "display_asset": {
                                        "request": "known map",
                                        "subject": "Flooded district map",
                                        "purpose": "map",
                                        "visible_scope": "routes the player has discovered",
                                        "visual_summary": "A public route map of the flooded district.",
                                        "reuse_key": "map:flooded-district:known",
                                        "canon_refs": ["story/known-routes.md", 2],
                                        "reuse_tags": ["map", "routes"],
                                        "reuse_notes": "Reuse until a new district is discovered.",
                                    },
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            world_simulator_gui.publish_output(session_path, payload_path)

            registry = json.loads((session_path / "ui" / "display_assets.json").read_text(encoding="utf-8"))
            self.assertEqual(registry["session_id"], "session")
            self.assertEqual(len(registry["items"]), 1)
            item = registry["items"][0]
            self.assertEqual(item["id"], "map-3")
            self.assertEqual(item["title"], "Known map")
            self.assertEqual(item["image_path"], "assets/map.png")
            self.assertEqual(item["caption"], "Player-known paths.")
            self.assertEqual(item["request"], "known map")
            self.assertEqual(item["subject"], "Flooded district map")
            self.assertEqual(item["purpose"], "map")
            self.assertEqual(item["visible_scope"], "routes the player has discovered")
            self.assertEqual(item["visual_summary"], "A public route map of the flooded district.")
            self.assertEqual(item["reuse_key"], "map:flooded-district:known")
            self.assertEqual(item["canon_refs"], ["story/known-routes.md", "2"])
            self.assertEqual(item["reuse_tags"], ["map", "routes"])
            self.assertEqual(item["reuse_notes"], "Reuse until a new district is discovered.")
            self.assertEqual(item["turn_id"], 3)
            history = world_simulator_gui.web_history(session_path)
            self.assertEqual(history["items"][0]["blocks"][0]["type"], "illustration")
            self.assertEqual(history["items"][0]["blocks"][0]["image_path"], "assets/map.png")
            self.assertEqual(history["items"][0]["blocks"][0]["codex_visibility"], "manual_only")

    def test_publish_output_records_history_entry_for_cumulative_gui_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"
            payload_path = pathlib.Path(tmpdir) / "payload.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "phase": "play",
                        "turn_id": 1,
                        "language": "en",
                        "history_entry": {
                            "label": "North Gate",
                            "blocks": [
                                {
                                    "type": "prose",
                                    "markdown": "Rain cuts across the gatehouse.",
                                }
                            ],
                        },
                        "status_sections": [],
                    }
                ),
                encoding="utf-8",
            )

            world_simulator_gui.publish_output(session_path, payload_path)

            log = json.loads((session_path / "ui" / "history_log.json").read_text(encoding="utf-8"))
            self.assertEqual(log["session_id"], "session")
            self.assertEqual(log["last_seq"], 1)
            self.assertEqual([item["turn_id"] for item in log["items"]], [1])
            self.assertEqual(log["items"][0]["label"], "North Gate")
            self.assertEqual(log["items"][0]["blocks"][0]["markdown"], "Rain cuts across the gatehouse.")

    def test_publish_output_upserts_history_entry_by_turn_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"
            first_payload = pathlib.Path(tmpdir) / "first.json"
            second_payload = pathlib.Path(tmpdir) / "second.json"
            first_payload.write_text(
                json.dumps(
                    {
                        "phase": "play",
                        "turn_id": 2,
                        "language": "en",
                        "history_entry": {"blocks": [{"type": "prose", "markdown": "First version."}]},
                        "status_sections": [],
                    }
                ),
                encoding="utf-8",
            )
            second_payload.write_text(
                json.dumps(
                    {
                        "phase": "play",
                        "turn_id": 2,
                        "language": "en",
                        "history_entry": {"blocks": [{"type": "prose", "markdown": "Revised version."}]},
                        "status_sections": [],
                    }
                ),
                encoding="utf-8",
            )

            world_simulator_gui.publish_output(session_path, first_payload)
            world_simulator_gui.publish_output(session_path, second_payload)

            entries = world_simulator_gui.list_history_entries(session_path)
            self.assertEqual([entry["turn_id"] for entry in entries], [2])
            self.assertEqual(entries[-1]["blocks"][0]["markdown"], "Revised version.")

    def test_init_session_does_not_create_authored_initial_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"

            world_simulator_gui.init_session(session_path)

            self.assertFalse((session_path / "ui" / "latest_output.json").exists())
            self.assertFalse((session_path / "current" / "start-here.md").exists())
            self.assertEqual(world_simulator_gui.web_history(session_path)["items"], [])

    def test_publish_output_can_seed_codex_authored_initial_gui_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"
            payload_path = pathlib.Path(tmpdir) / "start.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "phase": "world_concept",
                        "turn_id": 0,
                        "language": "ko",
                        "history_entry": {
                            "id": "codex:start",
                            "turn_id": 0,
                            "label": "시작",
                            "blocks": [{"type": "prose", "markdown": "처음부터 작성한 시작 안내."}],
                        },
                        "status_sections": [{"kind": "setup", "title": "시작", "body": "대기 중"}],
                        "ui_theme": {
                            "title": "월드 시뮬레이터",
                            "history_title": "기록",
                            "status_title": "상태",
                            "input_title": "입력",
                            "input_placeholder": "입력",
                            "send_label": "보내기",
                            "processing_message": "처리 중",
                            "processing_detail": "반영 중",
                            "palette": world_simulator_gui.DEFAULT_THEME,
                        },
                    }
                ),
                encoding="utf-8",
            )

            world_simulator_gui.publish_output(session_path, payload_path)

            latest = json.loads((session_path / "ui" / "latest_output.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["language"], "ko")
            self.assertEqual(world_simulator_gui.web_history(session_path)["items"][0]["id"], "codex:start")

    def test_web_state_exposes_display_assets_and_command_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"
            asset_path = session_path / "assets" / "sheet.png"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(b"image")
            world_simulator_gui.atomic_write_json(
                session_path / "ui" / "display_assets.json",
                {
                    "session_id": "session",
                    "items": [
                        {
                            "id": "sheet",
                            "title": "Character sheet",
                            "image_path": "assets/sheet.png",
                            "caption": "Known details.",
                            "turn_id": 2,
                            "created_at": "2026-01-01T00:00:00Z",
                            "last_seen_at": "2026-01-01T00:00:00Z",
                        }
                    ],
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            )

            state = world_simulator_gui.web_state(session_path)

            self.assertEqual(state["display_assets"][0]["image_path"], "assets/sheet.png")
            self.assertEqual(state["history"]["count"], 0)
            self.assertIn("/show", state["command_help"]["markdown"])
            self.assertIn("helpButton", world_simulator_gui.WEB_HTML)

    def test_display_asset_registry_ignores_missing_and_outside_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"
            valid_asset = session_path / "assets" / "valid.png"
            valid_asset.parent.mkdir(parents=True, exist_ok=True)
            valid_asset.write_bytes(b"image")
            outside_asset = pathlib.Path(tmpdir) / "outside.png"
            outside_asset.write_bytes(b"outside")
            world_simulator_gui.atomic_write_json(
                session_path / "ui" / "display_assets.json",
                {
                    "session_id": "session",
                    "items": [
                        {"title": "Valid", "image_path": "assets/valid.png"},
                        {"title": "Missing", "image_path": "assets/missing.png"},
                        {"title": "Outside", "image_path": str(outside_asset)},
                    ],
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            )

            assets = world_simulator_gui.list_display_assets(session_path)

            self.assertEqual([asset["title"] for asset in assets], ["Valid"])
            self.assertEqual(assets[0]["image_path"], "assets/valid.png")

    def test_malformed_display_asset_registry_does_not_block_web_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"
            registry_path = session_path / "ui" / "display_assets.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text("{not json", encoding="utf-8")

            state = world_simulator_gui.web_state(session_path)

            self.assertEqual(state["display_assets"], [])
            self.assertIn("/show", state["command_help"]["markdown"])

    def test_malformed_history_log_does_not_block_web_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = pathlib.Path(tmpdir) / "session"
            world_simulator_gui.init_session(session_path)
            (session_path / "ui" / "history_log.json").write_text("{not json", encoding="utf-8")

            state = world_simulator_gui.web_state(session_path)

            self.assertEqual(state["history"]["count"], 0)
            self.assertEqual(world_simulator_gui.web_history(session_path)["items"], [])


if __name__ == "__main__":
    unittest.main()
