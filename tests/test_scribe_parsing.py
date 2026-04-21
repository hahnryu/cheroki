"""ElevenLabs Scribe 응답 파싱 테스트. 실제 API 호출 없음."""
from __future__ import annotations

import math

import pytest

from cheroki.core.transcribers.scribe import ScribeTranscriber, _group_words_by_speaker

SAMPLE_RESPONSE = {
    "language_code": "ko",
    "language_probability": 0.99,
    "text": "안녕하세요 좋습니다 네 그렇죠",
    "audio_duration_secs": 10.5,
    "words": [
        {"text": "안녕하세요", "start": 0.0, "end": 1.2, "type": "word",
         "speaker_id": "speaker_0", "logprob": -0.1},
        {"text": " ", "start": 1.2, "end": 1.25, "type": "spacing",
         "speaker_id": "speaker_0"},
        {"text": "좋습니다", "start": 1.25, "end": 2.3, "type": "word",
         "speaker_id": "speaker_0", "logprob": -0.2},
        {"text": "네", "start": 3.5, "end": 3.9, "type": "word",
         "speaker_id": "speaker_1", "logprob": -0.3},
        {"text": " ", "start": 3.9, "end": 3.95, "type": "spacing",
         "speaker_id": "speaker_1"},
        {"text": "그렇죠", "start": 3.95, "end": 4.8, "type": "word",
         "speaker_id": "speaker_1", "logprob": -0.1},
        {"text": "[laughter]", "start": 4.8, "end": 5.2, "type": "audio_event",
         "speaker_id": "speaker_1"},
    ],
}


def test_parse_basic():
    t = ScribeTranscriber(api_key="fake")
    result = t._parse(SAMPLE_RESPONSE)

    assert len(result.utterances) == 2
    u0, u1 = result.utterances

    assert u0.speaker == 0
    assert u0.start == 0.0
    assert u0.end == pytest.approx(2.3)
    assert u0.text == "안녕하세요 좋습니다"
    assert 0.0 < u0.confidence <= 1.0
    assert u0.confidence == pytest.approx(math.exp(-0.15), rel=1e-3)

    assert u1.speaker == 1
    assert u1.text == "네 그렇죠"
    assert u1.start == pytest.approx(3.5)
    assert u1.end == pytest.approx(4.8)

    assert result.metadata.duration_sec == 10.5
    assert result.metadata.speaker_count == 2
    assert result.metadata.language == "ko"
    assert result.metadata.provider == "elevenlabs"
    assert result.metadata.model == "scribe_v2"
    assert result.raw_response == SAMPLE_RESPONSE


def test_parse_empty_words():
    t = ScribeTranscriber(api_key="fake")
    result = t._parse({"words": [], "audio_duration_secs": 0.0})
    assert result.utterances == []
    assert result.metadata.speaker_count == 0
    assert result.metadata.duration_sec == 0.0


def test_parse_single_speaker():
    t = ScribeTranscriber(api_key="fake")
    payload = {
        "audio_duration_secs": 3.0,
        "words": [
            {"text": "하나", "start": 0.0, "end": 1.0, "type": "word",
             "speaker_id": "speaker_0", "logprob": 0.0},
            {"text": "둘", "start": 1.5, "end": 2.0, "type": "word",
             "speaker_id": "speaker_0", "logprob": 0.0},
        ],
    }
    result = t._parse(payload)
    assert len(result.utterances) == 1
    assert result.utterances[0].speaker == 0
    assert result.metadata.speaker_count == 1


def test_group_skips_audio_events():
    # audio_event는 speaker 판단에서 제외 (박수/웃음 등 메타 이벤트).
    # 앞뒤 같은 speaker 발화는 하나로 이어진다.
    words = [
        {"text": "안녕", "start": 0.0, "end": 1.0, "type": "word",
         "speaker_id": "A", "logprob": 0.0},
        {"text": "[bg_noise]", "start": 1.0, "end": 2.0, "type": "audio_event",
         "speaker_id": "B"},
        {"text": "하세요", "start": 2.0, "end": 3.0, "type": "word",
         "speaker_id": "A", "logprob": 0.0},
    ]
    utterances = _group_words_by_speaker(words)
    assert len(utterances) == 1
    assert utterances[0].text == "안녕하세요"
    assert utterances[0].speaker == 0
    assert utterances[0].start == 0.0
    assert utterances[0].end == 3.0


def test_group_speaker_id_mapping_stable():
    # 처음 등장 순서대로 0,1,2... 매핑
    words = [
        {"text": "a", "start": 0.0, "end": 0.1, "type": "word",
         "speaker_id": "X", "logprob": 0.0},
        {"text": "b", "start": 0.2, "end": 0.3, "type": "word",
         "speaker_id": "Y", "logprob": 0.0},
        {"text": "c", "start": 0.4, "end": 0.5, "type": "word",
         "speaker_id": "X", "logprob": 0.0},
    ]
    utterances = _group_words_by_speaker(words)
    assert [u.speaker for u in utterances] == [0, 1, 0]


def test_scribe_requires_key():
    with pytest.raises(ValueError):
        ScribeTranscriber(api_key="")


def test_confidence_clamped_to_one():
    # logprob가 양수(이론상 없지만 방어)여도 1.0으로 클램프
    words = [
        {"text": "a", "start": 0.0, "end": 0.1, "type": "word",
         "speaker_id": "A", "logprob": 0.5},
    ]
    utterances = _group_words_by_speaker(words)
    assert utterances[0].confidence == 1.0
