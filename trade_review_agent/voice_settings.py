from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_OPENAI_VOICE = "alloy"
DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"

OPENAI_VOICE_OPTIONS = [
    {"value": "alloy", "label": "OpenAI Alloy"},
    {"value": "verse", "label": "OpenAI Verse"},
    {"value": "aria", "label": "OpenAI Aria"},
]

EDGE_VOICE_OPTIONS = [
    {"value": "zh-CN-XiaoxiaoNeural", "label": "Edge 晓晓"},
    {"value": "zh-CN-XiaoyiNeural", "label": "Edge 晓伊"},
    {"value": "zh-CN-YunxiNeural", "label": "Edge 云希"},
    {"value": "zh-CN-YunjianNeural", "label": "Edge 云健"},
]


@dataclass
class VoiceSettings:
    provider: str = "openai"
    openai_voice: str = DEFAULT_OPENAI_VOICE
    edge_voice: str = DEFAULT_EDGE_VOICE
    fallback_browser_voice_hint: str = "female"
    preview_text: str = "请注意，预案已经触发，请按计划执行。"


def default_voice_settings() -> VoiceSettings:
    return VoiceSettings()


def load_voice_settings(path: str | Path) -> VoiceSettings:
    path = Path(path)
    if not path.exists():
        return default_voice_settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_voice_settings()
    if not isinstance(data, dict):
        return default_voice_settings()
    settings = default_voice_settings()
    settings.provider = _provider(str(data.get("provider") or settings.provider))
    settings.openai_voice = _openai_voice(str(data.get("openai_voice") or settings.openai_voice))
    settings.edge_voice = _edge_voice(str(data.get("edge_voice") or settings.edge_voice))
    settings.fallback_browser_voice_hint = _voice_hint(
        str(data.get("fallback_browser_voice_hint") or settings.fallback_browser_voice_hint)
    )
    settings.preview_text = str(data.get("preview_text") or settings.preview_text).strip() or settings.preview_text
    return settings


def save_voice_settings(path: str | Path, settings: VoiceSettings) -> VoiceSettings:
    path = Path(path)
    normalized = normalize_voice_settings(asdict(settings))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(normalized), ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def normalize_voice_settings(payload: dict | None) -> VoiceSettings:
    data = payload or {}
    settings = default_voice_settings()
    settings.provider = _provider(str(data.get("provider") or settings.provider))
    settings.openai_voice = _openai_voice(str(data.get("openai_voice") or settings.openai_voice))
    settings.edge_voice = _edge_voice(str(data.get("edge_voice") or settings.edge_voice))
    settings.fallback_browser_voice_hint = _voice_hint(
        str(data.get("fallback_browser_voice_hint") or settings.fallback_browser_voice_hint)
    )
    preview_text = str(data.get("preview_text") or settings.preview_text).strip()
    settings.preview_text = preview_text or settings.preview_text
    return settings


def voice_settings_payload(settings: VoiceSettings) -> dict:
    return {
        "settings": asdict(settings),
        "options": {
            "provider": [
                {"value": "openai", "label": "OpenAI TTS"},
                {"value": "edge", "label": "Edge TTS"},
            ],
            "openai_voice": OPENAI_VOICE_OPTIONS,
            "edge_voice": EDGE_VOICE_OPTIONS,
            "fallback_browser_voice_hint": [
                {"value": "female", "label": "浏览器偏女声"},
                {"value": "male", "label": "浏览器偏男声"},
            ],
        },
    }


def _provider(value: str) -> str:
    return value if value in {"openai", "edge"} else "openai"


def _openai_voice(value: str) -> str:
    allowed = {item["value"] for item in OPENAI_VOICE_OPTIONS}
    return value if value in allowed else DEFAULT_OPENAI_VOICE


def _edge_voice(value: str) -> str:
    allowed = {item["value"] for item in EDGE_VOICE_OPTIONS}
    return value if value in allowed else DEFAULT_EDGE_VOICE


def _voice_hint(value: str) -> str:
    return value if value in {"female", "male"} else "female"
