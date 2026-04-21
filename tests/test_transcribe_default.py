"""_default_transcriber 분기 테스트. STT_PROVIDER env에 따른 선택 검증."""
from __future__ import annotations

import pytest

from cheroki.core.transcribe import _default_transcriber
from cheroki.core.transcribers.deepgram import DeepgramTranscriber
from cheroki.core.transcribers.scribe import ScribeTranscriber


def _prime_env(monkeypatch: pytest.MonkeyPatch, provider: str) -> None:
    # load_config가 _DOTENV_LOADED 플래그로 dotenv 재로드를 막기 때문에
    # os.environ를 직접 덮어쓰면 확실하다.
    monkeypatch.setenv("STT_PROVIDER", provider)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test_scribe")
    monkeypatch.setenv("ELEVENLABS_MODEL", "scribe_v2")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test_dg")
    monkeypatch.setenv("DEEPGRAM_MODEL", "nova-2")


def test_default_is_scribe(monkeypatch: pytest.MonkeyPatch):
    _prime_env(monkeypatch, "scribe")
    tr = _default_transcriber()
    assert isinstance(tr, ScribeTranscriber)
    assert tr.model == "scribe_v2"


def test_explicit_deepgram(monkeypatch: pytest.MonkeyPatch):
    _prime_env(monkeypatch, "deepgram")
    tr = _default_transcriber()
    assert isinstance(tr, DeepgramTranscriber)
    assert tr.model == "nova-2"


def test_case_insensitive_and_trim(monkeypatch: pytest.MonkeyPatch):
    _prime_env(monkeypatch, "  Scribe  ")
    tr = _default_transcriber()
    assert isinstance(tr, ScribeTranscriber)


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch):
    _prime_env(monkeypatch, "whispercpp")
    with pytest.raises(ValueError, match="STT_PROVIDER"):
        _default_transcriber()
