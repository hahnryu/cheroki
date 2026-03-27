"""dictionary 모듈 테스트."""

import tempfile
from pathlib import Path

import yaml

from cheroki.dictionary import Dictionary


def _write_dict_file(tmp: Path, name: str, data: dict) -> Path:
    path = tmp / name
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_load_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_dict_file(tmp, "test.yaml", {
            "people": ["류한석", "김철수"],
            "places": ["서울"],
        })
        d = Dictionary()
        d.load_file(tmp / "test.yaml")

        assert d.contains("류한석")
        assert d.contains("김철수")
        assert d.contains("서울")
        assert not d.contains("뉴욕")


def test_load_directory():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_dict_file(tmp, "people.yaml", {"people": ["류한석"]})
        _write_dict_file(tmp, "places.yaml", {"places": ["서울", "부산"]})

        d = Dictionary()
        d.load_directory(tmp)

        assert d.contains("류한석")
        assert d.contains("부산")
        assert len(d.all_words) == 3


def test_categories():
    d = Dictionary()
    d.add("류한석", "people")
    d.add("서울", "places")

    assert "people" in d.categories
    assert "places" in d.categories


def test_get_category():
    d = Dictionary()
    d.add("류한석", "people")
    d.add("Cheroki", "products")

    assert d.get_category("류한석") == "people"
    assert d.get_category("cheroki") == "products"  # 대소문자 무시
    assert d.get_category("없는단어") is None


def test_case_insensitive():
    d = Dictionary()
    d.add("Cheroki", "products")

    assert d.contains("cheroki")
    assert d.contains("CHEROKI")
    assert d.contains("Cheroki")


def test_add_and_save():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        d = Dictionary()
        d.add("새단어", "terms")
        d.add("류한석", "people")

        save_path = tmp / "saved.yaml"
        d.save_file(save_path)

        d2 = Dictionary()
        d2.load_file(save_path)
        assert d2.contains("새단어")
        assert d2.contains("류한석")


def test_empty_directory():
    with tempfile.TemporaryDirectory() as tmp:
        d = Dictionary()
        d.load_directory(Path(tmp))
        assert len(d.all_words) == 0


def test_from_config():
    d = Dictionary.from_config({})
    # default.yaml에서 로드되어야 함
    assert d.contains("류한석")
    assert d.contains("Cheroki")
