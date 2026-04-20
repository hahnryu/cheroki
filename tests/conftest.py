from __future__ import annotations

import pytest

from cheroki.core.types import TranscriptionMetadata, Utterance


@pytest.fixture
def sample_utterances() -> list[Utterance]:
    return [
        Utterance(speaker=0, start=0.0, end=3.25, text="안녕하세요, 오늘은 족보 이야기입니다.", confidence=0.97),
        Utterance(speaker=1, start=3.30, end=7.80, text="네, 증조부 때부터 시작하죠.", confidence=0.95),
        Utterance(speaker=0, start=8.0, end=12.5, text="고맙습니다.", confidence=0.92),
    ]


@pytest.fixture
def sample_metadata() -> TranscriptionMetadata:
    return TranscriptionMetadata(
        duration_sec=12.5,
        speaker_count=2,
        language="ko",
        model="nova-2",
        provider="deepgram",
    )
