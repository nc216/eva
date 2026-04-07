IMAGE_VERBS = (
    "generate",
    "create",
    "make",
    "draw",
    "illustrate",
    "paint",
    "render",
    "design",
    "show",
    "send",
)

IMAGE_NOUNS = (
    "image",
    "picture",
    "pic",
    "photo",
    "portrait",
    "illustration",
    "drawing",
    "art",
    "avatar",
    "logo",
    "wallpaper",
    "visual",
)

FOLLOW_UP_REQUESTS = (
    "yes",
    "yeah",
    "yep",
    "send it",
    "show it",
    "where is it",
    "where's it",
    "dont see it",
    "don't see it",
    "resend it",
    "send again",
    "show me",
)

FOLLOW_UP_NEW_IMAGE_REQUESTS = (
    "another one",
    "another pic",
    "another picture",
    "another photo",
    "different one",
    "different pic",
    "different picture",
    "different photo",
    "new one",
    "new pic",
    "new picture",
    "new photo",
    "take another picture",
    "take another photo",
    "second picture",
    "second pic",
    "second photo",
    "one more",
    "one more pic",
    "one more picture",
    "one more photo",
)

FOLLOW_UP_ASSISTANT_HINTS = (
    "would you like me to send it",
    "the image should appear",
    "i've created",
    "i created",
    "image",
    "picture",
)

SELF_IMAGE_PHRASES = (
    "picture of yourself",
    "photo of yourself",
    "pic of yourself",
    "image of yourself",
    "portrait of yourself",
    "picture of you",
    "photo of you",
    "pic of you",
    "image of you",
    "portrait of you",
    "picture of u",
    "photo of u",
    "pic of u",
    "what you look like",
    "what do you look like",
    "show yourself",
    "show me yourself",
    "send a selfie",
    "your selfie",
)


def resolve_image_request(
    message: str,
    history: list[dict],
    enabled: bool,
) -> dict | None:
    if not enabled:
        return None

    normalized = _normalize(message)
    last_generated = _last_generated_image(history)

    if _is_follow_up_new_image_request(normalized):
        if last_generated is not None:
            metadata = last_generated.get("metadata") or {}
            if metadata.get("preset") == "self_portrait":
                return {"action": "generate", "preset": "self_portrait", "variation": True}
            if metadata.get("image_prompt"):
                return {
                    "action": "generate",
                    "prompt": metadata["image_prompt"],
                    "variation": True,
                }

        last_prompt = _last_substantive_user_prompt(history)
        if last_prompt:
            if _is_self_image_request(_normalize(last_prompt)):
                return {"action": "generate", "preset": "self_portrait", "variation": True}
            return {"action": "generate", "prompt": last_prompt, "variation": True}

    if _is_direct_image_request(normalized):
        if _looks_like_variation_request(normalized) and last_generated is not None:
            metadata = last_generated.get("metadata") or {}
            if metadata.get("preset") == "self_portrait":
                return {"action": "generate", "preset": "self_portrait", "variation": True}
            if metadata.get("image_prompt"):
                return {
                    "action": "generate",
                    "prompt": metadata["image_prompt"],
                    "variation": True,
                }
        if _is_self_image_request(normalized):
            return {"action": "generate", "preset": "self_portrait"}
        return {"action": "generate", "prompt": message.strip()}

    if _is_follow_up_request(normalized):
        if last_generated is not None:
            return {"action": "resend"}

        last_prompt = _last_substantive_user_prompt(history)
        last_assistant = _last_assistant_text(history)
        if last_prompt and _assistant_was_talking_about_image(last_assistant):
            return {"action": "generate", "prompt": last_prompt}

    return None


def _normalize(message: str) -> str:
    return " ".join(message.lower().strip().split())


def _is_direct_image_request(normalized: str) -> bool:
    if normalized.startswith("/image"):
        return True

    if _is_self_image_request(normalized):
        return True

    if any(verb in normalized for verb in IMAGE_VERBS) and any(
        noun in normalized for noun in IMAGE_NOUNS
    ):
        return True

    if "show me" in normalized and any(noun in normalized for noun in IMAGE_NOUNS):
        return True

    return False


def _is_follow_up_request(normalized: str) -> bool:
    return normalized in FOLLOW_UP_REQUESTS


def _is_follow_up_new_image_request(normalized: str) -> bool:
    if normalized in FOLLOW_UP_NEW_IMAGE_REQUESTS:
        return True

    return _looks_like_variation_request(normalized)


def _is_self_image_request(normalized: str) -> bool:
    if any(phrase in normalized for phrase in SELF_IMAGE_PHRASES):
        return True

    return (
        any(verb in normalized for verb in ("send", "show", "create", "generate", "make"))
        and any(noun in normalized for noun in ("picture", "pic", "photo", "image", "portrait", "selfie"))
        and any(pronoun in normalized for pronoun in ("you", "u"))
    )


def _looks_like_variation_request(normalized: str) -> bool:
    variation_cues = (
        "another",
        "different",
        "new",
        "second",
        "one more",
        "more",
    )
    image_terms = (
        "image",
        "picture",
        "pic",
        "photo",
        "portrait",
        "selfie",
        "shot",
        "one",
    )

    if any(cue in normalized for cue in variation_cues) and any(
        term in normalized for term in image_terms
    ):
        return True

    if any(cue in normalized for cue in variation_cues) and any(
        phrase in normalized
        for phrase in ("of you", "of u", "yourself", "you", "u")
    ):
        return True

    return False


def _assistant_was_talking_about_image(text: str | None) -> bool:
    if not text:
        return False
    normalized = _normalize(text)
    return any(hint in normalized for hint in FOLLOW_UP_ASSISTANT_HINTS)


def _last_assistant_text(history: list[dict]) -> str | None:
    for message in reversed(history):
        if message["role"] == "assistant":
            return message["content"]
    return None


def _last_generated_image(history: list[dict]) -> dict | None:
    for message in reversed(history):
        metadata = message.get("metadata") or {}
        if metadata.get("kind") == "image" and metadata.get("image_url"):
            return message
    return None


def _last_substantive_user_prompt(history: list[dict]) -> str | None:
    for message in reversed(history):
        if message["role"] != "user":
            continue
        normalized = _normalize(message["content"])
        if not _is_follow_up_request(normalized) and not _is_follow_up_new_image_request(normalized):
            return message["content"]
    return None
