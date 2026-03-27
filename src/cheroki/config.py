"""설정 관리 모듈."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """config.yaml을 로드하고 경로를 확장한다."""
    config_path = path or _DEFAULT_CONFIG_PATH
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # ~ 확장
    for key, value in config.get("paths", {}).items():
        if isinstance(value, str) and value:
            config["paths"][key] = str(Path(value).expanduser())

    return config


def ensure_directories(config: dict[str, Any]) -> None:
    """데이터 디렉토리가 없으면 생성한다."""
    data_keys = ["originals", "transcripts", "corrections", "corpus", "exports"]
    for key in data_keys:
        path = config["paths"].get(key)
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)


def get_config(path: Path | None = None) -> dict[str, Any]:
    """설정 로드 + 디렉토리 생성을 한 번에."""
    config = load_config(path)
    ensure_directories(config)
    return config
