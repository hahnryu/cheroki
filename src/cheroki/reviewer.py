"""의심 구간 추출 및 질문 생성 모듈."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from typing import Any

from cheroki.transcriber import TranscriptionResult, Segment
from cheroki.dictionary import Dictionary


@dataclass
class SuspiciousSegment:
    """의심 구간."""
    segment_index: int
    segment: Segment
    reasons: list[str]
    unknown_words: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["segment"] = self.segment.to_dict()
        return d


@dataclass
class ReviewQuestion:
    """교정을 위한 질문."""
    segment_index: int
    timestamp: str  # "MM:SS-MM:SS"
    current_text: str
    reasons: list[str]
    context_before: str
    context_after: str
    unknown_words: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _format_timestamp(seconds: float) -> str:
    """초를 MM:SS 형식으로."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


# 한국어 고유명사 후보 패턴: 2~5음절 연속 한글 (조사 제거 시도)
_KOREAN_NOUN_PATTERN = re.compile(r"[가-힣]{2,5}")
# 영어 고유명사 후보: 대문자 시작 단어 (문장 시작이 아닌 위치)
_ENGLISH_PROPER_PATTERN = re.compile(r"(?<!\.\s)(?<!^)\b[A-Z][a-zA-Z]+\b")
# 흔한 영어 단어는 고유명사 후보에서 제외
_COMMON_ENGLISH = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "using", "use", "get", "got", "getting", "make", "made",
    "go", "going", "gone", "come", "came", "take", "took", "taken",
    "see", "saw", "seen", "know", "knew", "known", "think", "thought",
    "say", "said", "give", "gave", "given", "tell", "told", "work",
    "call", "called", "try", "tried", "ask", "asked", "put", "keep",
    "let", "begin", "began", "seem", "help", "show", "hear", "play",
    "run", "move", "live", "believe", "bring", "happen", "write", "provide",
    "sit", "stand", "lose", "pay", "meet", "include", "continue", "set",
    "learn", "change", "lead", "understand", "watch", "follow", "stop",
    "create", "speak", "read", "allow", "add", "spend", "grow", "open",
    "walk", "win", "offer", "remember", "love", "consider", "appear",
    "buy", "wait", "serve", "die", "send", "expect", "build", "stay",
    "fall", "cut", "reach", "kill", "remain", "suggest", "raise", "pass",
    "sell", "require", "report", "decide", "pull", "today", "yesterday",
    "tomorrow", "now", "then", "here", "there", "where", "when", "what",
    "which", "who", "whom", "how", "why", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "no", "not", "only",
    "same", "so", "than", "too", "very", "just", "because", "but", "and",
    "or", "if", "while", "after", "before", "since", "until", "about",
    "between", "through", "during", "without", "again", "once", "also",
    "back", "well", "still", "even", "new", "first", "last", "long",
    "great", "little", "own", "old", "right", "big", "high", "different",
    "small", "large", "next", "early", "young", "important", "public",
    "bad", "good",
}


def extract_suspicious(
    result: TranscriptionResult,
    dictionary: Dictionary | None = None,
    min_confidence: float = 0.7,
) -> list[SuspiciousSegment]:
    """전사 결과에서 의심 구간을 추출한다."""
    suspicious: list[SuspiciousSegment] = []

    for i, seg in enumerate(result.segments):
        reasons: list[str] = []
        unknown: list[str] = []

        # 1. 낮은 confidence
        if seg.confidence < min_confidence:
            reasons.append(f"낮은 신뢰도 ({seg.confidence:.2f})")

        # 2. 짧은/불완전 세그먼트
        text_stripped = seg.text.strip()
        if len(text_stripped) <= 2 and (seg.end - seg.start) > 2.0:
            reasons.append("긴 구간에 비해 짧은 텍스트")

        # 3. 고유명사 미매칭
        if dictionary:
            # 영어 고유명사 후보
            for match in _ENGLISH_PROPER_PATTERN.finditer(text_stripped):
                word = match.group()
                if word.lower() in _COMMON_ENGLISH:
                    continue
                if not dictionary.contains(word):
                    unknown.append(word)

            if unknown:
                reasons.append(f"미등록 고유명사: {', '.join(unknown)}")

        if reasons:
            suspicious.append(SuspiciousSegment(
                segment_index=i,
                segment=seg,
                reasons=reasons,
                unknown_words=unknown,
            ))

    return suspicious


def generate_questions(
    result: TranscriptionResult,
    suspicious: list[SuspiciousSegment],
) -> list[ReviewQuestion]:
    """의심 구간에 대한 질문 목록을 생성한다."""
    questions: list[ReviewQuestion] = []
    segments = result.segments

    for sus in suspicious:
        i = sus.segment_index
        seg = sus.segment

        # 전후 맥락
        context_before = segments[i - 1].text.strip() if i > 0 else ""
        context_after = segments[i + 1].text.strip() if i < len(segments) - 1 else ""

        timestamp = f"{_format_timestamp(seg.start)}-{_format_timestamp(seg.end)}"

        questions.append(ReviewQuestion(
            segment_index=i,
            timestamp=timestamp,
            current_text=seg.text.strip(),
            reasons=sus.reasons,
            context_before=context_before,
            context_after=context_after,
            unknown_words=sus.unknown_words,
        ))

    return questions
