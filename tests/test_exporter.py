from __future__ import annotations

from cheroki.core.exporter import to_markdown, to_srt, to_txt


def test_srt_basic(sample_utterances):
    srt = to_srt(sample_utterances)
    assert "00:00:00,000 --> 00:00:03,250" in srt
    assert "S0: 안녕하세요" in srt
    assert "S1: 네, 증조부" in srt
    # 번호가 1부터 시작
    assert srt.startswith("1\n")


def test_srt_milliseconds_precision():
    from cheroki.core.types import Utterance
    u = Utterance(speaker=0, start=1.234, end=2.567, text="hi", confidence=0.9)
    srt = to_srt([u])
    assert "00:00:01,234 --> 00:00:02,567" in srt


def test_markdown_has_frontmatter(sample_utterances, sample_metadata):
    md = to_markdown(sample_utterances, sample_metadata, title="테스트 인터뷰")
    assert md.startswith("---\n")
    assert "title: 테스트 인터뷰" in md
    assert "duration: 00:00:12" in md
    assert "speakers: 2" in md
    assert "model: nova-2" in md
    assert "**[S0 00:00:00]**" in md


def test_markdown_no_title(sample_utterances, sample_metadata):
    md = to_markdown(sample_utterances, sample_metadata)
    assert "title: 녹취" in md


def test_txt_is_plain(sample_utterances):
    txt = to_txt(sample_utterances)
    assert "안녕하세요" in txt
    assert "S0" not in txt
    assert "00:00" not in txt
    # 줄바꿈 구분
    assert txt.count("\n") >= 3
