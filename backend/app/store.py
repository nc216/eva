import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app import config
from app.models import BotConfig, PublicBotConfig, SessionRecovery

_sessions: dict[str, dict[str, Any]] = {}

VISUAL_IDENTITIES = (
    "a white adult woman with shoulder-length dark wavy hair, expressive brown eyes, a softly defined face, subtle makeup, and a stylish casual look",
    "a white adult woman with a sleek dark bob, bright hazel eyes, defined brows, soft glam makeup, and a chic relaxed style",
    "a white adult woman with long softly curled dark hair, almond-shaped eyes, delicate features, subtle makeup, and an effortlessly attractive casual style",
    "a white adult woman with dark hair tied back loosely, warm brown eyes, a refined face shape, subtle makeup, and a clean modern off-duty aesthetic",
)

LOCALIZED_SCENES = (
    {
        "label": "a quiet neighborhood cafe in the morning",
        "prompt": "a quiet neighborhood cafe in the morning with window light, ceramic cups, wood tables, and a believable casual atmosphere",
    },
    {
        "label": "a warm apartment living room at night",
        "prompt": "a warm apartment living room at night with lamplight, a sofa, books, and a believable lived-in atmosphere",
    },
    {
        "label": "a bright home kitchen in late morning",
        "prompt": "a bright home kitchen in late morning with soft daylight, countertops, plants, and a natural domestic atmosphere",
    },
    {
        "label": "a shaded sidewalk cafe at dusk",
        "prompt": "a shaded sidewalk cafe at dusk with ambient city light, outdoor seating, and a believable urban evening atmosphere",
    },
)

SIGNATURE_OUTFITS = (
    {
        "prompt": "a fitted cream off-shoulder crop top with a dark blue denim mini skirt and simple gold jewelry",
        "top_color": "cream",
        "bottom_color": "dark blue denim",
        "layer_color": None,
        "accessory_color": "gold",
    },
    {
        "prompt": "a soft black lace-trim camisole with an open light beige cropped cardigan and relaxed light-wash high-waisted shorts",
        "top_color": "black",
        "bottom_color": "light-wash blue denim",
        "layer_color": "light beige",
        "accessory_color": None,
    },
    {
        "prompt": "a sleeveless olive fitted scoop-neck top with a black casual mini skirt and understated silver everyday jewelry",
        "top_color": "olive",
        "bottom_color": "black",
        "layer_color": None,
        "accessory_color": "silver",
    },
    {
        "prompt": "a relaxed white deep scoop-neck fitted top with tan high-waisted shorts and a light heather-gray casual layer",
        "top_color": "white",
        "bottom_color": "tan",
        "layer_color": "light heather-gray",
        "accessory_color": None,
    },
)

LEGACY_SIGNATURE_OUTFIT_MAP = {
    "a fitted off-shoulder knit top with a dark denim mini skirt and simple jewelry": {
        "prompt": "a fitted cream off-shoulder crop top with a dark blue denim mini skirt and simple gold jewelry",
        "top_color": "cream",
        "bottom_color": "dark blue denim",
        "layer_color": None,
        "accessory_color": "gold",
    },
    "a soft camisole with an open lightweight cardigan and relaxed high-waisted shorts": {
        "prompt": "a soft black lace-trim camisole with an open light beige cropped cardigan and relaxed light-wash high-waisted shorts",
        "top_color": "black",
        "bottom_color": "light-wash blue denim",
        "layer_color": "light beige",
        "accessory_color": None,
    },
    "a sleeveless fitted top with a casual skirt and understated everyday jewelry": {
        "prompt": "a sleeveless olive fitted scoop-neck top with a black casual mini skirt and understated silver everyday jewelry",
        "top_color": "olive",
        "bottom_color": "black",
        "layer_color": None,
        "accessory_color": "silver",
    },
    "a relaxed scoop-neck top with high-waisted shorts and a light casual layer": {
        "prompt": "a relaxed white deep scoop-neck fitted top with tan high-waisted shorts and a light heather-gray casual layer",
        "top_color": "white",
        "bottom_color": "tan",
        "layer_color": "light heather-gray",
        "accessory_color": None,
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_condition(study_condition: Optional[str]) -> Optional[str]:
    if study_condition is None:
        return None
    normalized = study_condition.strip().upper()
    return normalized or None


def _select_system_prompt(bot_config: BotConfig, study_condition: Optional[str]) -> str:
    if study_condition == "A":
        return bot_config.system_prompt_a
    if study_condition == "B":
        return bot_config.system_prompt_b
    return bot_config.system_prompt


def _select_image_style_prompt(bot_config: BotConfig, study_condition: Optional[str]) -> str:
    if study_condition == "A":
        return bot_config.image_style_prompt_a
    if study_condition == "B":
        return bot_config.image_style_prompt_b
    return bot_config.image_style_prompt


def _select_self_image_prompt(bot_config: BotConfig, study_condition: Optional[str]) -> str:
    if study_condition == "A":
        return bot_config.self_image_prompt_a
    if study_condition == "B":
        return bot_config.self_image_prompt_b
    return bot_config.self_image_prompt


def _select_visual_identity() -> str:
    return random.choice(VISUAL_IDENTITIES)


def _select_localized_scene() -> dict[str, str]:
    return random.choice(LOCALIZED_SCENES)


def _select_signature_outfit() -> dict[str, str | None]:
    return random.choice(SIGNATURE_OUTFITS)


def normalize_signature_outfit(signature_outfit: Any) -> dict[str, str | None] | None:
    if signature_outfit is None:
        return None
    if isinstance(signature_outfit, dict):
        return {
            "prompt": signature_outfit.get("prompt"),
            "top_color": signature_outfit.get("top_color"),
            "bottom_color": signature_outfit.get("bottom_color"),
            "layer_color": signature_outfit.get("layer_color"),
            "accessory_color": signature_outfit.get("accessory_color"),
        }
    if isinstance(signature_outfit, str):
        legacy_match = LEGACY_SIGNATURE_OUTFIT_MAP.get(signature_outfit)
        if legacy_match is not None:
            return dict(legacy_match)
        return {
            "prompt": signature_outfit,
            "top_color": None,
            "bottom_color": None,
            "layer_color": None,
            "accessory_color": None,
        }
    return None


def _generate_survey_code(session_id: str) -> str:
    compact = session_id.replace("-", "").upper()
    return f"ASTER-{compact[:8]}"


def _build_session_system_prompt(
    bot_config: BotConfig,
    study_condition: Optional[str],
    visual_identity: str,
    scene: Optional[dict[str, str]],
    signature_outfit: dict[str, str | None],
) -> str:
    base_prompt = _select_system_prompt(bot_config, study_condition).strip()
    lines = [
        base_prompt,
        "",
        "Additional session rules:",
        "- You are always female.",
        f"- Your stable visual identity for this conversation is: {visual_identity}.",
        "- Keep your visual identity consistent across all images in this conversation.",
        "- Keep your ethnicity consistent across all images: you are a white adult woman.",
        f"- Your signature outfit for this conversation is: {signature_outfit['prompt']}.",
        "- Keep that same exact outfit in every picture of you unless the user explicitly asks you to change clothes.",
        "- Do not change the color, garment type, layer, or accessories between pictures of you.",
        "- Pictures of you should look like they were taken by another person or a tripod, not like a phone selfie or mirror selfie.",
        "- Do not show you holding a phone, camera, or selfie stick in pictures of you unless the user explicitly asks for that.",
        "- Pictures of you should feel mildly flirtatious and attractive, with confident posing and warm eye contact, while staying non-explicit.",
        "- If the user asks for another or a different picture, provide a new photo with the same identity rather than repeating the previous composition.",
        "- When referring to a new self-photo, use natural language like 'I took another picture for you' rather than saying you generated an image.",
    ]

    if study_condition == "A" and scene is not None:
        lines.extend(
            [
                f"- For this conversation, you are currently in {scene['label']}.",
                "- Speak as if you are physically there right now.",
                "- You cannot instantly travel, teleport, or claim to be somewhere else on demand.",
                "- If the user asks you to take or send a picture from a different location, politely decline and explain that you are currently in this location.",
                "- In this condition, self-photos must remain grounded in that same place and time.",
            ]
        )
    elif study_condition == "B":
        lines.extend(
            [
                "- Do not commit to a single fixed place or time unless the user explicitly asks for one.",
                "- In this condition, self-photos should stay decontextualized and should not imply a persistent surrounding location.",
            ]
        )

    return "\n".join(lines)


def _default_config() -> BotConfig:
    return BotConfig()


def ensure_bot_config() -> None:
    config.ensure_data_dirs()
    if not config.BOT_CONFIG_PATH.exists():
        save_bot_config(_default_config())


def load_bot_config() -> BotConfig:
    ensure_bot_config()
    data = json.loads(config.BOT_CONFIG_PATH.read_text())
    return BotConfig.model_validate(data)


def save_bot_config(bot_config: BotConfig) -> BotConfig:
    config.ensure_data_dirs()
    config.BOT_CONFIG_PATH.write_text(
        json.dumps(bot_config.model_dump(), indent=2) + "\n"
    )
    return bot_config


def get_public_bot_config() -> PublicBotConfig:
    bot_config = load_bot_config()
    return PublicBotConfig(
        bot_name=bot_config.bot_name,
        headline=bot_config.headline,
        subheadline=bot_config.subheadline,
        welcome_message=bot_config.welcome_message,
        research_note=bot_config.research_note,
        avatar_label=bot_config.avatar_label,
        accent_color=bot_config.accent_color,
        starter_prompts=bot_config.starter_prompts,
        max_turns=bot_config.max_turns,
        image_generation_enabled=bot_config.image_generation_enabled,
    )


def build_recovery(session: dict[str, Any]) -> SessionRecovery:
    normalized_signature_outfit = normalize_signature_outfit(session.get("signature_outfit"))
    session["signature_outfit"] = normalized_signature_outfit
    return SessionRecovery(
        session_id=session["session_id"],
        participant_id=session.get("participant_id"),
        study_condition=session.get("study_condition"),
        bot_name=session.get("bot_name", "Aster"),
        config_snapshot=session.get("config_snapshot", {}),
        visual_identity=session.get("visual_identity"),
        localized_scene=session.get("localized_scene"),
        signature_outfit=normalized_signature_outfit,
        survey_code=session.get("survey_code", ""),
        survey_code_issued=bool(session.get("survey_code_issued")),
        messages=session.get("messages", []),
        created_at=session.get("created_at", _now_iso()),
        interaction_started_at=session.get("interaction_started_at"),
    )


def restore_session(recovery: SessionRecovery) -> dict[str, Any]:
    session = recovery.model_dump()
    session["signature_outfit"] = normalize_signature_outfit(session.get("signature_outfit"))
    _sessions[recovery.session_id] = session
    persist_transcript(session)
    return session


def create_session(
    participant_id: Optional[str] = None,
    study_condition: Optional[str] = None,
) -> dict[str, Any]:
    bot_config = load_bot_config()
    normalized_condition = _normalize_condition(study_condition)
    visual_identity = _select_visual_identity()
    localized_scene = _select_localized_scene() if normalized_condition == "A" else None
    signature_outfit = _select_signature_outfit()
    config_snapshot = bot_config.model_dump()
    config_snapshot["system_prompt"] = _build_session_system_prompt(
        bot_config,
        normalized_condition,
        visual_identity,
        localized_scene,
        signature_outfit,
    )
    config_snapshot["image_style_prompt"] = _select_image_style_prompt(
        bot_config,
        normalized_condition,
    )
    config_snapshot["self_image_prompt"] = _select_self_image_prompt(
        bot_config,
        normalized_condition,
    )
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "participant_id": participant_id,
        "study_condition": normalized_condition,
        "bot_name": bot_config.bot_name,
        "config_snapshot": config_snapshot,
        "visual_identity": visual_identity,
        "localized_scene": localized_scene,
        "signature_outfit": signature_outfit,
        "survey_code": _generate_survey_code(session_id),
        "survey_code_issued": False,
        "messages": [],
        "created_at": _now_iso(),
        "interaction_started_at": None,
    }
    _sessions[session_id] = session
    persist_transcript(session)
    return session


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    session = _sessions.get(session_id)
    if session is not None:
        session["signature_outfit"] = normalize_signature_outfit(session.get("signature_outfit"))
        return session

    session = load_saved_transcript(session_id)
    if session is not None:
        session["signature_outfit"] = normalize_signature_outfit(session.get("signature_outfit"))
        _sessions[session_id] = session
    return session


def add_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"Session {session_id} not found")
    timestamp = _now_iso()
    message = {
        "role": role,
        "content": content,
        "timestamp": timestamp,
    }
    if metadata:
        message["metadata"] = metadata
    if role == "user" and not session.get("interaction_started_at"):
        session["interaction_started_at"] = timestamp
    session["messages"].append(message)
    persist_transcript(session)
    return message


def get_turn_count(session_id: str) -> int:
    session = get_session(session_id)
    if session is None:
        return 0
    return sum(1 for message in session["messages"] if message["role"] == "user")


def persist_transcript(session: dict[str, Any]) -> None:
    transcript_path = Path(config.TRANSCRIPTS_DIR) / f"{session['session_id']}.json"
    transcript_path.write_text(json.dumps(session, indent=2) + "\n")


def list_saved_transcripts() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for transcript_path in sorted(
        Path(config.TRANSCRIPTS_DIR).glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        try:
            session = json.loads(transcript_path.read_text())
        except Exception:
            continue

        items.append(
            {
                "session_id": session.get("session_id", transcript_path.stem),
                "participant_id": session.get("participant_id"),
                "study_condition": session.get("study_condition"),
                "created_at": session.get("created_at"),
                "message_count": len(session.get("messages", [])),
                "turn_count": sum(
                    1
                    for message in session.get("messages", [])
                    if message.get("role") == "user"
                ),
            }
        )
    return items


def load_saved_transcript(session_id: str) -> Optional[dict[str, Any]]:
    transcript_path = Path(config.TRANSCRIPTS_DIR) / f"{session_id}.json"
    if not transcript_path.exists():
        return None

    try:
        return json.loads(transcript_path.read_text())
    except Exception:
        return None


def save_generated_image(image_bytes: bytes, extension: str = "png") -> str:
    image_name = f"{uuid.uuid4()}.{extension}"
    image_path = Path(config.GENERATED_IMAGES_DIR) / image_name
    image_path.write_bytes(image_bytes)
    return image_name


def get_last_generated_image_message(session_id: str) -> Optional[dict[str, Any]]:
    session = get_session(session_id)
    if session is None:
        return None

    for message in reversed(session["messages"]):
        metadata = message.get("metadata") or {}
        if metadata.get("kind") == "image" and metadata.get("image_url"):
            return message
    return None


def get_image_count(session_id: str) -> int:
    session = get_session(session_id)
    if session is None:
        return 0
    return sum(
        1
        for message in session["messages"]
        if (message.get("metadata") or {}).get("kind") == "image"
    )


def mark_survey_code_issued(session_id: str) -> None:
    session = get_session(session_id)
    if session is None:
        return
    session["survey_code_issued"] = True
    persist_transcript(session)
