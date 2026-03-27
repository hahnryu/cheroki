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
