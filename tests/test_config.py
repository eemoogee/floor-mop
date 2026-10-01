"""Tests for floor_mop.config."""

from __future__ import annotations

import traceback
from pathlib import Path

import pytest

from floor_mop.config import ConfigError, load_settings

SECRET = "hunter2-secret-value"

DEFAULT_TOML = """\
[logging]
level = "INFO"
dir = "logs"
max_bytes = 10485760
backup_count = 5
console = true

[paths]
data_dir = "data"
"""


def _make_config_dir(
    tmp_path: Path,
    default_content: str = DEFAULT_TOML,
    local_content: str | None = None,
) -> Path:
    """Create a config directory under tmp_path with the given TOML contents."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "default.toml").write_text(default_content, encoding="utf-8")
    if local_content is not None:
        (config_dir / "local.toml").write_text(local_content, encoding="utf-8")
    return config_dir


def test_defaults_load(tmp_path: Path) -> None:
    """Values from default.toml alone load correctly."""
    config_dir = _make_config_dir(tmp_path)

    settings = load_settings(config_dir=config_dir, env={})

    assert settings.logging.level == "INFO"
    assert settings.logging.dir == Path("logs")
    assert settings.paths.data_dir == Path("data")


def test_local_overrides_default(tmp_path: Path) -> None:
    """local.toml overrides a value set in default.toml."""
    config_dir = _make_config_dir(
        tmp_path, local_content='[logging]\nlevel = "DEBUG"\n'
    )

    settings = load_settings(config_dir=config_dir, env={})

    assert settings.logging.level == "DEBUG"


def test_local_override_is_deep_merge(tmp_path: Path) -> None:
    """local.toml that sets only logging.level leaves logging.dir at its default."""
    config_dir = _make_config_dir(
        tmp_path, local_content='[logging]\nlevel = "DEBUG"\n'
    )

    settings = load_settings(config_dir=config_dir, env={})

    assert settings.logging.level == "DEBUG"
    assert settings.logging.dir == Path("logs")


def test_env_overrides_local(tmp_path: Path) -> None:
    """An env var beats a value set in local.toml."""
    config_dir = _make_config_dir(
        tmp_path, local_content='[logging]\nlevel = "DEBUG"\n'
    )

    settings = load_settings(
        config_dir=config_dir, env={"FLOOR_MOP__LOGGING__LEVEL": "ERROR"}
    )

    assert settings.logging.level == "ERROR"


def test_env_nested_key_path(tmp_path: Path) -> None:
    """FLOOR_MOP__LOGGING__LEVEL=DEBUG sets logging.level."""
    config_dir = _make_config_dir(tmp_path)

    settings = load_settings(
        config_dir=config_dir, env={"FLOOR_MOP__LOGGING__LEVEL": "DEBUG"}
    )

    assert settings.logging.level == "DEBUG"


def test_config_dir_env_var_honored(tmp_path: Path) -> None:
    """FLOOR_MOP_CONFIG_DIR selects the directory and is not treated as an override."""
    config_dir = _make_config_dir(tmp_path)

    settings = load_settings(
        config_dir=None, env={"FLOOR_MOP_CONFIG_DIR": str(config_dir)}
    )

    assert settings.logging.level == "INFO"
    assert settings.paths.data_dir == Path("data")


def test_config_dir_argument_beats_env_var(tmp_path: Path) -> None:
    """The config_dir argument wins over FLOOR_MOP_CONFIG_DIR."""
    real_dir = _make_config_dir(tmp_path / "real")
    decoy_dir = _make_config_dir(
        tmp_path / "decoy", local_content='[logging]\nlevel = "DEBUG"\n'
    )
    (real_dir / "local.toml").write_text('[logging]\nlevel = "WARNING"\n')

    settings = load_settings(
        config_dir=real_dir, env={"FLOOR_MOP_CONFIG_DIR": str(decoy_dir)}
    )

    assert settings.logging.level == "WARNING"


def test_unknown_toml_key_raises(tmp_path: Path) -> None:
    """An unknown key in default.toml raises ConfigError."""
    config_dir = _make_config_dir(
        tmp_path,
        default_content=DEFAULT_TOML + '\n[logging]\nnope = "x"\n',
    )

    with pytest.raises(ConfigError):
        load_settings(config_dir=config_dir, env={})


def test_unknown_env_key_raises(tmp_path: Path) -> None:
    """FLOOR_MOP__LOGGING__NOPE raises ConfigError."""
    config_dir = _make_config_dir(tmp_path)

    with pytest.raises(ConfigError):
        load_settings(
            config_dir=config_dir, env={"FLOOR_MOP__LOGGING__NOPE": "x"}
        )


def test_invalid_literal_raises(tmp_path: Path) -> None:
    """A bad logging.level value raises ConfigError."""
    config_dir = _make_config_dir(tmp_path)

    with pytest.raises(ConfigError):
        load_settings(
            config_dir=config_dir, env={"FLOOR_MOP__LOGGING__LEVEL": "NOT_A_LEVEL"}
        )


def test_missing_default_toml_raises(tmp_path: Path) -> None:
    """A missing default.toml raises ConfigError naming the missing path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    expected_path = config_dir / "default.toml"

    with pytest.raises(ConfigError) as exc_info:
        load_settings(config_dir=config_dir, env={})

    assert str(expected_path) in str(exc_info.value)


def test_malformed_toml_raises(tmp_path: Path) -> None:
    """Malformed TOML raises ConfigError naming the offending file."""
    config_dir = _make_config_dir(tmp_path, default_content="not = [valid toml")
    expected_path = config_dir / "default.toml"

    with pytest.raises(ConfigError) as exc_info:
        load_settings(config_dir=config_dir, env={})

    assert str(expected_path) in str(exc_info.value)


def test_settings_are_frozen(tmp_path: Path) -> None:
    """Assigning to a field of the returned Settings raises an exception."""
    config_dir = _make_config_dir(tmp_path)
    settings = load_settings(config_dir=config_dir, env={})

    with pytest.raises(Exception):  # noqa: B017
        settings.logging.level = "DEBUG"  # type: ignore[misc]


def test_real_default_toml_loads() -> None:
    """The repo's real config/default.toml loads successfully."""
    repo_root = Path(__file__).resolve().parents[1]
    settings = load_settings(config_dir=repo_root / "config", env={})

    assert settings.logging.level in {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }


def test_secret_not_in_error_message(tmp_path: Path) -> None:
    """A secret value supplied via env does not appear in str(ConfigError)."""
    config_dir = _make_config_dir(tmp_path)

    with pytest.raises(ConfigError) as exc_info:
        load_settings(config_dir=config_dir, env={"FLOOR_MOP__LOGGING__LEVEL": SECRET})

    assert SECRET not in str(exc_info.value)


def test_secret_not_in_full_traceback(tmp_path: Path) -> None:
    """A secret value supplied via env does not leak into the formatted traceback."""
    config_dir = _make_config_dir(tmp_path)

    exc: ConfigError | None = None
    try:
        load_settings(config_dir=config_dir, env={"FLOOR_MOP__LOGGING__LEVEL": SECRET})
    except ConfigError as caught:
        exc = caught

    assert exc is not None
    full_traceback = "".join(traceback.format_exception(exc))

    assert SECRET not in full_traceback
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True


def test_malformed_toml_has_no_chained_cause(tmp_path: Path) -> None:
    """Malformed TOML errors do not chain the original exception into the traceback."""
    config_dir = _make_config_dir(tmp_path, default_content="not = [valid toml")

    exc: ConfigError | None = None
    try:
        load_settings(config_dir=config_dir, env={})
    except ConfigError as caught:
        exc = caught

    assert exc is not None
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True

    full_traceback = "".join(traceback.format_exception(exc))
    assert "During handling of the above exception" not in full_traceback
    assert "direct cause" not in full_traceback


def test_secret_not_in_traceback_via_toml_value(tmp_path: Path) -> None:
    """A secret value supplied via TOML does not leak into the error or traceback."""
    config_dir = _make_config_dir(
        tmp_path,
        default_content=(
            f'[logging]\nlevel = "{SECRET}"\ndir = "logs"\n'
            "max_bytes = 10485760\nbackup_count = 5\nconsole = true\n\n"
            '[paths]\ndata_dir = "data"\n'
        ),
    )

    exc: ConfigError | None = None
    try:
        load_settings(config_dir=config_dir, env={})
    except ConfigError as caught:
        exc = caught

    assert exc is not None
    assert SECRET not in str(exc)

    full_traceback = "".join(traceback.format_exception(exc))
    assert SECRET not in full_traceback


def test_logging_rotation_defaults_load(tmp_path: Path) -> None:
    """max_bytes, backup_count and console load with the helper's default values."""
    config_dir = _make_config_dir(tmp_path)

    settings = load_settings(config_dir=config_dir, env={})

    assert settings.logging.max_bytes == 10485760
    assert settings.logging.backup_count == 5
    assert settings.logging.console is True


def test_logging_new_fields_overridable_by_local_toml(tmp_path: Path) -> None:
    """local.toml overrides max_bytes, backup_count and console."""
    config_dir = _make_config_dir(
        tmp_path,
        local_content="[logging]\nmax_bytes = 2048\nbackup_count = 0\nconsole = false\n",
    )

    settings = load_settings(config_dir=config_dir, env={})

    assert settings.logging.max_bytes == 2048
    assert settings.logging.backup_count == 0
    assert settings.logging.console is False


def test_logging_new_fields_overridable_by_env(tmp_path: Path) -> None:
    """Env vars override max_bytes, backup_count and console with lax coercion."""
    config_dir = _make_config_dir(tmp_path)

    settings = load_settings(
        config_dir=config_dir,
        env={
            "FLOOR_MOP__LOGGING__MAX_BYTES": "2048",
            "FLOOR_MOP__LOGGING__BACKUP_COUNT": "0",
            "FLOOR_MOP__LOGGING__CONSOLE": "false",
        },
    )

    assert settings.logging.max_bytes == 2048
    assert settings.logging.backup_count == 0
    assert settings.logging.console is False


def test_max_bytes_must_be_positive(tmp_path: Path) -> None:
    """max_bytes = 0 raises ConfigError mentioning logging.max_bytes."""
    config_dir = _make_config_dir(
        tmp_path, local_content="[logging]\nmax_bytes = 0\n"
    )

    with pytest.raises(ConfigError) as exc_info:
        load_settings(config_dir=config_dir, env={})

    assert "logging.max_bytes" in str(exc_info.value)


def test_backup_count_cannot_be_negative(tmp_path: Path) -> None:
    """backup_count = -1 raises ConfigError mentioning logging.backup_count."""
    config_dir = _make_config_dir(
        tmp_path, local_content="[logging]\nbackup_count = -1\n"
    )

    with pytest.raises(ConfigError) as exc_info:
        load_settings(config_dir=config_dir, env={})

    assert "logging.backup_count" in str(exc_info.value)


def test_console_rejects_non_boolean(tmp_path: Path) -> None:
    """A non-boolean console value raises ConfigError without leaking the value."""
    config_dir = _make_config_dir(tmp_path)

    with pytest.raises(ConfigError) as exc_info:
        load_settings(
            config_dir=config_dir,
            env={"FLOOR_MOP__LOGGING__CONSOLE": "not-a-bool"},
        )

    assert "not-a-bool" not in str(exc_info.value)
