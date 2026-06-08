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
    def test_publish_output_records_popup_image_for_reuse(self) -> None:
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
                        "history_markdown": "The scene holds.",
                        "status_sections": [],
                        "popup": {
                            "id": "map-3",
                            "title": "Known map",
                            "image_path": "assets/map.png",
                            "caption": "Player-known paths.",
                            "display_asset": {
                                "request": "known map",
                                "subject": "Flooded district map",
                                "purpose": "map",
                                "visible_scope": "routes the player has discovered",
                                "reuse_key": "map:flooded-district:known",
                                "canon_refs": ["story/known-routes.md", 2],
                                "reuse_tags": ["map", "routes"],
                                "reuse_notes": "Reuse until a new district is discovered.",
                            },
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
            self.assertEqual(item["reuse_key"], "map:flooded-district:known")
            self.assertEqual(item["canon_refs"], ["story/known-routes.md", "2"])
            self.assertEqual(item["reuse_tags"], ["map", "routes"])
            self.assertEqual(item["reuse_notes"], "Reuse until a new district is discovered.")
            self.assertEqual(item["turn_id"], 3)

    def test_initial_output_has_required_theme_processing_fields(self) -> None:
        output = world_simulator_gui.initial_output("session")

        theme = output["ui_theme"]
        self.assertTrue(theme["processing_message"])
        self.assertTrue(theme["processing_detail"])

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


if __name__ == "__main__":
    unittest.main()
