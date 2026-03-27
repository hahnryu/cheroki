"""corrector 모듈 테스트."""

import tempfile
from pathlib import Path

from cheroki.transcriber import Segment, TranscriptionResult
from cheroki.corrector import (
    Correction,
    CorrectionSet,
    apply_corrections,
    save_corrections,
    load_corrections,
)


def _make_result() -> TranscriptionResult:
    return TranscriptionResult(
        source_file="test.wav",
        language="ko",
        language_probability=0.98,
        duration=9.0,
        segments=[
            Segment(start=0.0, end=3.0, text="안녕하세여", confidence=0.6),
            Segment(start=3.0, end=6.0, text="잘못된 텍스트", confidence=0.4),
            Segment(start=6.0, end=9.0, text="정상 텍스트", confidence=0.95),
        ],
    )


def test_apply_corrections_changes_text():
    result = _make_result()
    corrections = [
        Correction(segment_index=0, original_text="안녕하세여", corrected_text="안녕하세요"),
        Correction(segment_index=1, original_text="잘못된 텍스트", corrected_text="올바른 텍스트"),
    ]
    corrected = apply_corrections(result, corrections)

    assert corrected.segments[0].text == "안녕하세요"
    assert corrected.segments[1].text == "올바른 텍스트"
    assert corrected.segments[2].text == "정상 텍스트"  # 변경 안 됨


def test_apply_corrections_sets_confidence_1():
    result = _make_result()
    corrections = [
        Correction(segment_index=0, original_text="안녕하세여", corrected_text="안녕하세요"),
    ]
    corrected = apply_corrections(result, corrections)
    assert corrected.segments[0].confidence == 1.0


def test_apply_corrections_preserves_original():
    result = _make_result()
    original_text = result.segments[0].text

    corrections = [
        Correction(segment_index=0, original_text="안녕하세여", corrected_text="안녕하세요"),
    ]
    apply_corrections(result, corrections)

    # 원본은 변경되지 않아야 한다
    assert result.segments[0].text == original_text


def test_apply_corrections_ignores_invalid_index():
    result = _make_result()
    corrections = [
        Correction(segment_index=99, original_text="없음", corrected_text="없음"),
    ]
    corrected = apply_corrections(result, corrections)
    # 에러 없이 무시
    assert len(corrected.segments) == 3


def test_save_and_load_corrections():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cs = CorrectionSet(
            file_id="test_file",
            corrections=[
                Correction(segment_index=0, original_text="틀림", corrected_text="맞음"),
                Correction(segment_index=2, original_text="또틀림", corrected_text="또맞음"),
            ],
        )
        path = save_corrections(cs, tmp)
        assert path.exists()

        loaded = load_corrections(path)
        assert loaded.file_id == "test_file"
        assert len(loaded.corrections) == 2
        assert loaded.corrections[0].corrected_text == "맞음"
        assert loaded.corrections[1].corrected_text == "또맞음"
        assert loaded.created_at != ""  # 타임스탬프 자동 설정
