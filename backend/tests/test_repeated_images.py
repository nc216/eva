import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app import openai_client, store
from app.image_intent import resolve_image_request
from app.main import app, build_image_prompt, build_image_reply


class RepeatedImageTests(unittest.TestCase):
    def setUp(self) -> None:
        store._sessions.clear()

        async def fake_generate_image_bytes(user_message: str, image_style_prompt: str) -> bytes:
            return b"fakepng"

        async def fake_generate_text_reply(
            system_prompt: str,
            transcript: list[dict],
            user_message: str,
            temperature: float,
        ) -> str:
            return "I took another picture for you."

        openai_client.generate_image_bytes = fake_generate_image_bytes
        openai_client.generate_text_reply = fake_generate_text_reply
        self.client = TestClient(app)

    def test_repeat_request_preserves_image_path_after_session_recovery(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        first = self.client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "message": "send me a pic of u"},
        ).json()
        self.assertEqual(first["kind"], "image")
        store._sessions.clear()
        second = self.client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "message": "send another"},
        ).json()
        self.assertEqual(second["kind"], "image")
        self.assertTrue(second["image_url"])
        self.assertEqual(second["reply"], "I took another picture for you.")

    def test_repeat_request_carries_requested_change(self) -> None:
        history = [
            {
                "role": "assistant",
                "content": "I took a picture for you.",
                "metadata": {
                    "kind": "image",
                    "preset": "self_portrait",
                    "image_url": "/generated-images/test.png",
                },
            }
        ]
        result = resolve_image_request(
            "send another but stand up this time",
            history,
            True,
        )
        self.assertEqual(result["preset"], "self_portrait")
        self.assertTrue(result["variation"])
        self.assertEqual(
            result["requested_change"],
            "send another but stand up this time",
        )

    def test_photo_adjustment_without_send_still_triggers_new_self_photo(self) -> None:
        history = [
            {
                "role": "assistant",
                "content": "I took a picture for you.",
                "metadata": {
                    "kind": "image",
                    "preset": "self_portrait",
                    "image_url": "/generated-images/test.png",
                },
            }
        ]
        result = resolve_image_request("stand up this time", history, True)
        self.assertEqual(result["preset"], "self_portrait")
        self.assertTrue(result["variation"])

    def test_build_image_prompt_includes_requested_change_and_color_lock(self) -> None:
        session = store.create_session(study_condition="A")
        prompt = build_image_prompt(
            session,
            session["config_snapshot"],
            {
                "preset": "self_portrait",
                "variation": True,
                "requested_change": "stand up this time",
            },
        )
        self.assertIn("Apply this requested change", prompt)
        self.assertIn("stand up this time", prompt)
        self.assertIn("Color lock:", prompt)
        self.assertIn("Wardrobe lock is mandatory", prompt)
        self.assertIn("Do not improvise a new top", prompt)

    def test_repeat_photo_reply_uses_human_language(self) -> None:
        self.assertEqual(
            build_image_reply({"variation": True}, 1),
            "I took another picture for you.",
        )
        self.assertEqual(
            build_image_reply({}, 0),
            "I took a picture for you.",
        )

    def test_legacy_signature_outfit_strings_are_upgraded_to_color_locked_dicts(self) -> None:
        upgraded = store.normalize_signature_outfit(
            "a sleeveless fitted top with a casual skirt and understated everyday jewelry"
        )
        self.assertEqual(upgraded["top_color"], "olive")
        self.assertEqual(upgraded["bottom_color"], "black")
        self.assertEqual(upgraded["accessory_color"], "silver")


if __name__ == "__main__":
    unittest.main()
