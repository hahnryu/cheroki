"""reviewer 모듈 테스트."""

from cheroki.transcriber import Segment, TranscriptionResult
from cheroki.dictionary import Dictionary
from cheroki.reviewer import extract_suspicious, generate_questions


def _make_result(segments: list[Segment]) -> TranscriptionResult:
    return TranscriptionResult(
        source_file="test.wav",
        language="ko",
        language_probability=0.98,
        duration=30.0,
        segments=segments,
    )


def test_low_confidence_detected():
    result = _make_result([
        Segment(start=0.0, end=3.0, text="안녕하세요", confidence=0.95),
        Segment(start=3.0, end=6.0, text="어쩌구 저쩌구", confidence=0.4),
        Segment(start=6.0, end=9.0, text="감사합니다", confidence=0.9),
    ])
    sus = extract_suspicious(result, min_confidence=0.7)
    assert len(sus) == 1
    assert sus[0].segment_index == 1
    assert "낮은 신뢰도" in sus[0].reasons[0]


def test_high_confidence_not_flagged():
    result = _make_result([
        Segment(start=0.0, end=3.0, text="안녕하세요", confidence=0.95),
        Segment(start=3.0, end=6.0, text="감사합니다", confidence=0.85),
    ])
    sus = extract_suspicious(result, min_confidence=0.7)
    assert len(sus) == 0


def test_short_text_long_duration():
    result = _make_result([
        Segment(start=0.0, end=5.0, text="음", confidence=0.8),
    ])
    sus = extract_suspicious(result, min_confidence=0.5)
    assert len(sus) == 1
    assert "짧은 텍스트" in sus[0].reasons[0]


def test_unknown_proper_noun_detected():
    d = Dictionary()
    d.add("Cheroki", "products")

    result = _make_result([
        Segment(start=0.0, end=3.0, text="I used Siltarae yesterday", confidence=0.9),
    ])
    sus = extract_suspicious(result, dictionary=d, min_confidence=0.5)
    assert len(sus) == 1
    assert "Siltarae" in sus[0].unknown_words


def test_known_proper_noun_not_flagged():
    d = Dictionary()
    d.add("Cheroki", "products")

    result = _make_result([
        Segment(start=0.0, end=3.0, text="Using Cheroki today", confidence=0.9),
    ])
    sus = extract_suspicious(result, dictionary=d, min_confidence=0.5)
    assert len(sus) == 0


def test_generate_questions_with_context():
    result = _make_result([
        Segment(start=0.0, end=3.0, text="첫 번째 문장", confidence=0.95),
        Segment(start=3.0, end=6.0, text="의심스러운 문장", confidence=0.4),
        Segment(start=6.0, end=9.0, text="세 번째 문장", confidence=0.9),
    ])
    sus = extract_suspicious(result, min_confidence=0.7)
    questions = generate_questions(result, sus)

    assert len(questions) == 1
    q = questions[0]
    assert q.segment_index == 1
    assert q.timestamp == "00:03-00:06"
    assert q.current_text == "의심스러운 문장"
    assert q.context_before == "첫 번째 문장"
    assert q.context_after == "세 번째 문장"


def test_generate_questions_first_segment_no_context_before():
    result = _make_result([
        Segment(start=0.0, end=3.0, text="의심", confidence=0.3),
        Segment(start=3.0, end=6.0, text="다음 문장", confidence=0.9),
    ])
    sus = extract_suspicious(result, min_confidence=0.7)
    questions = generate_questions(result, sus)

    assert len(questions) == 1
    assert questions[0].context_before == ""
    assert questions[0].context_after == "다음 문장"


def test_generate_questions_last_segment_no_context_after():
    result = _make_result([
        Segment(start=0.0, end=3.0, text="이전 문장", confidence=0.9),
        Segment(start=3.0, end=6.0, text="의심", confidence=0.3),
    ])
    sus = extract_suspicious(result, min_confidence=0.7)
    questions = generate_questions(result, sus)

    assert len(questions) == 1
    assert questions[0].context_before == "이전 문장"
    assert questions[0].context_after == ""


def test_multiple_reasons():
    d = Dictionary()
    result = _make_result([
        Segment(start=0.0, end=5.0, text="X", confidence=0.3),
    ])
    sus = extract_suspicious(result, dictionary=d, min_confidence=0.7)
    assert len(sus) == 1
    assert len(sus[0].reasons) >= 2  # 낮은 신뢰도 + 짧은 텍스트
