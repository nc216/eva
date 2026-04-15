from base64 import b64decode
from html import escape

from openai import AsyncOpenAI

from app import config

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if _client is None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _build_messages(
    system_prompt: str,
    transcript: list[dict],
    user_message: str,
) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    for message in transcript:
        if message["role"] in {"user", "assistant"}:
            messages.append({"role": message["role"], "content": message["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


async def generate_text_reply(
    system_prompt: str,
    transcript: list[dict],
    user_message: str,
    temperature: float,
) -> str:
    if config.MOCK_MODE or not config.OPENAI_API_KEY:
        return _mock_text_reply(user_message, transcript)

    client = get_client()
    response = await client.chat.completions.create(
        model=config.OPENAI_CHAT_MODEL,
        messages=_build_messages(system_prompt, transcript, user_message),
        temperature=temperature,
        max_tokens=700,
    )
    content = response.choices[0].message.content or ""
    return content.strip()


async def generate_image_bytes(
    user_message: str,
    image_style_prompt: str,
) -> bytes:
    if config.MOCK_MODE or not config.OPENAI_API_KEY:
        return _mock_image_bytes(user_message)

    client = get_client()
    response = await client.images.generate(
        model=config.OPENAI_IMAGE_MODEL,
        prompt=f"{image_style_prompt}\n\nUser request: {user_message}",
        size="1024x1024",
        quality=config.OPENAI_IMAGE_QUALITY,
        output_format=config.OPENAI_IMAGE_FORMAT,
    )
    image_base64 = response.data[0].b64_json
    return b64decode(image_base64)


def _mock_text_reply(user_message: str, transcript: list[dict]) -> str:
    turn_number = sum(1 for message in transcript if message["role"] == "user") + 1
    normalized = user_message.strip().lower()
    if any(keyword in normalized for keyword in ("image", "picture", "draw", "illustrate")):
        return (
            "Mock mode is active, so I generated a placeholder image instead of calling a live model. "
            "The production version will return a model-generated image here."
        )
    return (
        f"Mock response {turn_number}: I received your message: \"{user_message}\". "
        "This local preview is working, and once you add an OpenAI API key the backend will switch to live responses."
    )


def _mock_image_bytes(user_message: str) -> bytes:
    safe_prompt = escape(user_message[:120])
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
      <defs>
        <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#1a1416" />
          <stop offset="100%" stop-color="#8f5e39" />
        </linearGradient>
      </defs>
      <rect width="1024" height="1024" fill="url(#bg)" />
      <circle cx="512" cy="360" r="160" fill="rgba(255,255,255,0.10)" />
      <circle cx="512" cy="360" r="108" fill="#f0b47a" />
      <text x="512" y="620" text-anchor="middle" fill="#f6efe9" font-size="52" font-family="Arial, sans-serif">
        Mock image preview
      </text>
      <text x="512" y="700" text-anchor="middle" fill="#f6efe9" font-size="28" font-family="Arial, sans-serif">
        {safe_prompt}
      </text>
    </svg>
    """.strip()
    return svg.encode("utf-8")
