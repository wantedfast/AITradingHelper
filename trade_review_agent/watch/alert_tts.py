from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_EDGE_RATE = "+8%"
DEFAULT_EDGE_PITCH = "+12Hz"


@dataclass(frozen=True)
class VoiceDraft:
    agent: str
    text: str


def generate_voice_line(base_message: str, persona: str = "可爱AI女友") -> tuple[str, list[VoiceDraft]]:
    if persona != "可爱AI女友":
        draft = VoiceDraft("专业交易员Agent", base_message)
        return draft.text, [draft]

    drafts = [
        VoiceDraft("可爱Agent", f"主人，提醒你啦，{base_message} 我们按预案走，好不好。"),
        VoiceDraft("幽默Agent", f"报告老板，行情已经敲门啦：{base_message} 别和K线谈恋爱，先执行。"),
        VoiceDraft("凶巴巴Agent", f"喂，别发呆，{base_message} 现在按计划动手，纪律第一。"),
    ]
    return _judge_pick(drafts), drafts


def synthesize_edge_tts(
    text: str,
    output_dir: str | Path,
    voice: str = DEFAULT_EDGE_VOICE,
    rate: str = DEFAULT_EDGE_RATE,
    pitch: str = DEFAULT_EDGE_PITCH,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode("utf-8")).hexdigest()[:16]
    output = output_dir / f"{key}.mp3"
    if output.exists() and output.stat().st_size > 0:
        return output

    async def _run() -> None:
        import edge_tts

        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(str(output))

    asyncio.run(_run())
    return output


def _judge_pick(drafts: list[VoiceDraft]) -> str:
    # The judge favors reminders that are short, warm, and explicit about execution.
    def score(draft: VoiceDraft) -> int:
        text = draft.text
        value = 0
        value += 4 if "按预案" in text or "按计划" in text else 0
        value += 3 if len(text) <= 90 else 0
        value += 2 if "主人" in text else 0
        value += 1 if "纪律" in text else 0
        value -= 2 if "别和K线谈恋爱" in text else 0
        return value

    return max(drafts, key=score).text
