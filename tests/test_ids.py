from __future__ import annotations

from cheroki.storage.ids import generate_short_id


def test_id_length_default():
    assert len(generate_short_id()) == 6


def test_id_length_custom():
    assert len(generate_short_id(10)) == 10


def test_id_alphabet():
    # Crockford base32 제외 문자: I, L, O, U (소문자 기준 i, l, o, u)
    forbidden = set("ilou")
    for _ in range(200):
        rec_id = generate_short_id()
        assert not (set(rec_id) & forbidden), f"금지 문자 포함: {rec_id}"
        assert rec_id.islower() or rec_id.isdigit() or all(
            c.isdigit() or c.islower() for c in rec_id
        )


def test_id_randomness():
    ids = {generate_short_id() for _ in range(500)}
    # 6자리 base32는 ~10억 조합. 500개 샘플에서 거의 전부 유니크.
    assert len(ids) >= 495
