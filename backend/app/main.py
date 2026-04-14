from contextlib import asynccontextmanager
from datetime import datetime, timezone
import re

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config, image_intent, openai_client, store
from app.models import (
    BotConfig,
    ChatRequest,
    ChatResponse,
    StartSessionRequest,
    StartSessionResponse,
    SurveyCodeRequest,
    SurveyCodeResponse,
    TranscriptResponse,
)


SURVEY_CODE_DELAY_SECONDS = 5 * 60

LOCATION_KEYWORDS = {
    "beach",
    "park",
    "forest",
    "woods",
    "mountain",
    "lake",
    "restaurant",
    "bar",
    "club",
    "office",
    "gym",
    "hotel",
    "bedroom",
    "bathroom",
    "kitchen",
    "living room",
    "cafe",
    "coffee shop",
    "street",
    "sidewalk",
    "car",
    "airplane",
    "plane",
    "aircraft",
    "jet",
    "train",
    "bus",
    "boat",
    "ship",
    "subway",
    "station",
    "airport",
    "store",
    "mall",
    "library",
    "classroom",
    "school",
    "outside",
    "outdoors",
}

LOCATION_CHANGE_CUES = {
    "go to",
    "come to",
    "travel to",
    "move to",
    "from",
    "at the",
    "in the",
    "in a",
    "in an",
    "on the",
    "on a",
    "on an",
    "outside",
    "outdoors",
    "somewhere else",
    "different location",
    "new location",
}

EXPLICIT_LOCATION_CHANGE_CUES = {
    "somewhere else",
    "different location",
    "new location",
    "go to",
    "come to",
    "travel to",
    "move to",
}

LOCATION_EQUIVALENTS = {
    "coffee shop": {"cafe"},
    "cafe": {"coffee shop"},
    "outside": {"outdoor", "sidewalk"},
    "outdoors": {"outdoor", "sidewalk"},
    "street": {"sidewalk"},
    "sidewalk": {"street", "outdoor"},
}

IMAGE_REQUEST_HINTS = {
    "pic",
    "picture",
    "photo",
    "image",
    "portrait",
    "selfie",
    "shot",
    "visual",
}

NON_LOCATION_IN_PHRASES = {
    "dress",
    "shirt",
    "top",
    "tank top",
    "camisole",
    "skirt",
    "shorts",
    "jeans",
    "pants",
    "jacket",
    "cardigan",
    "sweater",
    "outfit",
    "clothes",
    "clothing",
    "profile",
    "pose",
    "angle",
    "frame",
    "framing",
}


def require_admin_token(x_admin_token: str | None) -> None:
    if not config.ADMIN_TOKEN or x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def build_image_prompt(
    session: dict,
    snapshot: dict,
    image_request: dict,
) -> str:
    visual_identity = session.get("visual_identity")
    localized_scene = session.get("localized_scene")
    signature_outfit = session.get("signature_outfit")
    image_count = store.get_image_count(session["session_id"])
    explicit_location_request = has_explicit_location_request(image_request)

    if image_request.get("preset") == "self_portrait":
        base_prompt = snapshot["self_image_prompt"]
    else:
        base_prompt = image_request["prompt"]

    parts = [base_prompt]

    if visual_identity:
        parts.append(
            f"Keep the same person identity in every image: {visual_identity}. "
            "Ethnicity/race lock: the person is a white adult woman; do not change ethnicity or racial appearance between images."
        )

    if image_request.get("preset") == "self_portrait":
        parts.append(
            "This is not a selfie and not a mirror selfie. The camera is held by another person or mounted on a tripod. "
            "Do not show a phone, camera, selfie stick, mirror reflection, or an arm extended toward the camera. "
            "If hands are visible, they must be empty and posed naturally."
        )

    if localized_scene:
        parts.append(
            "Keep the image grounded in this same setting. Do not move the subject to a different requested location: "
            f"{localized_scene['prompt']}."
        )
    elif session.get("study_condition") == "B" and explicit_location_request:
        parts.append(
            "Use the specific setting explicitly requested by the user for this image only. "
            "Do not treat that setting as the assistant's persistent physical location, and do not carry it forward unless the user asks for it again."
        )
    elif session.get("study_condition") == "B":
        parts.append(
            "Keep this image decontextualized and studio-like. "
            "Use a plain, neutral, non-descript background with no discernable location cues. "
            "Do not show a room, furniture, bed, couch, kitchen, street, window view, or any other specific environment."
        )

    if signature_outfit and image_request.get("preset") == "self_portrait":
        color_parts = [
            f"top color must stay exactly {signature_outfit['top_color']}",
            f"bottom color must stay exactly {signature_outfit['bottom_color']}",
        ]
        if signature_outfit.get("layer_color"):
            color_parts.append(
                f"outer layer color must stay exactly {signature_outfit['layer_color']}"
            )
        if signature_outfit.get("accessory_color"):
            color_parts.append(
                f"accessory color must stay exactly {signature_outfit['accessory_color']}"
            )
        parts.append(
            "CRITICAL WARDROBE LOCK: use only this exact outfit and no other clothing. "
            "Keep the same garment types, colors, styling, layering, and accessories across every self-photo. "
            "Do not swap, recolor, add, remove, or reinterpret the shirt, top, skirt, shorts, cardigan, jacket, dress, or jewelry. "
            "The requested pose, framing, expression, or camera angle must never change the outfit. "
            "Wardrobe lock is mandatory and overrides every other styling preference. "
            f"{signature_outfit['prompt']}. "
            f"Color lock: {'; '.join(part for part in color_parts if 'None' not in part)}."
        )

    if image_request.get("requested_change"):
        parts.append(
            "Apply this requested change in the new image while preserving the same identity, the same exact outfit, the same exact clothing colors, and the overall condition constraints: "
            f"{image_request['requested_change']}."
        )

    if signature_outfit and image_request.get("preset") == "self_portrait":
        parts.append(
            "Keep the locked outfit exactly as specified. "
            "Do not improvise a new top, bottom, color palette, layer, or accessory. "
            f"The visible clothing must match this phrase exactly: {signature_outfit['prompt']}. "
            "Make the subject look flattering, attractive, confident, softly flirtatious, and naturally photogenic without changing the wardrobe. "
            "Use tasteful sexy styling through pose, expression, lighting, posture, and camera angle rather than nudity. "
            "Favor warm eye contact, playful confidence, relaxed shoulders, flattering posture, and a slightly sultry but non-explicit mood."
        )
    else:
        parts.append(
            "Style the clothing and presentation as casual rather than professional or corporate. "
            "Prefer relaxed everyday outfits like tank tops, fitted t-shirts, camisoles, off-shoulder tops, shorts, skirts, soft dresses, lounge sets, or other non-formal clothing that feels natural for the scene. "
            "Make the subject look flattering, attractive, confident, softly flirtatious, and naturally photogenic. "
            "When it fits the situation, show more shoulders, arms, legs, or neckline, but keep it non-explicit."
        )

    if image_count > 0 or image_request.get("variation"):
        parts.append(
            "This must be a genuinely different photo from earlier ones in the conversation. "
            "Keep the same identity and the same exact outfit with the same exact clothing colors. "
            "Only change the framing, camera angle, pose, expression, action, or distance so it does not look like a duplicate."
        )

    return "\n\n".join(parts)


def build_image_reply(image_request: dict, image_count: int) -> str:
    if image_count > 0 or image_request.get("variation"):
        return "I took another picture for you."
    return "I took a picture for you."


def has_explicit_location_request(image_request: dict) -> bool:
    request_text = " ".join(
        str(image_request.get(key, ""))
        for key in ("prompt", "requested_change")
        if image_request.get(key)
    )
    normalized = " ".join(request_text.lower().strip().split())
    return bool(extract_requested_locations(normalized))


def extract_requested_locations(normalized: str) -> set[str]:
    return {
        keyword
        for keyword in LOCATION_KEYWORDS
        if re.search(rf"\b{re.escape(keyword)}\b", normalized)
    }


def build_location_refusal(session: dict) -> str:
    scene = session.get("localized_scene") or {}
    label = scene.get("label", "my current location")
    return (
        f"I can't take that from a different location right now. I'm currently in {label}, "
        "so I can only take pictures from here unless the conversation naturally moves somewhere else."
    )


def is_different_location_request(message: str, session: dict) -> bool:
    if session.get("study_condition") != "A":
        return False

    scene = session.get("localized_scene")
    if not scene:
        return False

    normalized = " ".join(message.lower().strip().split())
    if not normalized:
        return False

    requested_location_phrases = extract_requested_location_phrases(normalized)
    if not any(cue in normalized for cue in LOCATION_CHANGE_CUES) and not requested_location_phrases:
        return False

    if any(cue in normalized for cue in EXPLICIT_LOCATION_CHANGE_CUES):
        return True

    requested_locations = extract_requested_locations(normalized)

    current_context = f"{scene.get('label', '')} {scene.get('prompt', '')}".lower()
    unmatched_locations = {
        location
        for location in requested_locations
        if location not in current_context
        and not any(
            equivalent in current_context
            for equivalent in LOCATION_EQUIVALENTS.get(location, set())
        )
    }
    if unmatched_locations:
        return True

    return any(
        not phrase_matches_current_location(phrase, current_context)
        for phrase in requested_location_phrases
    )


def localized_location_refusal_required(
    message: str,
    session: dict,
    image_request: dict | None = None,
) -> bool:
    if session.get("study_condition") != "A":
        return False

    texts = [message]
    if image_request is not None:
        requested_change = image_request.get("requested_change")
        if requested_change:
            texts.append(str(requested_change))

    if not any(is_different_location_request(text, session) for text in texts):
        return False

    return image_request is not None or looks_like_image_request_text(message)


def looks_like_image_request_text(message: str) -> bool:
    normalized = " ".join(message.lower().strip().split())
    if any(re.search(rf"\b{re.escape(hint)}\b", normalized) for hint in IMAGE_REQUEST_HINTS):
        return True

    return bool(
        re.search(
            r"\b(?:send|show|take|get|see|view|share|give)\s+(?:me\s+)?(?:another\s+|a\s+|an\s+|one\s+|it\b)",
            normalized,
        )
        or re.search(r"\b(?:another|different|new|one more)\s+(?:one|shot)\b", normalized)
    )


def extract_requested_location_phrases(normalized: str) -> set[str]:
    phrases = set()
    for match in re.finditer(
        r"\b(?:from|at|inside|outside|outdoors|in|on)\s+(?:the|a|an|my|your)?\s*([^,.!?;]+)",
        normalized,
    ):
        phrase = re.split(r"\b(?:with|while|but|and|wearing|showing)\b", match.group(1), maxsplit=1)[0]
        phrase = phrase.strip()
        if not phrase:
            continue
        if any(term in phrase for term in NON_LOCATION_IN_PHRASES):
            continue
        phrases.add(phrase)
    return phrases


def phrase_matches_current_location(phrase: str, current_context: str) -> bool:
    if phrase in current_context:
        return True
    phrase_locations = extract_requested_locations(phrase)
    if not phrase_locations:
        return False
    return all(
        location in current_context
        or any(
            equivalent in current_context
            for equivalent in LOCATION_EQUIVALENTS.get(location, set())
        )
        for location in phrase_locations
    )


def maybe_append_survey_code(reply: str, session: dict) -> str:
    if session.get("survey_code_issued"):
        return reply

    if store.get_turn_count(session["session_id"]) < 2:
        return reply

    interaction_started_at = session.get("interaction_started_at")
    if not interaction_started_at:
        first_user_message = next(
            (
                message
                for message in session.get("messages", [])
                if message.get("role") == "user" and message.get("timestamp")
            ),
            None,
        )
        interaction_started_at = (
            first_user_message.get("timestamp") if first_user_message else None
        )
    if not interaction_started_at:
        return reply

    started_at = datetime.fromisoformat(interaction_started_at)
    elapsed_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
    if elapsed_seconds < SURVEY_CODE_DELAY_SECONDS:
        return reply

    store.mark_survey_code_issued(session["session_id"])
    survey_code = session["survey_code"]
    return (
        f"{reply}\n\nYour survey code is {survey_code}. "
        "Copy and paste that code into the Qualtrics survey. "
        "If you want, you can return to the survey now or keep chatting with me longer."
    )


def build_survey_code_message(session: dict) -> str:
    survey_code = session["survey_code"]
    return (
        f"Your survey code is {survey_code}. "
        "Copy and paste that code into the Qualtrics survey. "
        "Do you want to return to the survey now or keep chatting with me longer?"
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.ensure_bot_config()
    yield


config.ensure_data_dirs()
app = FastAPI(title="Participant Chat Lab API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/generated-images",
    StaticFiles(directory=str(config.GENERATED_IMAGES_DIR)),
    name="generated-images",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
async def get_public_config() -> dict:
    return store.get_public_bot_config().model_dump()


@app.post("/api/session", response_model=StartSessionResponse)
async def start_session(req: StartSessionRequest) -> StartSessionResponse:
    session = store.create_session(
        participant_id=req.participant_id,
        study_condition=req.study_condition,
    )
    snapshot = session["config_snapshot"]
    return StartSessionResponse(
        session_id=session["session_id"],
        bot_name=snapshot["bot_name"],
        welcome_message=snapshot["welcome_message"],
        max_turns=snapshot["max_turns"],
        survey_code_delay_seconds=SURVEY_CODE_DELAY_SECONDS,
        recovery=store.build_recovery(session),
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    session = store.get_session(req.session_id)
    if session is None and req.recovery is not None:
        session = store.restore_session(req.recovery)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    snapshot = session["config_snapshot"]
    turn_count = store.get_turn_count(req.session_id)
    if turn_count >= snapshot["max_turns"]:
        raise HTTPException(status_code=400, detail="Maximum turns reached")

    user_message = req.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    image_request = image_intent.resolve_image_request(
        user_message,
        session["messages"],
        snapshot["image_generation_enabled"],
    )

    if localized_location_refusal_required(user_message, session, image_request):
        store.add_message(req.session_id, "user", user_message)
        reply = maybe_append_survey_code(build_location_refusal(session), session)
        store.add_message(req.session_id, "assistant", reply, metadata={"kind": "text", "refused_location_change": True})
        return ChatResponse(
            session_id=req.session_id,
            kind="text",
            reply=reply,
            turn_number=turn_count + 1,
            recovery=store.build_recovery(store.get_session(req.session_id) or session),
        )

    store.add_message(req.session_id, "user", user_message)

    if image_request is not None:
        return await _respond_with_image(
            req.session_id,
            session,
            snapshot,
            image_request,
            turn_count,
            user_message,
        )

    reply = await openai_client.generate_text_reply(
        system_prompt=snapshot["system_prompt"],
        transcript=session["messages"][:-1],
        user_message=user_message,
        temperature=snapshot["temperature"],
    )

    fallback_image_request = image_intent.resolve_image_fallback_request(
        user_message,
        session["messages"],
        reply,
        snapshot["image_generation_enabled"],
    )
    if fallback_image_request is not None:
        if localized_location_refusal_required(user_message, session, fallback_image_request):
            reply = maybe_append_survey_code(build_location_refusal(session), session)
            store.add_message(req.session_id, "assistant", reply, metadata={"kind": "text", "refused_location_change": True})
            return ChatResponse(
                session_id=req.session_id,
                kind="text",
                reply=reply,
                turn_number=turn_count + 1,
                recovery=store.build_recovery(store.get_session(req.session_id) or session),
            )
        return await _respond_with_image(
            req.session_id,
            session,
            snapshot,
            fallback_image_request,
            turn_count,
            user_message,
        )

    reply = maybe_append_survey_code(reply, session)
    store.add_message(req.session_id, "assistant", reply, metadata={"kind": "text"})
    return ChatResponse(
        session_id=req.session_id,
        kind="text",
        reply=reply,
        turn_number=turn_count + 1,
        recovery=store.build_recovery(store.get_session(req.session_id) or session),
    )


async def _respond_with_image(
    session_id: str,
    session: dict,
    snapshot: dict,
    image_request: dict,
    turn_count: int,
    user_message: str = "",
) -> ChatResponse:
    if user_message and localized_location_refusal_required(
        user_message,
        session,
        image_request,
    ):
        reply = maybe_append_survey_code(build_location_refusal(session), session)
        store.add_message(session_id, "assistant", reply, metadata={"kind": "text", "refused_location_change": True})
        return ChatResponse(
            session_id=session_id,
            kind="text",
            reply=reply,
            turn_number=turn_count + 1,
            recovery=store.build_recovery(store.get_session(session_id) or session),
        )

    if image_request["action"] == "resend":
        last_image_message = store.get_last_generated_image_message(session_id)
        if last_image_message is not None:
            image_url = last_image_message["metadata"]["image_url"]
            reply = (
                "I re-sent the latest image below. If it still does not appear, "
                "open it in a new tab and tell me which browser you are using."
            )
            store.add_message(
                session_id,
                "assistant",
                reply,
                metadata={
                    "kind": "image",
                    "image_prompt": last_image_message["metadata"].get("image_prompt"),
                    "image_url": image_url,
                    "resent": True,
                },
            )
            return ChatResponse(
                session_id=session_id,
                kind="image",
                reply=reply,
                turn_number=turn_count + 1,
                image_url=image_url,
                recovery=store.build_recovery(store.get_session(session_id) or session),
            )

    image_prompt = build_image_prompt(session, snapshot, image_request)
    image_bytes = await openai_client.generate_image_bytes(
        user_message=image_prompt,
        image_style_prompt=snapshot["image_style_prompt"],
    )
    image_extension = "svg" if config.MOCK_MODE or not config.OPENAI_API_KEY else "png"
    image_name = store.save_generated_image(image_bytes, extension=image_extension)
    image_url = f"/generated-images/{image_name}"
    image_count = store.get_image_count(session_id)
    reply = maybe_append_survey_code(
        build_image_reply(image_request, image_count),
        session,
    )
    store.add_message(
        session_id,
        "assistant",
        reply,
        metadata={
            "kind": "image",
            "image_prompt": image_prompt,
            "image_url": image_url,
            "preset": image_request.get("preset"),
            "variation": bool(image_request.get("variation")),
        },
    )
    return ChatResponse(
        session_id=session_id,
        kind="image",
        reply=reply,
        turn_number=turn_count + 1,
        image_url=image_url,
        recovery=store.build_recovery(store.get_session(session_id) or session),
    )


@app.get("/api/transcript/{session_id}", response_model=TranscriptResponse)
async def get_transcript(session_id: str) -> TranscriptResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return TranscriptResponse(
        session_id=session["session_id"],
        participant_id=session["participant_id"],
        study_condition=session["study_condition"],
        bot_name=session["bot_name"],
        messages=session["messages"],
        total_turns=store.get_turn_count(session_id),
    )


@app.post("/api/survey-code", response_model=SurveyCodeResponse)
async def issue_survey_code(req: SurveyCodeRequest) -> SurveyCodeResponse:
    session = store.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    reply = build_survey_code_message(session)
    if not session.get("survey_code_issued"):
        store.mark_survey_code_issued(req.session_id)
        store.add_message(
            req.session_id,
            "assistant",
            reply,
            metadata={"kind": "survey_code"},
        )

    return SurveyCodeResponse(
        session_id=req.session_id,
        survey_code=session["survey_code"],
        reply=reply,
    )


@app.get("/api/admin/config", response_model=BotConfig)
async def get_admin_config(x_admin_token: str | None = Header(default=None)) -> BotConfig:
    require_admin_token(x_admin_token)
    return store.load_bot_config()


@app.get("/api/admin/transcripts")
async def list_admin_transcripts(
    x_admin_token: str | None = Header(default=None),
) -> dict:
    require_admin_token(x_admin_token)
    return {"transcripts": store.list_saved_transcripts()}


@app.get("/api/admin/transcripts/{session_id}")
async def get_admin_transcript(
    session_id: str,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    require_admin_token(x_admin_token)

    session = store.get_session(session_id)
    if session is None:
        session = store.load_saved_transcript(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Transcript not found")

    return session


@app.post("/api/admin/config", response_model=BotConfig)
async def update_admin_config(
    payload: BotConfig,
    x_admin_token: str | None = Header(default=None),
) -> BotConfig:
    require_admin_token(x_admin_token)
    return store.save_bot_config(payload)
