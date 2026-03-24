from typing import Optional

from pydantic import BaseModel, Field


class BotConfig(BaseModel):
    bot_name: str = "Aster"
    headline: str = "A research-ready conversational agent with a premium interface."
    subheadline: str = "Built for participant studies, guided interactions, and controlled prompt behavior."
    welcome_message: str = "Hi, I'm Aster. Ask me anything."
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
    image_style_prompt: str = (
        "Create a polished, cinematic, visually coherent image with elegant lighting."
    )
    self_image_prompt: str = (
        "Create a photorealistic portrait of a single approachable adult person looking into the camera. "
        "Use natural skin tones, soft flattering light, a neutral background, and a warm but realistic expression. "
        "Do not add text, logos, multiple people, masks, helmets, or surreal elements."
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


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    session_id: str
    kind: str
    reply: str
    turn_number: int
    image_data_url: Optional[str] = None
    image_url: Optional[str] = None


class TranscriptResponse(BaseModel):
    session_id: str
    participant_id: Optional[str]
    study_condition: Optional[str]
    bot_name: str
    messages: list[dict]
    total_turns: int
