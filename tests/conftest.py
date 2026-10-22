"""Never import the app with developer/production configuration active."""
import os
import socket
import sys
from unittest.mock import patch

# These values must be set before importing any app module, including at collection.
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['RORI_API_KEYS'] = 'pytest-only-key:101,pytest-other-key:202'
os.environ['JWT_SECRET_KEY'] = 'pytest-only-secret-never-use-in-production'
for name in ('SUPABASE_URL', 'SUPABASE_KEY'):
    os.environ.pop(name, None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Intercept the loader before importing app. Unlike PYTHON_DOTENV_DISABLED,
# this also works with python-dotenv 1.0 and never opens the real .env.
with patch('dotenv.load_dotenv', return_value=False):
    from app.main import app
    from app.models import models
    from app.core import auth
    from app.api import routes


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch, request):
    """Fresh database per test, including commits from request/background sessions."""
    monkeypatch.chdir(tmp_path)
    engine = create_engine(f'sqlite:///{tmp_path / "test.sqlite"}',
                           connect_args={'check_same_thread': False})
    factory = sessionmaker(bind=engine, autoflush=False)
    models.Base.metadata.create_all(engine)
    for name, module in list(sys.modules.items()):
        if name.startswith(('app.', 'scripts.')) and module is not None:
            if hasattr(module, 'SessionLocal'):
                monkeypatch.setattr(module, 'SessionLocal', factory)
            if hasattr(module, 'engine'):
                monkeypatch.setattr(module, 'engine', engine)
    monkeypatch.setattr(auth, '_supabase_client', None)
    monkeypatch.setattr(routes, '_last_analysis_results', None)
    if request.node.get_closest_marker('external') is None:
        def deny_network(*args, **kwargs):
            raise AssertionError('Local tests must not access network services')
        monkeypatch.setattr(socket.socket, 'connect', deny_network)
    yield factory
    engine.dispose()


@pytest.fixture
def db(isolated_runtime):
    with isolated_runtime() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def headers():
    return {'X-API-Key': 'pytest-only-key'}
