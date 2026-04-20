"""Deepgram 응답 파싱 테스트. 실제 API 호출 없음."""
from __future__ import annotations

from cheroki.core.transcribers.deepgram import DeepgramTranscriber

SAMPLE_RESPONSE = {
    "metadata": {
        "request_id": "abc-123",
        "duration": 45.5,
        "sha256": "deadbeef",
    },
    "results": {
        "utterances": [
            {
                "start": 0.0,
                "end": 3.25,
                "transcript": "오늘은 족보 이야기.",
                "confidence": 0.97,
                "speaker": 0,
            },
            {
                "start": 3.5,
                "end": 7.8,
                "transcript": "좋습니다.",
                "confidence": 0.95,
                "speaker": 1,
            },
            {
                "start": 8.0,
                "end": 10.0,
                "transcript": "",
                "confidence": 0.1,
                "speaker": 0,
            },
        ]
    },
}


def test_parse_basic():
    t = DeepgramTranscriber(api_key="fake")
    result = t._parse(SAMPLE_RESPONSE)
    # 빈 transcript는 제외됨
    assert len(result.utterances) == 2
    assert result.utterances[0].text == "오늘은 족보 이야기."
    assert result.utterances[0].speaker == 0
    assert result.utterances[1].speaker == 1
    assert result.metadata.duration_sec == 45.5
    assert result.metadata.speaker_count == 2
    assert result.metadata.provider == "deepgram"
    assert result.raw_response == SAMPLE_RESPONSE


def test_parse_empty_response():
    t = DeepgramTranscriber(api_key="fake")
    result = t._parse({"metadata": {"duration": 0}, "results": {"utterances": []}})
    assert result.utterances == []
    assert result.metadata.speaker_count == 0


def test_deepgram_requires_key():
    import pytest
    with pytest.raises(ValueError):
        DeepgramTranscriber(api_key="")
