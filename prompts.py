"""
Prompt templates cho Gemini dịch phụ đề (từ pyvideotrans).
Mỗi style có 2 variant: batch (hàng loạt) và roleplay (phân vai).
"""

import os
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent / "prompts"

# Map style → prompt file name
STYLE_FILES = {
    "default": "gemini_default.txt",
    "dialogue": "gemini_dialogue.txt",
    "review": "gemini_review.txt",
    "tutorial": "gemini_tutorial.txt",
}

# Cache prompt content
_cache = {}

def _load_prompt(style: str) -> str:
    """Load prompt từ file và cache."""
    if style in _cache:
        return _cache[style]
    filename = STYLE_FILES.get(style, "gemini_default.txt")
    filepath = _PROMPT_DIR / filename
    if not filepath.exists():
        filepath = _PROMPT_DIR / "gemini_default.txt"
    content = filepath.read_text(encoding="utf-8-sig", errors="ignore")
    # Thay placeholder {lang} = Vietnamese
    content = content.replace("{lang}", "Vietnamese")
    _cache[style] = content
    return content


def build_batch_prompt(ocr_texts: list, style: str = "default", topic: str = None) -> str:
    """
    Build prompt cho chế độ dịch hàng loạt (không phân vai).
    Dùng prompt gốc từ file nhưng rút gọn + ép output text-only.
    """
    prompt = _load_prompt(style)

    batch_text = "\n---\n".join(
        f"[{i+1}] {t}" for i, t in enumerate(ocr_texts) if t.strip()
    )

    topic_line = ""
    if topic and topic.strip():
        topic_line = f"\n\n# VIDEO TOPIC\nThis video is about: {topic.strip()}. Use appropriate specialized terminology.\n"

    return (
        "You are an expert subtitle translator. Translate each Chinese segment below into natural spoken Vietnamese.\n"
        "Return ONLY translations, one per line, in exact order. No numbers, no prefixes, no comments.\n\n"
        "TRANSLATION STYLE GUIDELINES:\n"
        + _extract_style_rules(prompt)
        + "\n\n"
        "CRITICAL RULES:\n"
        "1. Each block must be self-contained and natural when spoken alone.\n"
        "2. Keep translations concise — similar speaking duration as original.\n"
        "3. Vietnamese length must not exceed original by more than 10%.\n"
        "4. Prefer short, natural, spoken Vietnamese over literal translation.\n"
        + topic_line +
        "\n# TEXT TO TRANSLATE:\n" + batch_text
    )


def _extract_style_rules(prompt: str) -> str:
    """Extract key style rules từ full prompt để nhét vào batch prompt."""
    lines = []
    capture = False
    for line in prompt.split("\n"):
        stripped = line.strip()
        # Capture sections that define style/role/persona
        if stripped.startswith("#") and any(kw in stripped.lower() for kw in ["role", "style", "tone", "persona", "voice", "register", "overriding", "hard rule"]):
            capture = True
        elif stripped.startswith("#") and capture:
            capture = False
        if capture and stripped and not stripped.startswith("# TODO") and not stripped.startswith("# ACTUAL"):
            # Simplify: chỉ lấy tối đa 15 dòng style
            if len(lines) < 15:
                lines.append(stripped)
    return "\n".join(lines) if lines else "- Translate naturally, as if speaking in a conversation."


def build_roleplay_prompt(ocr_texts: list, style: str = "default", topic: str = None) -> str:
    """
    Build prompt cho chế độ dịch + phân vai (có speaker prediction).
    Dùng prompt gốc từ file + thêm instruction phân vai.
    """
    prompt = _load_prompt(style)

    batch_text = "\n---\n".join(
        f"[{i+1}] {t}" for i, t in enumerate(ocr_texts) if t.strip()
    )

    topic_line = ""
    if topic and topic.strip():
        topic_line = f"\n\n# VIDEO TOPIC\nThis video is about: {topic.strip()}. Use appropriate specialized terminology.\n"

    # Lấy style rules ngắn gọn
    style_rules = _extract_style_rules(prompt)

    return (
        prompt
        + topic_line +
        "\n\n# ADDITIONAL INSTRUCTION: Predict speakers (Speaker A for female/default, Speaker B for male/others). Return JSON with 'translation' and 'speaker' for each block.\n"
        + "\n# TEXT TO TRANSLATE:\n" + batch_text
    )
