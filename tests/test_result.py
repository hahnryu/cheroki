from __future__ import annotations

from cheroki.core.result import TranscriptionResult


def test_result_properties(sample_utterances, sample_metadata):
    result = TranscriptionResult(
        utterances=sample_utterances,
        metadata=sample_metadata,
        raw_response={"foo": "bar"},
    )
    assert result.duration_sec == 12.5
    assert result.speaker_count == 2
    assert "S0" in result.text
    assert "00:00:00" in result.text
    assert "S0" not in result.plain_text
    assert "안녕하세요" in result.plain_text


def test_result_to_srt_and_md(sample_utterances, sample_metadata):
    result = TranscriptionResult(utterances=sample_utterances, metadata=sample_metadata)
    srt = result.to_srt()
    md = result.to_markdown(title="t")
    txt = result.to_txt()
    assert "-->" in srt
    assert md.startswith("---\n")
    assert "안녕하세요" in txt


def test_result_roundtrip(sample_utterances, sample_metadata):
    result = TranscriptionResult(
        utterances=sample_utterances,
        metadata=sample_metadata,
        raw_response={"k": 1},
    )
    data = result.to_dict()
    restored = TranscriptionResult.from_dict(data)
    assert restored.duration_sec == result.duration_sec
    assert len(restored.utterances) == len(result.utterances)
    assert restored.utterances[0].text == result.utterances[0].text
    assert restored.raw_response == {"k": 1}
