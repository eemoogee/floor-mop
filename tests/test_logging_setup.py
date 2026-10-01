"""Tests for floor_mop.logging_setup."""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from floor_mop.config import LoggingConfig, PathsConfig, Settings
from floor_mop.logging_setup import (
    LOG_FILENAME,
    LOGGER_NAME,
    setup_logging,
    teardown_logging,
)

TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def make_settings(
    tmp_path: Path,
    *,
    level: str = "INFO",
    console: bool = False,
    max_bytes: int = 1_048_576,
    backup_count: int = 2,
    subdir: str = "logs",
) -> Settings:
    """Build a full Settings object with logging.dir under tmp_path."""
    return Settings(
        logging=LoggingConfig(
            level=level,  # type: ignore[arg-type]
            dir=tmp_path / subdir,
            max_bytes=max_bytes,
            backup_count=backup_count,
            console=console,
        ),
        paths=PathsConfig(data_dir=tmp_path / "data"),
    )


def read_lines(path: Path) -> list[str]:
    """Read a log file as UTF-8 and return its physical lines."""
    return path.read_text(encoding="utf-8").splitlines()


@pytest.fixture(autouse=True)
def _isolate_floor_mop_logger() -> Any:
    """Snapshot and restore the floor_mop logger's state around every test."""
    logger = logging.getLogger(LOGGER_NAME)
    teardown_logging()
    pre_handlers = list(logger.handlers)
    pre_level = logger.level
    pre_propagate = logger.propagate

    yield

    teardown_logging()
    logger.handlers = pre_handlers
    logger.setLevel(pre_level)
    logger.propagate = pre_propagate


def test_setup_creates_nested_log_directory_and_file(tmp_path: Path) -> None:
    """setup_logging creates nested, nonexistent directories and the log file."""
    settings = make_settings(tmp_path, subdir="a/b/c")

    setup_logging(settings)

    assert settings.logging.dir.is_dir()
    assert (settings.logging.dir / LOG_FILENAME).is_file()


def test_setup_returns_floor_mop_logger(tmp_path: Path) -> None:
    """setup_logging returns the floor_mop logger."""
    settings = make_settings(tmp_path)

    logger = setup_logging(settings)

    assert logger is logging.getLogger(LOGGER_NAME)


def test_file_lines_are_valid_json_with_required_keys(tmp_path: Path) -> None:
    """Every log line is JSON with ts, level, logger, msg as the first four keys."""
    settings = make_settings(tmp_path)
    logger = setup_logging(settings)

    logger.info("hello")
    for handler in logger.handlers:
        handler.flush()

    lines = read_lines(settings.logging.dir / LOG_FILENAME)
    assert lines
    for line in lines:
        obj = json.loads(line)
        assert list(obj.keys())[:4] == ["ts", "level", "logger", "msg"]


def test_timestamp_is_utc_iso8601_with_milliseconds(tmp_path: Path) -> None:
    """ts matches UTC ISO 8601 with milliseconds and a trailing Z."""
    settings = make_settings(tmp_path)
    logger = setup_logging(settings)

    logger.info("hello")
    for handler in logger.handlers:
        handler.flush()

    lines = read_lines(settings.logging.dir / LOG_FILENAME)
    obj = json.loads(lines[0])
    assert TS_PATTERN.match(obj["ts"])


def test_level_filtering(tmp_path: Path) -> None:
    """An INFO message is dropped when the level is WARNING; WARNING is kept."""
    settings = make_settings(tmp_path, level="WARNING")
    logger = setup_logging(settings)

    logger.info("should not appear")
    logger.warning("should appear")
    for handler in logger.handlers:
        handler.flush()

    msgs = [json.loads(line)["msg"] for line in read_lines(settings.logging.dir / LOG_FILENAME)]
    assert "should not appear" not in msgs
    assert "should appear" in msgs


def test_console_true_writes_to_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """console=True writes log output to sys.stderr."""
    capture = io.StringIO()
    monkeypatch.setattr(sys, "stderr", capture)
    settings = make_settings(tmp_path, console=True)
    logger = setup_logging(settings)

    logger.warning("console message")
    for handler in logger.handlers:
        handler.flush()

    assert "console message" in capture.getvalue()


def test_console_false_writes_nothing_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """console=False produces no stderr output."""
    capture = io.StringIO()
    monkeypatch.setattr(sys, "stderr", capture)
    settings = make_settings(tmp_path, console=False)
    logger = setup_logging(settings)

    logger.warning("console message")
    for handler in logger.handlers:
        handler.flush()

    assert capture.getvalue() == ""


def test_console_timestamps_are_utc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The console handler renders timestamps in UTC."""
    capture = io.StringIO()
    monkeypatch.setattr(sys, "stderr", capture)
    settings = make_settings(tmp_path, console=True)
    logger = setup_logging(settings)

    before = datetime.now(UTC)
    logger.warning("console message")
    for handler in logger.handlers:
        handler.flush()
    after = datetime.now(UTC)

    output = capture.getvalue()
    match = re.search(r"(\d{2}):(\d{2}):(\d{2}),\d{3}", output)
    assert match is not None
    logged_seconds = int(match[1]) * 3600 + int(match[2]) * 60 + int(match[3])
    before_seconds = before.hour * 3600 + before.minute * 60 + before.second
    after_seconds = after.hour * 3600 + after.minute * 60 + after.second
    diff = min(abs(logged_seconds - before_seconds), abs(logged_seconds - after_seconds))
    assert diff <= 2 or diff >= 86398


def test_setup_twice_does_not_duplicate_handlers(tmp_path: Path) -> None:
    """Calling setup_logging twice with identical settings keeps handler count stable."""
    settings = make_settings(tmp_path)

    logger = setup_logging(settings)
    count_after_first = len(logger.handlers)
    logger = setup_logging(settings)
    count_after_second = len(logger.handlers)

    assert count_after_first == count_after_second


def test_setup_twice_produces_one_line_per_record(tmp_path: Path) -> None:
    """After two setup calls, one log call yields exactly one line."""
    settings = make_settings(tmp_path)
    setup_logging(settings)
    logger = setup_logging(settings)

    logger.info("single line")
    for handler in logger.handlers:
        handler.flush()

    lines = read_lines(settings.logging.dir / LOG_FILENAME)
    assert len(lines) == 1


def test_reconfiguration_replaces_previous_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second setup_logging call with new settings fully replaces the first."""
    capture = io.StringIO()
    monkeypatch.setattr(sys, "stderr", capture)
    first_settings = make_settings(tmp_path, level="DEBUG", console=True)
    setup_logging(first_settings)

    second_settings = make_settings(tmp_path, level="WARNING", console=False)
    logger = setup_logging(second_settings)

    capture.truncate(0)
    capture.seek(0)
    logger.info("should be filtered")
    logger.warning("should be kept")
    for handler in logger.handlers:
        handler.flush()

    msgs = [json.loads(line)["msg"] for line in read_lines(second_settings.logging.dir / LOG_FILENAME)]
    assert "should be filtered" not in msgs
    assert "should be kept" in msgs
    assert capture.getvalue() == ""


def test_reconfiguration_to_new_directory_stops_writing_to_old_one(tmp_path: Path) -> None:
    """Switching directories on reconfiguration stops writes to the old file."""
    old_settings = make_settings(tmp_path, subdir="old")
    logger = setup_logging(old_settings)
    logger.info("first")
    for handler in logger.handlers:
        handler.flush()
    old_path = old_settings.logging.dir / LOG_FILENAME
    old_size_before = old_path.stat().st_size

    new_settings = make_settings(tmp_path, subdir="new")
    logger = setup_logging(new_settings)
    logger.info("second")
    for handler in logger.handlers:
        handler.flush()

    new_path = new_settings.logging.dir / LOG_FILENAME
    assert old_path.stat().st_size == old_size_before
    lines = read_lines(new_path)
    assert any(json.loads(line)["msg"] == "second" for line in lines)


def test_exception_record_is_single_line_with_exc_key(tmp_path: Path) -> None:
    """logger.exception produces one line containing an exc key with the type name."""
    settings = make_settings(tmp_path)
    logger = setup_logging(settings)

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("caught it")
    for handler in logger.handlers:
        handler.flush()

    lines = read_lines(settings.logging.dir / LOG_FILENAME)
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert "ValueError" in obj["exc"]


def test_extra_fields_land_under_extra_key(tmp_path: Path) -> None:
    """Extra keyword fields appear under the extra key."""
    settings = make_settings(tmp_path)
    logger = setup_logging(settings)

    logger.info("x", extra={"token": "abc", "n": 1})
    for handler in logger.handlers:
        handler.flush()

    obj = json.loads(read_lines(settings.logging.dir / LOG_FILENAME)[0])
    assert obj["extra"] == {"token": "abc", "n": 1}


def test_record_without_extra_has_no_extra_key(tmp_path: Path) -> None:
    """A plain message has neither extra nor exc keys."""
    settings = make_settings(tmp_path)
    logger = setup_logging(settings)

    logger.info("plain message")
    for handler in logger.handlers:
        handler.flush()

    obj = json.loads(read_lines(settings.logging.dir / LOG_FILENAME)[0])
    assert "extra" not in obj
    assert "exc" not in obj


def test_unserialisable_extra_does_not_raise(tmp_path: Path) -> None:
    """A non-JSON-serialisable extra value does not raise and still parses."""
    settings = make_settings(tmp_path)
    logger = setup_logging(settings)

    logger.info("x", extra={"o": object()})
    for handler in logger.handlers:
        handler.flush()

    lines = read_lines(settings.logging.dir / LOG_FILENAME)
    obj = json.loads(lines[0])
    assert "o" in obj["extra"]


def test_newline_and_unicode_message_stays_on_one_line(tmp_path: Path) -> None:
    """A message with an embedded newline and unicode stays on one physical line."""
    settings = make_settings(tmp_path)
    logger = setup_logging(settings)
    message = "line1\nline2 é 日本"

    logger.info(message)
    for handler in logger.handlers:
        handler.flush()

    lines = read_lines(settings.logging.dir / LOG_FILENAME)
    assert len(lines) == 1
    assert json.loads(lines[0])["msg"] == message


def test_rotation_respects_backup_count_and_size(tmp_path: Path) -> None:
    """Rotation keeps at most backup_count backups, each near the size cap."""
    settings = make_settings(tmp_path, max_bytes=512, backup_count=2)
    logger = setup_logging(settings)

    for n in range(200):
        logger.info("x" * 50 + f" {n}")
    teardown_logging()

    log_dir = settings.logging.dir
    assert (log_dir / LOG_FILENAME).is_file()
    assert (log_dir / f"{LOG_FILENAME}.1").is_file()
    assert (log_dir / f"{LOG_FILENAME}.2").is_file()
    assert not (log_dir / f"{LOG_FILENAME}.3").exists()
    for path in log_dir.glob(f"{LOG_FILENAME}*"):
        assert path.stat().st_size <= 512 * 2


def test_backup_count_zero_keeps_no_backups(tmp_path: Path) -> None:
    """backup_count=0 never creates rotated files."""
    settings = make_settings(tmp_path, max_bytes=512, backup_count=0)
    logger = setup_logging(settings)

    for n in range(200):
        logger.info("x" * 50 + f" {n}")
    teardown_logging()

    log_dir = settings.logging.dir
    assert (log_dir / LOG_FILENAME).is_file()
    assert not (log_dir / f"{LOG_FILENAME}.1").exists()


def test_teardown_removes_installed_handlers(tmp_path: Path) -> None:
    """teardown_logging restores the pre-setup handler count."""
    logger = logging.getLogger(LOGGER_NAME)
    pre_count = len(logger.handlers)
    settings = make_settings(tmp_path)

    setup_logging(settings)
    teardown_logging()

    assert len(logger.handlers) == pre_count


def test_teardown_is_safe_to_call_twice_and_when_unconfigured(tmp_path: Path) -> None:
    """teardown_logging is a no-op when unconfigured and safe to call repeatedly."""
    teardown_logging()

    settings = make_settings(tmp_path)
    setup_logging(settings)
    teardown_logging()
    teardown_logging()


def test_teardown_releases_file_handle(tmp_path: Path) -> None:
    """After teardown, the log directory can be deleted with shutil.rmtree."""
    settings = make_settings(tmp_path)
    logger = setup_logging(settings)
    logger.info("hello")
    teardown_logging()

    shutil.rmtree(settings.logging.dir)
    assert not settings.logging.dir.exists()


def test_unmarked_handler_survives_setup_and_teardown(tmp_path: Path) -> None:
    """A handler not installed by this module survives setup_logging and teardown."""
    logger = logging.getLogger(LOGGER_NAME)
    foreign_handler = logging.NullHandler()
    logger.addHandler(foreign_handler)

    try:
        settings = make_settings(tmp_path)
        setup_logging(settings)
        setup_logging(settings)
        assert foreign_handler in logger.handlers

        teardown_logging()
        assert foreign_handler in logger.handlers
    finally:
        logger.removeHandler(foreign_handler)


def test_root_logger_handlers_unchanged(tmp_path: Path) -> None:
    """The root logger's handler list is unaffected by setup_logging/teardown_logging."""
    root = logging.getLogger()
    before = list(root.handlers)

    settings = make_settings(tmp_path)
    setup_logging(settings)
    teardown_logging()

    assert root.handlers == before


def test_propagate_flag_unchanged(tmp_path: Path) -> None:
    """setup_logging does not alter the logger's propagate flag."""
    logger = logging.getLogger(LOGGER_NAME)
    before = logger.propagate

    settings = make_settings(tmp_path)
    setup_logging(settings)

    assert logger.propagate == before


def test_oserror_propagates_when_log_dir_cannot_be_created(tmp_path: Path) -> None:
    """An OSError from directory creation propagates without installing handlers."""
    blocking_file = tmp_path / "not_a_dir"
    blocking_file.write_text("x", encoding="utf-8")
    logger = logging.getLogger(LOGGER_NAME)
    pre_count = len(logger.handlers)

    settings = Settings(
        logging=LoggingConfig(
            level="INFO",
            dir=blocking_file / "sub",
            max_bytes=1_048_576,
            backup_count=2,
            console=False,
        ),
        paths=PathsConfig(data_dir=tmp_path / "data"),
    )

    with pytest.raises(OSError):
        setup_logging(settings)

    assert len(logger.handlers) == pre_count


def test_import_has_no_side_effects(tmp_path: Path) -> None:
    """Importing floor_mop.logging_setup creates no files and installs no handlers."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    code = (
        "import json, logging, os\n"
        "import floor_mop.logging_setup\n"
        "print(json.dumps({\n"
        "    'entries': os.listdir('.'),\n"
        "    'handlers': len(logging.getLogger('floor_mop').handlers),\n"
        "}))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=empty_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["entries"] == []
    assert payload["handlers"] == 0
