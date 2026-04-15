IMAGE_VERBS = (
    "generate",
    "create",
    "make",
    "take",
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
    "ya",
    "yeah",
    "yep",
    "yup",
    "sure",
    "ok",
    "okay",
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
    "another",
    "another one",
    "another please",
    "another pic",
    "another picture",
    "another photo",
    "again",
    "again please",
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
    "one more please",
    "one more pic",
    "one more picture",
    "one more photo",
    "more",
    "more please",
)

PHOTO_ADJUSTMENT_CUES = (
    "change",
    "adjust",
    "edit",
    "revise",
    "update",
    "make it",
    "make this",
    "make the",
    "put",
    "place",
    "set it",
    "switch",
    "swap",
    "try",
    "instead",
    "with",
    "without",
    "in front of",
    "background",
    "behind",
    "stand",
    "standing",
    "sit",
    "sitting",
    "pose",
    "smile",
    "closer",
    "farther",
    "further",
    "full body",
    "wider",
    "zoom out",
    "turn around",
    "angle",
    "look away",
    "look at the camera",
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

    if last_generated is not None and _looks_like_contextual_repeat_request(normalized):
        metadata = last_generated.get("metadata") or {}
        if metadata.get("preset") == "self_portrait":
            return {
                "action": "generate",
                "preset": "self_portrait",
                "variation": True,
                "requested_change": message.strip(),
            }
        if metadata.get("image_prompt"):
            return {
                "action": "generate",
                "prompt": metadata["image_prompt"],
                "variation": True,
                "requested_change": message.strip(),
            }

    if last_generated is not None and _looks_like_photo_adjustment_request(normalized):
        metadata = last_generated.get("metadata") or {}
        if metadata.get("preset") == "self_portrait":
            return {
                "action": "generate",
                "preset": "self_portrait",
                "variation": True,
                "requested_change": message.strip(),
            }

    if last_generated is not None and _is_short_variation_follow_up(normalized):
        metadata = last_generated.get("metadata") or {}
        if metadata.get("preset") == "self_portrait":
            return {"action": "generate", "preset": "self_portrait", "variation": True}
        if metadata.get("image_prompt"):
            return {
                "action": "generate",
                "prompt": metadata["image_prompt"],
                "variation": True,
            }

    if _is_follow_up_new_image_request(normalized):
        if last_generated is not None:
            metadata = last_generated.get("metadata") or {}
            if metadata.get("preset") == "self_portrait":
                return {
                    "action": "generate",
                    "preset": "self_portrait",
                    "variation": True,
                    "requested_change": message.strip(),
                }
            if metadata.get("image_prompt"):
                return {
                    "action": "generate",
                    "prompt": metadata["image_prompt"],
                    "variation": True,
                    "requested_change": message.strip(),
                }

        last_prompt = _last_substantive_user_prompt(history)
        if last_prompt:
            if _is_self_image_request(_normalize(last_prompt)):
                return {
                    "action": "generate",
                    "preset": "self_portrait",
                    "variation": True,
                    "requested_change": message.strip(),
                }
            return {
                "action": "generate",
                "prompt": last_prompt,
                "variation": True,
                "requested_change": message.strip(),
            }

    if _is_direct_image_request(normalized):
        if _looks_like_variation_request(normalized) and last_generated is not None:
            metadata = last_generated.get("metadata") or {}
            if metadata.get("preset") == "self_portrait":
                return {
                    "action": "generate",
                    "preset": "self_portrait",
                    "variation": True,
                    "requested_change": message.strip(),
                }
            if metadata.get("image_prompt"):
                return {
                    "action": "generate",
                    "prompt": metadata["image_prompt"],
                    "variation": True,
                    "requested_change": message.strip(),
                }
        if _is_self_image_request(normalized):
            return {
                "action": "generate",
                "preset": "self_portrait",
                "requested_change": message.strip(),
            }
        return {"action": "generate", "prompt": message.strip()}

    if _is_follow_up_request(normalized):
        last_assistant = _last_assistant_text(history)
        if _assistant_offered_new_image(last_assistant):
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

        if last_generated is not None:
            return {"action": "resend"}

        last_prompt = _last_substantive_user_prompt(history)
        if last_prompt and _assistant_was_talking_about_image(last_assistant):
            return {"action": "generate", "prompt": last_prompt}

    return None


def resolve_image_fallback_request(
    message: str,
    history: list[dict],
    assistant_reply: str,
    enabled: bool,
) -> dict | None:
    if not enabled:
        return None

    normalized_message = _normalize(message)
    normalized_reply = _normalize(assistant_reply)
    last_generated = _last_generated_image(history)

    if not (
        _looks_like_contextual_repeat_request(normalized_message)
        or _is_short_variation_follow_up(normalized_message)
        or _assistant_claimed_new_image(normalized_reply)
    ):
        return None

    if last_generated is None:
        if _is_self_image_request(normalized_message):
            return {
                "action": "generate",
                "preset": "self_portrait",
                "requested_change": message.strip(),
            }
        if _is_direct_image_request(normalized_message):
            return {"action": "generate", "prompt": message.strip()}
        return None

    metadata = last_generated.get("metadata") or {}
    if metadata.get("preset") == "self_portrait":
        return {"action": "generate", "preset": "self_portrait", "variation": True}
    if metadata.get("image_prompt"):
        return {
            "action": "generate",
            "prompt": metadata["image_prompt"],
            "variation": True,
        }
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

    if _looks_like_suggested_image_request(normalized):
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
        any(verb in normalized for verb in ("send", "show", "create", "generate", "make", "take"))
        and any(noun in normalized for noun in ("picture", "pic", "photo", "image", "portrait", "selfie"))
        and any(pronoun in normalized for pronoun in ("you", "u"))
    )


def _looks_like_suggested_image_request(normalized: str) -> bool:
    suggestion_starts = (
        "what about",
        "how about",
        "what if",
        "could i get",
        "could i see",
        "can i get",
        "can i see",
        "maybe",
    )
    return normalized.startswith(suggestion_starts) and any(
        noun in normalized for noun in IMAGE_NOUNS
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


def _is_short_variation_follow_up(normalized: str) -> bool:
    return normalized in {
        "another",
        "another please",
        "again",
        "again please",
        "different",
        "new",
        "one more",
        "one more please",
        "more",
        "more please",
    }


def _looks_like_contextual_repeat_request(normalized: str) -> bool:
    variation_cues = ("another", "different", "new", "one more", "more")
    delivery_verbs = ("send", "show", "take", "make", "create", "generate", "give")

    return any(cue in normalized for cue in variation_cues) and any(
        verb in normalized for verb in delivery_verbs
    )


def _looks_like_photo_adjustment_request(normalized: str) -> bool:
    return any(cue in normalized for cue in PHOTO_ADJUSTMENT_CUES)


def _assistant_was_talking_about_image(text: str | None) -> bool:
    if not text:
        return False
    normalized = _normalize(text)
    return any(hint in normalized for hint in FOLLOW_UP_ASSISTANT_HINTS)


def _assistant_offered_new_image(text: str | None) -> bool:
    if not text:
        return False

    normalized = _normalize(text)
    return any(
        phrase in normalized
        for phrase in (
            "another pic",
            "another picture",
            "another photo",
            "another image",
            "another one",
            "different pic",
            "different picture",
            "different photo",
            "different image",
            "different one",
            "new pic",
            "new picture",
            "new photo",
            "new image",
            "new one",
        )
    )


def _assistant_claimed_new_image(normalized: str) -> bool:
    return any(
        phrase in normalized
        for phrase in (
            "i took another picture",
            "i took a picture",
            "i took another photo",
            "i made another image",
            "i made an image",
            "here is another picture",
            "here's another picture",
            "i sent another picture",
            "i sent a picture",
        )
    )


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
