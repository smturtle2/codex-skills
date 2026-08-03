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

if __name__ == "__main__":
    unittest.main()
