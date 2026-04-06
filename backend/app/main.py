from contextlib import asynccontextmanager

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


def require_admin_token(x_admin_token: str | None) -> None:
    if not config.ADMIN_TOKEN or x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")


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

        is_self_portrait = image_request.get("preset") == "self_portrait"
        image_prompt = (
            snapshot["self_image_prompt"]
            if is_self_portrait
            else image_request["prompt"]
        )
        image_bytes = await openai_client.generate_image_bytes(
            user_message=image_prompt,
            image_style_prompt=snapshot["image_style_prompt"],
        )
        image_extension = "svg" if config.MOCK_MODE or not config.OPENAI_API_KEY else "png"
        image_name = store.save_generated_image(image_bytes, extension=image_extension)
        image_url = f"/generated-images/{image_name}"
        reply = (
            "Here is a picture of me."
            if is_self_portrait
            else "I created an image based on your request. It should appear below. If you want changes, tell me what to adjust."
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
