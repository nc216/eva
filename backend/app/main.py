from contextlib import asynccontextmanager
from datetime import datetime, timezone

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
    TranscriptResponse,
)


SURVEY_CODE_DELAY_SECONDS = 5 * 60


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
    image_count = store.get_image_count(session["session_id"])

    if image_request.get("preset") == "self_portrait":
        base_prompt = snapshot["self_image_prompt"]
    else:
        base_prompt = image_request["prompt"]

    parts = [base_prompt]

    if visual_identity:
        parts.append(f"Keep the same person identity in every image: {visual_identity}.")

    if localized_scene:
        parts.append(
            "Keep the image grounded in this same setting unless the user clearly asks to change it: "
            f"{localized_scene['prompt']}."
        )

    parts.append(
        "Style the clothing and presentation as casual rather than professional or corporate. "
        "Prefer relaxed everyday outfits like tank tops, fitted t-shirts, camisoles, off-shoulder tops, shorts, skirts, dresses, lounge sets, or other non-formal clothing that feels natural for the scene. "
        "When it fits the situation, show more shoulders, arms, legs, or neckline, but keep it non-explicit."
    )

    if image_count > 0 or image_request.get("variation"):
        parts.append(
            "This must be a genuinely different photo from earlier ones in the conversation. "
            "Keep the same identity, but change the framing, camera angle, pose, expression, action, or distance so it does not look like a duplicate."
        )

    return "\n\n".join(parts)


def build_image_reply(image_request: dict, image_count: int) -> str:
    is_self_portrait = image_request.get("preset") == "self_portrait"
    if is_self_portrait:
        if image_count > 0 or image_request.get("variation"):
            return "I took another picture for you."
        return "I took a picture for you."
    if image_count > 0 or image_request.get("variation"):
        return "I made another image for you."
    return "I made an image for you."


def maybe_append_survey_code(reply: str, session: dict) -> str:
    if session.get("survey_code_issued"):
        return reply

    created_at = datetime.fromisoformat(session["created_at"])
    elapsed_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
    if elapsed_seconds < SURVEY_CODE_DELAY_SECONDS:
        return reply

    store.mark_survey_code_issued(session["session_id"])
    survey_code = session["survey_code"]
    return (
        f"{reply}\n\nYour survey code is {survey_code}. "
        "Copy and paste that code into the Qualtrics survey. "
        "If you want, you can return to the survey now or keep chatting with me longer."
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
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    session = store.get_session(req.session_id)
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

    store.add_message(req.session_id, "user", user_message)

    if image_request is not None:
        if image_request["action"] == "resend":
            last_image_message = store.get_last_generated_image_message(req.session_id)
            if last_image_message is not None:
                image_url = last_image_message["metadata"]["image_url"]
                reply = (
                    "I re-sent the latest image below. If it still does not appear, "
                    "open it in a new tab and tell me which browser you are using."
                )
                store.add_message(
                    req.session_id,
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
                    session_id=req.session_id,
                    kind="image",
                    reply=reply,
                    turn_number=turn_count + 1,
                    image_url=image_url,
                )

        image_prompt = build_image_prompt(session, snapshot, image_request)
        image_bytes = await openai_client.generate_image_bytes(
            user_message=image_prompt,
            image_style_prompt=snapshot["image_style_prompt"],
        )
        image_extension = "svg" if config.MOCK_MODE or not config.OPENAI_API_KEY else "png"
        image_name = store.save_generated_image(image_bytes, extension=image_extension)
        image_url = f"/generated-images/{image_name}"
        image_count = store.get_image_count(req.session_id)
        reply = maybe_append_survey_code(
            build_image_reply(image_request, image_count),
            session,
        )
        store.add_message(
            req.session_id,
            "assistant",
            reply,
            metadata={
                "kind": "image",
                "image_prompt": image_prompt,
                "image_url": image_url,
                "preset": image_request.get("preset"),
            },
        )
        return ChatResponse(
            session_id=req.session_id,
            kind="image",
            reply=reply,
            turn_number=turn_count + 1,
            image_url=image_url,
        )

    reply = await openai_client.generate_text_reply(
        system_prompt=snapshot["system_prompt"],
        transcript=session["messages"][:-1],
        user_message=user_message,
        temperature=snapshot["temperature"],
    )
    reply = maybe_append_survey_code(reply, session)
    store.add_message(req.session_id, "assistant", reply, metadata={"kind": "text"})
    return ChatResponse(
        session_id=req.session_id,
        kind="text",
        reply=reply,
        turn_number=turn_count + 1,
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
