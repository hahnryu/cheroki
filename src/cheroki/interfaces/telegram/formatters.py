"""Telegram 메시지 포맷팅 헬퍼."""
from __future__ import annotations

from cheroki.core.result import TranscriptionResult


def fmt_hms(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}시간 {m}분 {s}초"
    if m > 0:
        return f"{m}분 {s}초"
    return f"{s}초"


def welcome_message() -> str:
    return (
        "안녕하세요. 저는 cheroki입니다.\n"
        "오디오/비디오 파일을 보내주시면 한국어 녹취 + 화자분리 + SRT/MD/TXT를 돌려드립니다.\n\n"
        "명령어는 /help 로 확인하세요."
    )


def help_message() -> str:
    return (
        "사용법:\n"
        "· 오디오/비디오 파일 전송 → 자동 녹취 (캡션은 제목으로 저장됨)\n"
        "· /last - 최근 녹취 5건\n"
        "· /get <id> - 특정 건 파일 재전송\n"
        "· /status <id> - 처리 상태 조회\n"
        "· /help - 이 도움말"
    )


def not_allowed_message() -> str:
    return "죄송합니다. 이 봇은 초대받은 사용자만 사용할 수 있습니다."


def received_message(
    record_id: str,
    file_name: str | None,
    size_bytes: int | None,
    duration_sec: int | None = None,
    storage_rel_path: str | None = None,
) -> str:
    meta_parts: list[str] = []
    if file_name:
        meta_parts.append(file_name)
    if size_bytes:
        meta_parts.append(f"{size_bytes / 1e6:.1f} MB")
    if duration_sec:
        meta_parts.append(f"약 {fmt_hms(duration_sec)}")
    meta_line = f"파일: {' · '.join(meta_parts)}" if meta_parts else ""
    storage_line = f"저장: {storage_rel_path}" if storage_rel_path else ""

    lines = [f"[ 받음 ]  ID: {record_id}"]
    if meta_line:
        lines.append(meta_line)
    if storage_line:
        lines.append(storage_line)
    lines.append("Scribe v2로 전사 시작합니다.")
    return "\n".join(lines)


def status_downloading(elapsed_sec: float | None = None) -> str:
    if elapsed_sec is None:
        return "[ 다운로드 ] 시작"
    return f"[ 다운로드 ] {int(elapsed_sec)}초 경과"


def status_downloaded(elapsed_sec: float) -> str:
    return f"[ 다운로드 ] 완료 ({int(elapsed_sec)}초)"


def status_transcribing(elapsed_sec: float | None = None) -> str:
    if elapsed_sec is None:
        return "[ 전사 ] Scribe v2 호출 중"
    return f"[ 전사 ] {int(elapsed_sec)}초 경과"


def status_transcribed(elapsed_sec: float, result: TranscriptionResult) -> str:
    return (
        f"[ 전사 ] 완료 ({int(elapsed_sec)}초) · "
        f"{fmt_hms(result.duration_sec)} · 화자 {result.speaker_count}명 · "
        f"발화 {len(result.utterances)}개"
    )


def status_exporting() -> str:
    return "[ 저장 ] SRT / MD / TXT 생성 중"


def status_sending() -> str:
    return "[ 전송 ] 파일 보내는 중"


def status_all_done() -> str:
    return "[ 완료 ]"


def completed_message(record_id: str, result: TranscriptionResult, caption: str | None = None) -> str:
    duration = fmt_hms(result.duration_sec)
    preview_lines = []
    for u in result.utterances[:4]:
        mm = int(u.start // 60)
        ss = int(u.start % 60)
        text = u.text if len(u.text) <= 80 else u.text[:77] + "..."
        preview_lines.append(f"[S{u.speaker} {mm:02d}:{ss:02d}] {text}")
    preview = "\n".join(preview_lines)

    title_line = f"\n제목: {caption}" if caption else ""
    return (
        f"완료. ID: {record_id}{title_line}\n"
        f"길이: {duration} · 화자 {result.speaker_count}명\n\n"
        f"미리보기:\n{preview}"
    )


def failed_message(record_id: str, error: str) -> str:
    return f"녹취 실패. ID: {record_id}\n사유: {error}"


def status_message(record: dict) -> str:
    status = record.get("status")
    rec_id = record.get("id")
    if status == "completed":
        dur = fmt_hms(record.get("duration_sec") or 0.0)
        spk = record.get("speaker_count") or 0
        return f"ID {rec_id} · 완료 · {dur} · 화자 {spk}명"
    if status == "failed":
        return f"ID {rec_id} · 실패 · {record.get('error') or '(사유 미상)'}"
    if status == "processing":
        return f"ID {rec_id} · 처리 중"
    return f"ID {rec_id} · 대기 중"


def list_recent_message(records: list[dict]) -> str:
    if not records:
        return "아직 녹취 기록이 없습니다."
    lines = ["최근 녹취 기록:"]
    for r in records:
        rec_id = r.get("id")
        status = r.get("status") or "?"
        title = r.get("session_title") or r.get("file_name") or "(제목 없음)"
        created = (r.get("created_at") or "")[:10]
        if len(title) > 40:
            title = title[:37] + "..."
        lines.append(f"· {rec_id} · {status} · {created} · {title}")
    return "\n".join(lines)


def record_not_found_message(record_id: str) -> str:
    return f"ID {record_id}를 찾을 수 없습니다."


def record_not_completed_message(record_id: str, status: str) -> str:
    return f"ID {record_id}는 아직 {status} 상태입니다. 완료 후 다시 시도하세요."
