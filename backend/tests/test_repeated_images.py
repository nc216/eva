import unittest
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app import openai_client, store
from app.image_intent import resolve_image_fallback_request, resolve_image_request
from app.main import (
    app,
    build_image_content_challenge_reply,
    build_image_prompt,
    build_image_reply,
    build_wardrobe_lock,
    has_explicit_location_request,
    is_different_location_request,
    maybe_append_survey_code,
    should_lock_outfit,
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

    def test_unorthodox_prior_image_change_requests_trigger_new_self_photo(self) -> None:
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
        for message in (
            "change it so you are in front of a garden",
            "make it in front of a garden",
            "put yourself in front of a garden",
            "change the background to a garden",
            "with a garden behind you",
        ):
            result = resolve_image_request(message, history, True)
            self.assertEqual(result["preset"], "self_portrait")
            self.assertTrue(result["variation"])
            self.assertEqual(result["requested_change"], message)

    def test_object_interaction_followup_triggers_new_self_photo(self) -> None:
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
            "pick out a book there and hold it up for me",
            history,
            True,
        )
        self.assertEqual(result["preset"], "self_portrait")
        self.assertTrue(result["variation"])
        self.assertEqual(
            result["requested_change"],
            "pick out a book there and hold it up for me",
        )

    def test_fallback_image_generation_preserves_object_interaction_request(self) -> None:
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
        result = resolve_image_fallback_request(
            "pick out a book there and hold it up for me",
            history,
            "I took another picture for you.",
            True,
        )
        self.assertEqual(result["preset"], "self_portrait")
        self.assertTrue(result["variation"])
        self.assertEqual(
            result["requested_change"],
            "pick out a book there and hold it up for me",
        )

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
        self.assertIn("Wardrobe lock is mandatory", prompt)
        self.assertIn("CRITICAL WARDROBE LOCK", prompt)
        self.assertIn("FINAL WARDROBE CHECK", prompt)
        self.assertIn("outer layer: none", prompt)
        self.assertIn("If the user asks for clothing changes", prompt)
        self.assertIn("Do not show a phone", prompt)
        self.assertIn("not a phone selfie or mirror selfie", prompt)
        self.assertIn("object and action are mandatory", prompt)
        self.assertGreater(prompt.count("solid black sleeveless scoop-neck fitted tank top"), 2)

    def test_image_content_challenge_reply_does_not_hallucinate_details(self) -> None:
        reply = build_image_content_challenge_reply()
        self.assertIn("did not capture that part correctly", reply)
        self.assertNotIn("holding", reply)
        self.assertNotIn("cover", reply)

    def test_where_is_object_after_image_uses_nonhallucinating_reply(self) -> None:
        async def hallucinating_text_reply(
            system_prompt: str,
            transcript: list[dict],
            user_message: str,
            temperature: float,
        ) -> str:
            return "In the photo, I am holding up a deep blue book."

        openai_client.generate_text_reply = hallucinating_text_reply
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        store.add_message(
            session["session_id"],
            "assistant",
            "I took another picture for you.",
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
                "message": "where's the book?",
                "recovery": store.build_recovery(store.get_session(session["session_id"])).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("did not capture that part correctly", response["reply"])
        self.assertNotIn("deep blue book", response["reply"])

    def test_where_are_you_after_image_is_not_image_content_challenge(self) -> None:
        async def location_text_reply(
            system_prompt: str,
            transcript: list[dict],
            user_message: str,
            temperature: float,
        ) -> str:
            return "I'm in the kitchen right now."

        openai_client.generate_text_reply = location_text_reply
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        store.add_message(
            session["session_id"],
            "assistant",
            "I took another picture for you.",
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
                "message": "where are you",
                "recovery": store.build_recovery(store.get_session(session["session_id"])).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertEqual(response["reply"], "I'm in the kitchen right now.")
        self.assertNotIn("did not capture that part correctly", response["reply"])

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
        self.assertEqual(upgraded["top_color"], "solid black")
        self.assertEqual(upgraded["bottom_color"], "solid black")
        self.assertEqual(upgraded["accessory_color"], "gold")

    def test_signature_outfit_is_single_simple_locked_uniform(self) -> None:
        outfits = {store._select_signature_outfit()["prompt"] for _ in range(10)}
        self.assertEqual(
            outfits,
            {
                "a solid black sleeveless scoop-neck fitted tank top with a solid black high-waisted mini skirt and small gold hoop earrings"
            },
        )

    def test_wardrobe_lock_forbids_layers_and_clothing_changes(self) -> None:
        session = store.create_session(study_condition="A")
        lock = build_wardrobe_lock(session["signature_outfit"])
        self.assertIn("outer layer: none", lock)
        self.assertIn("Do not add jackets, cardigans, coats", lock)
        self.assertIn("ignore the clothing-change part", lock)

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
        self.assertTrue(is_different_location_request("take one at the beach", session))
        self.assertTrue(is_different_location_request("send a pic from the gym", session))
        self.assertTrue(is_different_location_request("send a pic from an airplane", session))
        self.assertTrue(is_different_location_request("take one in the lobby", session))
        self.assertTrue(is_different_location_request("send me a pic in Paris", session))
        self.assertTrue(is_different_location_request("send one in front of a garden", session))
        self.assertTrue(is_different_location_request("take a photo somewhere else", session))
        self.assertFalse(is_different_location_request("go to the kitchen and take one", session))
        self.assertFalse(is_different_location_request("stand up in the living room", session))
        self.assertFalse(is_different_location_request("stand on one foot in the living room", session))
        self.assertFalse(is_different_location_request("move to the bedroom and send another", session))
        self.assertFalse(is_different_location_request("take one on the couch", session))
        self.assertFalse(is_different_location_request("pick out a book from the bookshelf and hold it up", session))
        self.assertFalse(is_different_location_request("take one outside on the patio", session))
        self.assertFalse(is_different_location_request("send a picture standing on one foot in this kitchen", session))
        self.assertFalse(is_different_location_request("send a picture standing on one foot", session))
        self.assertFalse(is_different_location_request("take one in a red dress", session))
        self.assertTrue(is_different_location_request("take one outside", session))

    def test_localized_condition_uses_fixed_home_scene(self) -> None:
        first = store.create_session(study_condition="A")
        second = store.create_session(study_condition="A")
        self.assertEqual(first["localized_scene"], second["localized_scene"])
        self.assertEqual(first["localized_scene"]["label"], "my home")
        self.assertIn("same cozy private home", first["localized_scene"]["prompt"])

    def test_localized_condition_allows_home_room_photo_requests(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "go to the kitchen and take one",
            },
        ).json()
        self.assertEqual(response["kind"], "image")
        self.assertTrue(response["image_url"])

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
        self.assertIn("do not move the subject to a public venue", prompt)
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

    def test_suggested_self_image_requests_are_detected(self) -> None:
        for message in (
            "what about a picture of you in front of a garden?",
            "how about a picture of you in front of a garden?",
            "could I see a picture of you in front of a garden?",
        ):
            result = resolve_image_request(message, [], True)
            self.assertEqual(result["preset"], "self_portrait")
            self.assertEqual(result["requested_change"], message)

    def test_nonlocalized_condition_uses_suggested_garden_setting(self) -> None:
        session = store.create_session(study_condition="B")
        image_request = resolve_image_request(
            "how about a picture of you in front of a garden?",
            [],
            True,
        )
        prompt = build_image_prompt(session, session["config_snapshot"], image_request)
        self.assertIn("Use the specific setting explicitly requested", prompt)
        self.assertIn("garden", prompt)
        self.assertNotIn("Use a plain, neutral, non-descript background", prompt)

    def test_nonlocalized_condition_allows_requested_outfit_changes(self) -> None:
        session = store.create_session(study_condition="B")
        image_request = resolve_image_request(
            "send me a picture of you wearing a red dress",
            [],
            True,
        )
        prompt = build_image_prompt(session, session["config_snapshot"], image_request)
        self.assertFalse(should_lock_outfit(session, image_request))
        self.assertIn("allow the requested outfit", prompt)
        self.assertIn("red dress", prompt)
        self.assertNotIn("CRITICAL WARDROBE LOCK", prompt)
        self.assertNotIn("FINAL WARDROBE CHECK", prompt)

    def test_nonlocalized_condition_allows_unorthodox_outfit_change_followup(self) -> None:
        session = store.create_session(study_condition="B")
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
        image_request = resolve_image_request("change it to a red dress", history, True)
        prompt = build_image_prompt(session, session["config_snapshot"], image_request)
        self.assertFalse(should_lock_outfit(session, image_request))
        self.assertIn("allow the requested outfit", prompt)
        self.assertIn("red dress", prompt)

    def test_localized_condition_still_locks_outfit_when_requested_to_change(self) -> None:
        session = store.create_session(study_condition="A")
        image_request = resolve_image_request(
            "send me a picture of you wearing a red dress",
            [],
            True,
        )
        prompt = build_image_prompt(session, session["config_snapshot"], image_request)
        self.assertTrue(should_lock_outfit(session, image_request))
        self.assertIn("CRITICAL WARDROBE LOCK", prompt)
        self.assertIn("ignore the clothing-change part", prompt)

    def test_location_refusal_happens_before_image_generation(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "send me a picture from the beach",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm at home", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_location_refusal_catches_unlisted_destination_words(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "send me a picture from the lobby",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm at home", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_location_refusal_catches_indirect_image_language(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "could I see one from the beach",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm at home", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_location_refusal_catches_in_location_without_article(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
        response = self.client.post(
            "/api/chat",
            json={
                "session_id": session["session_id"],
                "message": "send me a picture in Paris",
                "recovery": store.build_recovery(restored).model_dump(),
            },
        ).json()
        self.assertEqual(response["kind"], "text")
        self.assertIn("I'm at home", response["reply"])
        self.assertIsNone(response.get("image_url"))

    def test_location_refusal_blocks_fallback_image_generation(self) -> None:
        session = self.client.post("/api/session", json={"study_condition": "A"}).json()
        restored = store.get_session(session["session_id"])
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
        self.assertIn("I'm at home", response["reply"])
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
