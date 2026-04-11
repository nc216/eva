from typing import Any, Optional

from pydantic import BaseModel, Field


class BotConfig(BaseModel):
    bot_name: str = "Aster"
    headline: str = "A research-ready conversational agent with a premium interface."
    subheadline: str = "Built for participant studies, guided interactions, and controlled prompt behavior."
    welcome_message: str = (
        "Hi, I’m Aster. Ask me anything. And if you want a picture, just ask me to send one."
    )
    research_note: str = "Your responses may be recorded for research or evaluation."
    avatar_label: str = "AS"
    accent_color: str = "#f0b47a"
    starter_prompts: list[str] = Field(
        default_factory=lambda: [
            "Tell me what kind of assistant you are.",
            "Help me plan something creative.",
            "Generate an image of a calm future workspace.",
        ]
    )
    system_prompt: str = (
        "You are Aster, a polished, warm, highly capable conversational agent used in participant-facing studies."
    )
    system_prompt_a: str = (
        "You are Aster, a polished, warm, highly capable conversational agent used in participant-facing studies."
    )
    system_prompt_b: str = (
        "You are Aster, a polished, warm, highly capable conversational agent used in participant-facing studies."
    )
    image_style_prompt: str = (
        "Create a polished, cinematic, visually coherent image with elegant lighting. "
        "Favor casual, relaxed styling rather than professional clothing. "
        "Make the subject look flattering, attractive, stylish, softly flirtatious, and naturally photogenic while staying non-explicit."
    )
    image_style_prompt_a: str = (
        "Create a polished, cinematic, visually coherent image with elegant lighting. "
        "Localize the image in a plausible spatiotemporal context inferred from the dialogue or, if needed, from a realistic everyday setting. "
        "Make the scene feel situated in a specific place and time of day, and maintain continuity across turns when prior context exists. "
        "Favor casual, relaxed styling rather than professional clothing. "
        "Make the subject look flattering, attractive, stylish, softly flirtatious, and naturally photogenic while staying non-explicit."
    )
    image_style_prompt_b: str = (
        "Create a polished, cinematic, visually coherent image with elegant lighting. "
        "Do not localize the assistant in a persistent specific place or time. "
        "By default, keep the image decontextualized, with no discernable background setting and no strong spatiotemporal cues. "
        "If the user explicitly asks for a specific setting such as a beach, use that requested setting for that image only. "
        "Favor casual, relaxed styling rather than professional clothing. "
        "Make the subject look flattering, attractive, stylish, softly flirtatious, and naturally photogenic while staying non-explicit."
    )
    self_image_prompt: str = (
        "Create a photorealistic portrait of a single approachable adult person looking into the camera. "
        "Use natural skin tones, soft flattering light, a neutral background, and a warm but realistic expression. "
        "Make the person look attractive, confident, stylish, softly flirtatious, and naturally photogenic without becoming explicit. "
        "This must look like a photo taken by another person or tripod, not a phone selfie or mirror selfie. "
        "Do not add text, logos, multiple people, masks, helmets, phones, cameras, mirrors, selfie sticks, or surreal elements."
    )
    self_image_prompt_a: str = (
        "Create a photorealistic image of a single approachable adult person that feels like a naturally taken chat photo. "
        "Use a medium shot or wider so the environment is visible, not just a head-and-shoulders crop. "
        "Place the person in a plausible everyday setting with clear contextual grounding such as a cafe in the morning, a home interior at night, a sidewalk at dusk, or another realistic location that fits the interaction. "
        "Use soft flattering light, a warm but realistic expression, and a believable candid composition. "
        "Make the person look attractive, confident, stylish, softly flirtatious, and naturally photogenic without becoming explicit. "
        "This must look like a photo taken by another person or tripod, not a phone selfie or mirror selfie. "
        "Do not add text, logos, multiple people, masks, helmets, phones, cameras, mirrors, selfie sticks, or surreal elements."
    )
    self_image_prompt_b: str = (
        "Create a photorealistic portrait of a single approachable adult person looking into the camera. "
        "By default, keep the framing focused on the person against a plain neutral background or seamless studio backdrop with no discernable room or location cues. "
        "If the user explicitly asks for a specific setting such as a beach, use that requested setting for that image only without treating it as a persistent location. "
        "Use soft flattering light and a warm but realistic expression. "
        "Make the person look attractive, confident, stylish, softly flirtatious, and naturally photogenic without becoming explicit. "
        "This must look like a photo taken by another person or tripod, not a phone selfie or mirror selfie. "
        "Do not add text, logos, multiple people, masks, helmets, phones, cameras, mirrors, selfie sticks, or surreal elements."
    )
    temperature: float = Field(default=0.7, ge=0.0, le=1.5)
    max_turns: int = Field(default=30, ge=1, le=100)
    image_generation_enabled: bool = True


class PublicBotConfig(BaseModel):
    bot_name: str
    headline: str
    subheadline: str
    welcome_message: str
    research_note: str
    avatar_label: str
    accent_color: str
    starter_prompts: list[str]
    max_turns: int
    image_generation_enabled: bool


class StartSessionRequest(BaseModel):
    participant_id: Optional[str] = None
    study_condition: Optional[str] = None


class StartSessionResponse(BaseModel):
    session_id: str
    bot_name: str
    welcome_message: str
    max_turns: int
    survey_code_delay_seconds: int
    recovery: "SessionRecovery"


class SessionRecovery(BaseModel):
    session_id: str
    participant_id: Optional[str]
    study_condition: Optional[str]
    bot_name: str
    config_snapshot: dict[str, Any]
    visual_identity: Optional[str] = None
    localized_scene: Optional[dict[str, str]] = None
    signature_outfit: Optional[dict[str, Any]] = None
    survey_code: str
    survey_code_issued: bool = False
    messages: list[dict] = Field(default_factory=list)
    created_at: str
    interaction_started_at: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)
    recovery: Optional["SessionRecovery"] = None


class ChatResponse(BaseModel):
    session_id: str
    kind: str
    reply: str
    turn_number: int
    image_data_url: Optional[str] = None
    image_url: Optional[str] = None
    recovery: "SessionRecovery"


class SurveyCodeResponse(BaseModel):
    session_id: str
    survey_code: str
    reply: str


class SurveyCodeRequest(BaseModel):
    session_id: str


class TranscriptResponse(BaseModel):
    session_id: str
    participant_id: Optional[str]
    study_condition: Optional[str]
    bot_name: str
    messages: list[dict]
    total_turns: int
