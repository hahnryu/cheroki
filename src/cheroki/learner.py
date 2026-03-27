"""지능화 모듈 — 교정 패턴 학습, 고유명사 자동 추출, 자동 교정 제안."""

from __future__ import annotations

import json
import re
import structlog
from collections import Counter
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from cheroki.corpus import load_corpus_pairs, list_corpus_files
from cheroki.dictionary import Dictionary

logger = structlog.get_logger()

# ── F3-1: 고유명사 자동 추출 ─────────────────────────

# 고유명사 후보 패턴
_KOREAN_PROPER_NOUN = re.compile(r"[가-힣]{2,6}")
_ENGLISH_PROPER_NOUN = re.compile(r"[A-Z][a-zA-Z]+")

# 흔한 한국어 단어 (고유명사가 아닌 것) — 짧은 리스트, 확장 가능
_COMMON_KOREAN = {
    "그래서", "그런데", "하지만", "그리고", "그러면", "그러니까",
    "왜냐하면", "때문에", "그래도", "그러나", "그렇지만",
    "여기서", "거기서", "저기서", "이것은", "그것은", "저것은",
    "합니다", "합니다", "입니다", "있습니다", "없습니다",
    "했습니다", "됩니다", "습니다", "됐습니다", "하겠습니다",
    "안녕하세요", "감사합니다", "고맙습니다", "죄송합니다",
    "네", "예", "아니요", "아니오", "맞습니다", "그렇습니다",
}


def extract_proper_nouns_from_corrections(
    corpus_dir: Path,
    dictionary: Dictionary | None = None,
) -> dict[str, int]:
    """교정 코퍼스에서 고유명사 후보를 추출한다.

    교정된 텍스트에만 존재하고 원본에 없는 단어 = 사용자가 의도적으로 넣은 고유명사.
    반복 등장하는 단어를 높은 우선순위로.

    Returns:
        {단어: 등장횟수} — 빈도순 정렬
    """
    candidates: Counter[str] = Counter()

    for path in list_corpus_files(corpus_dir):
        data = load_corpus_pairs(path)
        for pair in data.get("pairs", []):
            original = pair.get("original", "")
            corrected = pair.get("corrected", "")

            # 교정 후에만 등장하는 단어 추출
            orig_words = set(_KOREAN_PROPER_NOUN.findall(original))
            corr_words = set(_KOREAN_PROPER_NOUN.findall(corrected))
            new_words = corr_words - orig_words

            # 영어도
            orig_eng = set(_ENGLISH_PROPER_NOUN.findall(original))
            corr_eng = set(_ENGLISH_PROPER_NOUN.findall(corrected))
            new_words.update(corr_eng - orig_eng)

            # 필터: 흔한 단어 제거, 이미 사전에 있는 것 제거
            for w in new_words:
                if w in _COMMON_KOREAN:
                    continue
                if len(w) < 2:
                    continue
                if dictionary and dictionary.contains(w):
                    continue
                candidates[w] += 1

    return dict(candidates.most_common())


def auto_update_dictionary(
    corpus_dir: Path,
    dictionary: Dictionary,
    min_frequency: int = 2,
    category: str = "auto_learned",
) -> list[str]:
    """교정 코퍼스에서 추출한 고유명사를 사전에 자동 추가한다.

    min_frequency 이상 등장한 단어만 추가.

    Returns:
        추가된 단어 리스트
    """
    candidates = extract_proper_nouns_from_corrections(corpus_dir, dictionary)
    added: list[str] = []

    for word, freq in candidates.items():
        if freq >= min_frequency:
            dictionary.add(word, category)
            added.append(word)
            logger.info("dictionary_auto_add", word=word, frequency=freq)

    return added


# ── F3-2: 교정 패턴 학습 ─────────────────────────────

@dataclass
class CorrectionPattern:
    """학습된 교정 패턴."""
    original: str
    corrected: str
    frequency: int = 1
    source_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def learn_correction_patterns(corpus_dir: Path) -> list[CorrectionPattern]:
    """교정 코퍼스에서 반복되는 교정 패턴을 학습한다.

    동일한 (원본→교정) 쌍이 여러 파일에서 반복되면 패턴으로 인정.
    """
    pattern_counts: dict[tuple[str, str], list[str]] = {}

    for path in list_corpus_files(corpus_dir):
        data = load_corpus_pairs(path)
        file_id = data.get("file_id", "")
        for pair in data.get("pairs", []):
            orig = pair["original"].strip()
            corr = pair["corrected"].strip()
            if orig == corr:
                continue
            key = (orig, corr)
            if key not in pattern_counts:
                pattern_counts[key] = []
            if file_id not in pattern_counts[key]:
                pattern_counts[key].append(file_id)

    patterns = [
        CorrectionPattern(
            original=orig,
            corrected=corr,
            frequency=len(files),
            source_files=files,
        )
        for (orig, corr), files in pattern_counts.items()
    ]

    # 빈도순 정렬
    patterns.sort(key=lambda p: p.frequency, reverse=True)
    return patterns


def suggest_corrections(
    text: str,
    patterns: list[CorrectionPattern],
    min_frequency: int = 1,
) -> list[dict[str, str]]:
    """텍스트에서 학습된 패턴에 매칭되는 자동 교정을 제안한다.

    Returns:
        [{"original": "...", "suggested": "...", "frequency": N}, ...]
    """
    suggestions: list[dict[str, str]] = []

    for pat in patterns:
        if pat.frequency < min_frequency:
            continue
        if pat.original in text:
            suggestions.append({
                "original": pat.original,
                "suggested": pat.corrected,
                "frequency": str(pat.frequency),
            })

    return suggestions


def save_patterns(patterns: list[CorrectionPattern], path: Path) -> Path:
    """학습된 패턴을 JSON으로 저장."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [p.to_dict() for p in patterns]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_patterns(path: Path) -> list[CorrectionPattern]:
    """저장된 패턴을 로드."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        CorrectionPattern(
            original=p["original"],
            corrected=p["corrected"],
            frequency=p.get("frequency", 1),
            source_files=p.get("source_files", []),
        )
        for p in data
    ]


# ── F3-3: Vault 연동 ─────────────────────────────────

def route_to_vault(
    md_path: Path,
    config: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> Path | None:
    """최종 MD를 Hahnness vault의 적절한 폴더로 복사한다.

    라우팅 규칙:
    - 기본: vault_log (20 Log/)
    - metadata에 'vault_folder'가 있으면 해당 폴더
    """
    import shutil

    vault_base = config.get("paths", {}).get("vault", "")
    if not vault_base:
        logger.warning("vault_not_configured")
        return None

    vault_base = Path(vault_base)
    if not vault_base.exists():
        logger.warning("vault_dir_not_found", path=str(vault_base))
        return None

    # 대상 폴더 결정
    meta = metadata or {}
    if meta.get("vault_folder"):
        target_dir = vault_base / meta["vault_folder"]
    else:
        vault_log = config.get("paths", {}).get("vault_log", "")
        target_dir = Path(vault_log) if vault_log else vault_base / "20 Log"

    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / md_path.name
    shutil.copy2(str(md_path), str(dest))

    logger.info("vault_routed", source=str(md_path), dest=str(dest))
    return dest
