"""AI 교정 제안 모듈 — Claude Sonnet으로 전사 오류를 감지하고 교정을 제안한다."""

from __future__ import annotations

import json
import structlog
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any

logger = structlog.get_logger()


@dataclass
class CorrectionSuggestion:
    """AI가 제안하는 교정."""
    segment_index: int
    timestamp: str
    original: str
    suggested: str
    reason: str


def suggest_corrections_ai(
    segments: list[dict[str, Any]],
    api_key: str,
    context: str = "",
    model: str = "claude-sonnet-4-20250514",
) -> list[CorrectionSuggestion]:
    """Claude API로 전사 결과의 오류를 감지하고 교정을 제안한다.

    Args:
        segments: [{"index": 0, "start": 0.0, "text": "..."}, ...]
        api_key: Anthropic API 키
        context: 추가 맥락 (화자, 주제 등)
        model: Claude 모델명
    """
    if not api_key:
        return []

    # 세그먼트를 텍스트로 포맷
    lines = []
    for seg in segments:
        ts = _fmt_ts(seg["start"])
        lines.append(f"[{seg['index']}] [{ts}] {seg['text']}")
    transcript_text = "\n".join(lines)

    prompt = (
        "다음은 한국어+영어 혼용 음성 전사(Whisper) 결과입니다. "
        "전사 오류를 찾아 교정을 제안해주세요.\n\n"
        "오류 유형: 잘못 들은 단어, 고유명사 오류, 문맥상 맞지 않는 단어, 불분명한 표현\n"
        "정상적인 구어체 표현은 교정하지 마세요.\n\n"
    )
    if context:
        prompt += f"맥락: {context}\n\n"
    prompt += f"전사 결과:\n{transcript_text}\n\n"
    prompt += (
        "JSON 배열로 응답해주세요. 교정이 필요한 세그먼트만:\n"
        '[{"index": 0, "original": "잘못된 부분", "suggested": "교정", "reason": "사유"}]\n'
        "교정할 것이 없으면 빈 배열 []을 반환하세요."
    )

    payload = json.dumps({
        "model": model,
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("claude_api_error", status=e.code, body=error_body[:300])
        return []

    # 응답 파싱
    text_content = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text_content += block["text"]

    # JSON 추출
    suggestions = _parse_json_from_text(text_content)

    result = []
    seg_map = {seg["index"]: seg for seg in segments}
    for s in suggestions:
        idx = s.get("index", -1)
        seg = seg_map.get(idx)
        if not seg:
            continue
        result.append(CorrectionSuggestion(
            segment_index=idx,
            timestamp=_fmt_ts(seg["start"]),
            original=s.get("original", ""),
            suggested=s.get("suggested", ""),
            reason=s.get("reason", ""),
        ))

    logger.info("ai_review_complete", suggestions=len(result))
    return result


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _parse_json_from_text(text: str) -> list[dict]:
    """텍스트에서 JSON 배열을 추출한다."""
    text = text.strip()
    # 코드블록 안에 있을 수 있음
    if "```" in text:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # [ ] 부분만 추출 시도
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return []
