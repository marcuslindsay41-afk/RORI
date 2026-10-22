import os
import pytest

from tests.integration_config import supabase_config

NAMES = ('URL', 'KEY', 'EMAIL', 'PASSWORD', 'RESTAURANT_ID')


@pytest.fixture
def empty_supabase_config(monkeypatch):
    for name in (*NAMES, 'ALLOW'):
        monkeypatch.delenv(f'RORI_TEST_SUPABASE_{name}', raising=False)


def test_external_disabled_skips(empty_supabase_config):
    with pytest.raises(pytest.skip.Exception, match='disabled'):
        supabase_config()


@pytest.mark.parametrize('missing', NAMES)
def test_external_enabled_missing_setting_fails(empty_supabase_config, monkeypatch, missing):
    monkeypatch.setenv('RORI_TEST_SUPABASE_ALLOW', '1')
    for name in NAMES:
        monkeypatch.setenv(f'RORI_TEST_SUPABASE_{name}', '101' if name == 'RESTAURANT_ID' else 'dummy-test-value')
    monkeypatch.delenv(f'RORI_TEST_SUPABASE_{missing}')
    with pytest.raises(pytest.fail.Exception) as error:
        supabase_config()
    assert f'RORI_TEST_SUPABASE_{missing}' in str(error.value)
    assert 'dummy-test-value' not in str(error.value)


@pytest.mark.parametrize('value', ['', ' ', 'not-an-integer', '0', '-1'])
def test_external_enabled_invalid_id_fails(empty_supabase_config, monkeypatch, value):
    monkeypatch.setenv('RORI_TEST_SUPABASE_ALLOW', '1')
    for name in NAMES:
        monkeypatch.setenv(f'RORI_TEST_SUPABASE_{name}', 'dummy-test-value')
    monkeypatch.setenv('RORI_TEST_SUPABASE_RESTAURANT_ID', value)
    with pytest.raises(pytest.fail.Exception, match='RESTAURANT_ID'):
        supabase_config()


def test_dotenv_loader_was_intercepted():
    import app
    from unittest.mock import Mock
    # The real loader is never invoked, regardless of dotenv version.
    assert isinstance(app.load_dotenv, Mock)
    assert app.load_dotenv.return_value is False
    assert os.environ['DATABASE_URL'] == 'sqlite://'
    assert 'SUPABASE_URL' not in os.environ
    assert 'SUPABASE_KEY' not in os.environ
