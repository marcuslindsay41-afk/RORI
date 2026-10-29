"""Unconditional legacy containment, using isolated data and synthetic identities."""
from unittest.mock import Mock

import pytest
from starlette.background import BackgroundTasks

from app.api import routes, analysis, pos, inventory, labor, sync
from app.core import auth, logger
from app.models import models
from app.rules import engine as rules
from app.services import analysis_service as service
from tests.test_api import CASES

CODE = 'OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE'
PATHS = [('POST', '/run-analysis'), ('GET', '/recommendations'),
         ('POST', '/run-analysis/202'), ('POST', '/analysis/run-analysis/202')]


@pytest.fixture
def forbidden_effects(monkeypatch):
    effects = []
    def forbid(*args, **kwargs):
        effects.append('called')
        raise AssertionError('Forbidden operational side effect')
    # Instrument remaining imports as well as the defining modules. Future route
    # aliases cannot accidentally hide a DB, rule, logging or scheduling call.
    for module in (routes, analysis, service, pos, inventory, labor, sync, models, rules, logger):
        for name in ('SessionLocal', 'run_analysis', 'run_full_analysis', 'run_all_rules',
                     'get_latest_recommendations', 'run_background_analysis', 'log_analysis_run'):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, forbid)
    monkeypatch.setattr(BackgroundTasks, 'add_task', forbid)
    # A cache sentinel detects even iteration/access, rather than only inspecting
    # the HTTP result after an unsafe cache lookup.
    class CacheTrap:
        def __getattribute__(self, name):
            # pytest 8's monkeypatch checks the value's class during setup.
            # Permit that reflection; any cache-content access still fails.
            if name == '__class__':
                return object.__getattribute__(self, name)
            forbid()
    monkeypatch.setattr(routes, '_last_analysis_results', CacheTrap())
    return effects


@pytest.mark.parametrize('method,path', PATHS)
@pytest.mark.parametrize('identity', ['anonymous', 'tenant_101_key', 'tenant_202_key', 'jwt', 'invalid'])
def test_http_denial_precedes_all_operational_effects(client, monkeypatch, method, path, identity, forbidden_effects):
    headers = {}
    if identity == 'tenant_101_key': headers = {'X-API-Key': 'pytest-only-key'}
    elif identity == 'tenant_202_key': headers = {'X-API-Key': 'pytest-other-key'}
    elif identity == 'jwt':
        token = auth.create_access_token({'user_id': 'test-user', 'restaurant_id': 101})
        headers = {'Authorization': 'Bearer '+token}
    elif identity == 'invalid': headers = {'Authorization': 'Bearer invalid', 'X-API-Key': 'invalid'}
    response = client.request(method, path, headers=headers,
        params={'restaurant_id': 101, 'decision_eligible': 'true', 'profile': 'synthetic_test_approved'})
    assert response.status_code == 503
    assert response.json() == {'detail': CODE}
    assert forbidden_effects == []


@pytest.mark.parametrize('method,path', PATHS)
def test_missing_configuration_and_hostile_cache_cannot_enable_http(client, monkeypatch, forbidden_effects, method, path):
    for name in ('DATABASE_URL', 'RORI_API_KEYS', 'JWT_SECRET_KEY', 'SUPABASE_URL', 'SUPABASE_KEY'):
        monkeypatch.delenv(name, raising=False)
    response = client.request(method, path)
    assert response.status_code == 503 and response.json() == {'detail': CODE}
    assert forbidden_effects == []


@pytest.mark.parametrize('name', ['run_analysis', 'run_full_analysis', 'get_latest_recommendations', 'run_background_analysis', 'run_all_rules'])
def test_internal_entrypoints_deny_before_side_effects(monkeypatch, name, tmp_path):
    # Capture the actual entry point before poisoning its potential dependencies.
    entry = getattr(rules if name == 'run_all_rules' else service, name)
    calls = Mock(side_effect=AssertionError('Forbidden operational dependency'))
    for module in (service, rules, logger, models):
        for dep in ('SessionLocal', 'run_all_rules', 'check_waste', 'low_performing_items',
                    'labor_efficiency', 'log_analysis_run', 'run_full_analysis'):
            if hasattr(module, dep): monkeypatch.setattr(module, dep, calls)
    import threading
    monkeypatch.setattr(threading, 'Thread', calls)
    from app.core.recommendation_containment import OperationalRecommendationsUnavailable
    with pytest.raises(OperationalRecommendationsUnavailable) as error:
        if name == 'run_all_rules': entry(calls, 202)
        else: entry(202)
    assert str(error.value) == CODE
    calls.assert_not_called()
    assert not list(tmp_path.glob('logs/analysis_*.json'))


@pytest.mark.parametrize('endpoint', ['pos', 'inventory', 'labor', 'sync'])
@pytest.mark.parametrize('invalid', [False, True])
def test_ingestion_never_schedules_recommendations(client, headers, db, monkeypatch, endpoint, invalid):
    schedule = Mock(side_effect=AssertionError('Unexpected background scheduling'))
    monkeypatch.setattr(BackgroundTasks, 'add_task', schedule)
    for module in (service, pos, inventory, labor, sync):
        for name in ('run_full_analysis', 'run_background_analysis'):
            if hasattr(module, name): monkeypatch.setattr(module, name, schedule)
    if endpoint == 'sync':
        payload = {key: [item] for _, key, item, _, _ in CASES}
    else:
        _, key, item, _, _ = next(c for c in CASES if c[0] == endpoint)
        payload = {key: [item]}
    response = client.post('/data/'+endpoint, headers={'X-API-Key': 'invalid'} if invalid else headers, json=payload)
    assert response.status_code == (401 if invalid else 200)
    schedule.assert_not_called()
    if not invalid:
        for _, key, _, model, _ in CASES:
            if key in payload:
                row = db.query(model).one()
                assert row.restaurant_id == 101


@pytest.mark.parametrize('endpoint,key,item,model,count_key', CASES + [
    ('sync', 'sales', CASES[0][2], models.Sales, 'sales_rows')])
@pytest.mark.parametrize('failure_at', ['session', 'commit'])
def test_ingestion_infrastructure_errors_are_generic(client, headers, isolated_runtime, monkeypatch,
        endpoint, key, item, model, count_key, failure_at):
    module = {'pos': pos, 'inventory': inventory, 'labor': labor, 'sync': sync}[endpoint]
    sensitive = 'postgresql://private-user:private-password@private-host SELECT secret Traceback'
    if failure_at == 'session':
        monkeypatch.setattr(module, 'SessionLocal', Mock(side_effect=RuntimeError(sensitive)))
    else:
        session = isolated_runtime()
        monkeypatch.setattr(session, 'commit', Mock(side_effect=RuntimeError(sensitive)))
        monkeypatch.setattr(module, 'SessionLocal', lambda: session)
    response = client.post('/data/'+endpoint, headers=headers, json={key: [item]})
    assert response.status_code == 500
    assert response.json() == {'detail': 'DATA_INGESTION_UNAVAILABLE'}
    assert sensitive not in response.text
