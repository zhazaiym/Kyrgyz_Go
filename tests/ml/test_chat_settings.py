"""A mistyped chat setting stops the launch instead of the first client message."""

import pytest

from ML.config import CHAT_SETTINGS, chat_setting, validate_chat_settings


def test_defaults_are_valid():
    validate_chat_settings()


@pytest.mark.parametrize('name', sorted(CHAT_SETTINGS))
@pytest.mark.parametrize('value', ['abc', '', '0', '-5', '12.5', '999999999'])
def test_bad_value_is_refused_at_startup_with_the_setting_name(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        validate_chat_settings()


@pytest.mark.parametrize('name', sorted(CHAT_SETTINGS))
def test_bounds_themselves_are_accepted(monkeypatch, name):
    _, minimum, maximum = CHAT_SETTINGS[name]
    for value in (minimum, maximum):
        monkeypatch.setenv(name, str(value))
        assert chat_setting(name) == value


def test_application_checks_chat_settings_when_it_starts():
    from pathlib import Path

    main = (Path(__file__).resolve().parents[2] / 'main.py').read_text(encoding='utf-8')
    assert 'validate_chat_settings()' in main
