"""고유명사 사전 관리 모듈."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Dictionary:
    """고유명사 사전. 여러 YAML 파일에서 로드하여 통합 관리."""

    def __init__(self) -> None:
        self._entries: dict[str, set[str]] = {}

    @property
    def all_words(self) -> set[str]:
        """모든 카테고리의 단어를 합쳐 반환."""
        result: set[str] = set()
        for words in self._entries.values():
            result.update(words)
        return result

    @property
    def categories(self) -> list[str]:
        return list(self._entries.keys())

    def load_file(self, path: Path) -> None:
        """YAML 파일 하나를 로드하여 사전에 추가."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        for category, words in data.items():
            if not isinstance(words, list):
                continue
            if category not in self._entries:
                self._entries[category] = set()
            self._entries[category].update(str(w) for w in words if w)

    def load_directory(self, directory: Path) -> None:
        """디렉토리 내 모든 YAML 파일을 로드."""
        directory = Path(directory)
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.yaml")):
            self.load_file(path)
        for path in sorted(directory.glob("*.yml")):
            self.load_file(path)

    def contains(self, word: str) -> bool:
        """단어가 사전에 있는지 확인 (대소문자 무시)."""
        lower = word.lower()
        return any(lower == w.lower() for w in self.all_words)

    def get_category(self, word: str) -> str | None:
        """단어의 카테고리를 반환. 없으면 None."""
        lower = word.lower()
        for category, words in self._entries.items():
            if any(lower == w.lower() for w in words):
                return category
        return None

    def add(self, word: str, category: str = "terms") -> None:
        """단어를 사전에 추가."""
        if category not in self._entries:
            self._entries[category] = set()
        self._entries[category].add(word)

    def save_file(self, path: Path) -> None:
        """현재 사전을 YAML 파일로 저장."""
        data = {cat: sorted(words) for cat, words in self._entries.items()}
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Dictionary:
        """config에서 사전 디렉토리를 찾아 로드."""
        d = cls()
        # config.yaml에 dictionary 경로가 없으면 프로젝트 루트의 dictionary/ 사용
        dict_dir = Path(__file__).resolve().parents[2] / "dictionary"
        d.load_directory(dict_dir)
        return d
