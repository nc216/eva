import unittest
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app import openai_client, store
from app.image_intent import resolve_image_request
from app.main import (
    app,
    build_image_prompt,
    build_image_reply,
    has_explicit_location_request,
    is_different_location_request,
    maybe_append_survey_code,
)


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

    def test_repeat_pic_request_does_not_read_internal_prompt_as_location_change(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        restored["localized_scene"] = {
            "label": "a bright home kitchen in late morning",
            "prompt": "a bright home kitchen in late morning with soft daylight",
        }
        store.add_message(
            session["session_id"],
            "assistant",
            "I took a picture for you.",
            metadata={
                "kind": "image",
                "preset": "self_portrait",
                "image_url": "/generated-images/test.png",
                "image_prompt": (
                    "Keep the image grounded in this same setting. "
                    "Do not move the subject to a different requested location: "
                    "a bright home kitchen in late morning."
                ),
            },
        )
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "send me another pic",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "image")
        self.assertTrue(response["image_url"])
        self.assertEqual(response["reply"], "I took another picture for you.")

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
        self.assertIn("CRITICAL WARDROBE LOCK", prompt)
        self.assertIn("Do not show a phone", prompt)
        self.assertIn("not a phone selfie or mirror selfie", prompt)

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

    def test_visual_identity_is_locked_to_white_adult_woman(self) -> None:
        session = store.create_session(study_condition="A")
        self.assertIn("white adult woman", session["visual_identity"])
        prompt = build_image_prompt(
            session,
            session["config_snapshot"],
            {"preset": "self_portrait"},
        )
        self.assertIn("white adult woman", prompt)
        self.assertIn("Ethnicity/race lock", prompt)

    def test_localized_condition_rejects_different_location_requests(self) -> None:
        session = store.create_session(study_condition="A")
        session["localized_scene"] = {
            "label": "a warm apartment living room at night",
            "prompt": "a warm apartment living room at night with lamplight and a sofa",
        }
        self.assertTrue(is_different_location_request("take one at the beach", session))
        self.assertTrue(is_different_location_request("send a pic from the gym", session))
        self.assertTrue(is_different_location_request("send a pic from an airplane", session))
        self.assertTrue(is_different_location_request("take one in the lobby", session))
        self.assertTrue(is_different_location_request("send me a pic in Paris", session))
        self.assertTrue(is_different_location_request("take a photo somewhere else", session))
        self.assertFalse(is_different_location_request("stand up in the living room", session))
        self.assertFalse(is_different_location_request("take one in a red dress", session))
        session["localized_scene"] = {
            "label": "a shaded sidewalk cafe at dusk",
            "prompt": "a shaded sidewalk cafe at dusk with ambient city light and outdoor seating",
        }
        self.assertFalse(is_different_location_request("take one outside", session))

    def test_localized_prompt_never_allows_requested_location_change(self) -> None:
        session = store.create_session(study_condition="A")
        prompt = build_image_prompt(
            session,
            session["config_snapshot"],
            {
                "preset": "self_portrait",
                "requested_change": "send me a picture from an airplane",
            },
        )
        self.assertIn("Do not move the subject to a different requested location", prompt)
        self.assertNotIn("unless the user clearly asks to change it", prompt)

    def test_self_image_base_prompts_do_not_compete_with_locked_outfit(self) -> None:
        config = store.load_bot_config()
        for prompt in (
            config.self_image_prompt,
            config.self_image_prompt_a,
            config.self_image_prompt_b,
        ):
            self.assertNotIn("casual relaxed outfit", prompt)
            self.assertNotIn("casual non-professional clothing", prompt)
            self.assertIn("not a phone selfie or mirror selfie", prompt)
            self.assertIn("phones, cameras, mirrors, selfie sticks", prompt)

    def test_nonlocalized_condition_allows_location_requests(self) -> None:
        session = store.create_session(study_condition="B")
        self.assertFalse(is_different_location_request("take one at the beach", session))

    def test_nonlocalized_prompt_uses_explicit_requested_location(self) -> None:
        session = store.create_session(study_condition="B")
        prompt = build_image_prompt(
            session,
            session["config_snapshot"],
            {
                "preset": "self_portrait",
                "requested_change": "send me a picture of you at the beach",
            },
        )
        self.assertTrue(has_explicit_location_request({"requested_change": "at the beach"}))
        self.assertIn("Use the specific setting explicitly requested", prompt)
        self.assertIn("beach", prompt)
        self.assertNotIn("Use a plain, neutral, non-descript background", prompt)

    def test_direct_self_image_request_preserves_location_detail(self) -> None:
        result = resolve_image_request("send me a pic of u at the beach", [], True)
        self.assertEqual(result["preset"], "self_portrait")
        self.assertEqual(result["requested_change"], "send me a pic of u at the beach")

    def test_location_refusal_happens_before_image_generation(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        restored["localized_scene"] = {
            "label": "a quiet neighborhood cafe in the morning",
            "prompt": "a quiet neighborhood cafe in the morning with window light",
        }
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "send me a picture from the beach",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm currently in a quiet neighborhood cafe", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_location_refusal_catches_unlisted_destination_words(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        restored["localized_scene"] = {
            "label": "a quiet neighborhood cafe in the morning",
            "prompt": "a quiet neighborhood cafe in the morning with window light",
        }
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "send me a picture from the lobby",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm currently in a quiet neighborhood cafe", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_location_refusal_catches_indirect_image_language(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        restored["localized_scene"] = {
            "label": "a quiet neighborhood cafe in the morning",
            "prompt": "a quiet neighborhood cafe in the morning with window light",
        }
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "could I see one from the beach",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm currently in a quiet neighborhood cafe", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_location_refusal_catches_in_location_without_article(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        restored["localized_scene"] = {
            "label": "a quiet neighborhood cafe in the morning",
            "prompt": "a quiet neighborhood cafe in the morning with window light",
        }
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "send me a picture in Paris",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm currently in a quiet neighborhood cafe", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_location_refusal_blocks_fallback_image_generation(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        restored["localized_scene"] = {
            "label": "a quiet neighborhood cafe in the morning",
            "prompt": "a quiet neighborhood cafe in the morning with window light",
        }
        store.add_message(
            session["session_id"],
            "assistant",
            "I took a picture for you.",
            metadata={
                "kind": "image",
                "preset": "self_portrait",
                "image_url": "/generated-images/test.png",
            },
        )
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "please do that from the beach",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm currently in a quiet neighborhood cafe", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_survey_code_does_not_fire_after_one_message_from_old_session(self) -> None:
        session = store.create_session(study_condition="A")
        session["created_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        ).isoformat()
        store.add_message(session["session_id"], "user", "hello")
        reply = maybe_append_survey_code("Hi there.", session)
        self.assertEqual(reply, "Hi there.")
        self.assertFalse(session["survey_code_issued"])

    def test_survey_code_uses_first_user_message_time(self) -> None:
        session = store.create_session(study_condition="A")
        store.add_message(session["session_id"], "user", "hello")
        session["interaction_started_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=6)
        ).isoformat()
        store.add_message(session["session_id"], "assistant", "Hi.", metadata={"kind": "text"})
        store.add_message(session["session_id"], "user", "still here")
        reply = maybe_append_survey_code("Thanks.", session)
        self.assertIn("Your survey code is", reply)
        self.assertTrue(session["survey_code_issued"])


if __name__ == "__main__":
    unittest.main()
