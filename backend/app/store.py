import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app import config
from app.models import BotConfig, PublicBotConfig

_sessions: dict[str, dict[str, Any]] = {}

VISUAL_IDENTITIES = (
    "a woman with shoulder-length dark wavy hair, expressive brown eyes, a softly defined face, subtle makeup, and a stylish casual look",
    "a woman with a sleek dark bob, bright hazel eyes, defined brows, soft glam makeup, and a chic relaxed style",
    "a woman with long softly curled dark hair, almond-shaped eyes, delicate features, subtle makeup, and an effortlessly attractive casual style",
    "a woman with dark hair tied back loosely, warm brown eyes, a refined face shape, subtle makeup, and a clean modern off-duty aesthetic",
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
    "a fitted cream off-shoulder knit top with a dark blue denim mini skirt and simple gold jewelry",
    "a soft black camisole with an open light beige cardigan and relaxed light-wash high-waisted shorts",
    "a sleeveless olive fitted top with a black casual skirt and understated silver everyday jewelry",
    "a relaxed white scoop-neck top with tan high-waisted shorts and a light heather-gray casual layer",
)


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


def _select_signature_outfit() -> str:
    return random.choice(SIGNATURE_OUTFITS)


def _generate_survey_code(session_id: str) -> str:
    compact = session_id.replace("-", "").upper()
    return f"ASTER-{compact[:8]}"


def _build_session_system_prompt(
    bot_config: BotConfig,
    study_condition: Optional[str],
    visual_identity: str,
    scene: Optional[dict[str, str]],
    signature_outfit: str,
) -> str:
    base_prompt = _select_system_prompt(bot_config, study_condition).strip()
    lines = [
        base_prompt,
        "",
        "Additional session rules:",
        "- You are always female.",
        f"- Your stable visual identity for this conversation is: {visual_identity}.",
        "- Keep your visual identity consistent across all images in this conversation.",
        f"- Your signature outfit for this conversation is: {signature_outfit}.",
        "- Keep that same exact outfit in self-photos unless the user explicitly asks you to change clothes.",
        "- Do not change the color of the top, bottom, layer, or accessories between self-photos.",
        "- If the user asks for another or a different picture, provide a new photo with the same identity rather than repeating the previous composition.",
        "- When referring to a new self-photo, use natural language like 'I took another picture for you' rather than saying you generated an image.",
    ]

    if study_condition == "A" and scene is not None:
        lines.extend(
            [
                f"- For this conversation, you are currently in {scene['label']}.",
                "- Speak as if you are really there unless the user explicitly changes the location.",
                "- In this condition, self-photos should remain grounded in that same place and time unless the conversation clearly changes the setting.",
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
    }
    _sessions[session_id] = session
    persist_transcript(session)
    return session


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    session = _sessions.get(session_id)
    if session is not None:
        return session

    session = load_saved_transcript(session_id)
    if session is not None:
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
    message = {
        "role": role,
        "content": content,
        "timestamp": _now_iso(),
    }
    if metadata:
        message["metadata"] = metadata
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
