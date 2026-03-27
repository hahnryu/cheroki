"""CLI 인터페이스."""

from __future__ import annotations

from pathlib import Path

import click
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
)


@click.group()
@click.version_option(package_name="cheroki")
def main() -> None:
    """Cheroki — 음성 전사 파이프라인."""


@main.command()
@click.argument("audio_path", type=click.Path(exists=True, path_type=Path))
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
def transcribe(audio_path: Path, config_path: Path | None) -> None:
    """음성 파일을 전사한다."""
    from cheroki.pipeline import run_pipeline

    result = run_pipeline(audio_path, config_path=config_path)
    click.echo(f"\n전사 완료: {result['file_id']}")
    click.echo(f"전사 결과: {result['transcript_path']}")
    click.echo(f"세그먼트 수: {len(result['result'].segments)}")
    click.echo(f"전체 텍스트 (앞 200자): {result['result'].full_text[:200]}")


@main.command()
def info() -> None:
    """현재 설정 정보를 출력한다."""
    from cheroki.config import get_config

    config = get_config()
    click.echo("=== Cheroki 설정 ===")
    click.echo(f"Whisper 모델: {config['whisper']['model']}")
    click.echo(f"디바이스: {config['whisper']['device']}")
    click.echo(f"언어: {config['whisper']['language']}")
    click.echo("\n경로:")
    for key, value in config["paths"].items():
        click.echo(f"  {key}: {value}")


@main.command()
@click.argument("file_id")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
def review(file_id: str, config_path: Path | None) -> None:
    """전사 결과를 검토하고 의심 구간 질문 목록을 생성한다."""
    import json
    from cheroki.config import get_config
    from cheroki.transcript_store import load_transcript
    from cheroki.dictionary import Dictionary
    from cheroki.reviewer import extract_suspicious, generate_questions

    config = get_config(config_path)
    transcripts_dir = Path(config["paths"]["transcripts"])

    # 전사 결과 찾기
    transcript_path = transcripts_dir / f"{file_id}.transcript.json"
    if not transcript_path.exists():
        click.echo(f"전사 결과를 찾을 수 없습니다: {file_id}", err=True)
        raise SystemExit(1)

    result = load_transcript(transcript_path)
    dictionary = Dictionary.from_config(config)
    min_conf = config.get("transcription", {}).get("min_confidence", 0.7)

    suspicious = extract_suspicious(result, dictionary=dictionary, min_confidence=min_conf)
    questions = generate_questions(result, suspicious)

    if not questions:
        click.echo("의심 구간이 없습니다. 전사 품질이 양호합니다.")
        return

    click.echo(f"=== 의심 구간 {len(questions)}개 ===\n")
    for i, q in enumerate(questions, 1):
        click.echo(f"[{i}] {q.timestamp}")
        click.echo(f"    현재: {q.current_text}")
        if q.context_before:
            click.echo(f"    앞: ...{q.context_before}")
        if q.context_after:
            click.echo(f"    뒤: {q.context_after}...")
        click.echo(f"    사유: {', '.join(q.reasons)}")
        click.echo()

    # 질문 목록 JSON 저장
    questions_path = transcripts_dir / f"{file_id}.questions.json"
    questions_path.write_text(
        json.dumps([q.to_dict() for q in questions], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    click.echo(f"질문 목록 저장: {questions_path}")


@main.command()
@click.argument("file_id")
@click.argument("corrections_file", type=click.Path(exists=True, path_type=Path))
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
def correct(file_id: str, corrections_file: Path, config_path: Path | None) -> None:
    """교정 파일을 적용하여 최종본을 생성한다.

    CORRECTIONS_FILE은 JSON 배열: [{"segment_index": 0, "corrected_text": "교정된 텍스트"}, ...]
    """
    import json
    from cheroki.config import get_config
    from cheroki.transcript_store import load_transcript, save_transcript
    from cheroki.corrector import Correction, CorrectionSet, apply_corrections, save_corrections
    from cheroki.corpus import save_corpus_pairs

    config = get_config(config_path)
    transcripts_dir = Path(config["paths"]["transcripts"])
    corrections_dir = Path(config["paths"]["corrections"])
    corpus_dir = Path(config["paths"]["corpus"])

    # 전사 결과 로드
    transcript_path = transcripts_dir / f"{file_id}.transcript.json"
    if not transcript_path.exists():
        click.echo(f"전사 결과를 찾을 수 없습니다: {file_id}", err=True)
        raise SystemExit(1)

    result = load_transcript(transcript_path)

    # 교정 데이터 파싱
    raw = json.loads(corrections_file.read_text(encoding="utf-8"))
    corrections = []
    for item in raw:
        idx = item["segment_index"]
        original = result.segments[idx].text.strip() if idx < len(result.segments) else ""
        corrections.append(Correction(
            segment_index=idx,
            original_text=original,
            corrected_text=item["corrected_text"],
        ))

    # 교정 적용
    corrected = apply_corrections(result, corrections)

    # 최종본 저장
    final_path = save_transcript(corrected, transcripts_dir, f"{file_id}_final")
    click.echo(f"최종본 저장: {final_path}")

    # 교정 이력 저장
    cs = CorrectionSet(file_id=file_id, corrections=corrections)
    corr_path = save_corrections(cs, corrections_dir)
    click.echo(f"교정 이력 저장: {corr_path}")

    # 코퍼스 누적
    corpus_path = save_corpus_pairs(file_id, corrections, corpus_dir, source_file=result.source_file)
    click.echo(f"코퍼스 저장: {corpus_path}")

    click.echo(f"\n교정 완료: {len(corrections)}개 세그먼트 수정")


@main.command()
@click.argument("watch_dir", type=click.Path(path_type=Path), default=None, required=False)
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None)
def watch(watch_dir: Path | None, config_path: Path | None) -> None:
    """폴더를 감시하여 새 음성 파일을 자동 전사한다."""
    import time
    from cheroki.config import get_config
    from cheroki.pipeline import run_pipeline
    from cheroki.watcher import watch_folder

    config = get_config(config_path)
    target = watch_dir or Path(config["paths"]["originals"])

    def on_new_file(path: Path) -> None:
        try:
            run_pipeline(path, config=config)
        except Exception as e:
            click.echo(f"전사 실패: {path.name} — {e}", err=True)

    click.echo(f"감시 시작: {target}")
    click.echo("Ctrl+C로 종료")
    observer = watch_folder(target, on_new_file)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
        click.echo("\n감시 종료.")


if __name__ == "__main__":
    main()
