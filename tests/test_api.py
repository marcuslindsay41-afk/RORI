import json

import pytest
from app.models.models import Sales, Inventory, Labor
from app.api import pos

CASES = [
    ('pos', 'sales', {'date': '2026-01-01', 'item_name': 'Burger', 'quantity_sold': 10, 'revenue': 100}, Sales, 'rows_inserted'),
    ('inventory', 'inventory', {'item_name': 'Burger', 'quantity_in_stock': 40, 'cost_per_unit': 2}, Inventory, 'rows_updated'),
    ('labor', 'labor', {'date': '2026-01-01', 'hours_worked': 4, 'total_labor_cost': 50}, Labor, 'rows_inserted'),
]


def test_health(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


@pytest.mark.parametrize('endpoint,key,item,model,count_key', CASES)
def test_ingestion_persists_without_analysis(client, headers, db, tmp_path, endpoint, key, item, model, count_key):
    response = client.post(f'/data/{endpoint}', headers=headers, json={key: [item], 'restaurant_id': 202})
    assert response.status_code == 200, response.text
    assert response.json() == {'status': 'success', count_key: 1}
    row = db.query(model).one()
    assert row.restaurant_id == 101  # Payload cannot choose another tenant.
    for field, value in item.items():
        assert (getattr(row, field).isoformat() if field == 'date' else getattr(row, field)) == value
    assert not list((tmp_path / 'logs').glob('analysis_*.json'))
    events = json.loads(next((tmp_path / 'logs').glob('ingestion_*.json')).read_text())
    assert events[-1]['status'] == 'success'
    assert events[-1]['rows'] == 1


@pytest.mark.parametrize('endpoint,key,item,model,count_key', CASES)
@pytest.mark.parametrize('kind,status', [('missing_key', 422), ('invalid_key', 401), ('empty', 422), ('negative', 422)])
def test_rejected_ingestion_does_not_write(client, headers, db, endpoint, key, item, model, count_key, kind, status):
    item = dict(item)
    payload = {key: [item]}
    if kind == 'missing_key': headers = {}
    if kind == 'invalid_key': headers = {'X-API-Key': 'invalid'}
    if kind == 'empty': payload[key] = []
    if kind == 'negative':
        field = {'pos': 'quantity_sold', 'inventory': 'quantity_in_stock', 'labor': 'hours_worked'}[endpoint]
        item[field] = -1
    response = client.post(f'/data/{endpoint}', headers=headers, json=payload)
    assert response.status_code == status, response.text
    assert db.query(model).count() == 0
    if kind == 'missing_key':
        assert ['header', 'X-API-Key'] in [e['loc'] for e in response.json()['detail']]


@pytest.mark.parametrize('endpoint,key,item,model,count_key', [CASES[0], CASES[2]])
def test_bad_date_rolls_back_entire_batch(client, headers, db, endpoint, key, item, model, count_key):
    response = client.post(f'/data/{endpoint}', headers=headers, json={key: [item, {**item, 'date': 'bad-date'}]})
    assert response.status_code == 400
    assert db.query(model).count() == 0


@pytest.mark.parametrize('case', [CASES[1], CASES[2]])
def test_upsert_is_tenant_scoped(client, db, case):
    endpoint, key, item, model, _ = case
    field = 'quantity_in_stock' if endpoint == 'inventory' else 'hours_worked'
    for api_key, value in [('pytest-only-key', 10), ('pytest-other-key', 20), ('pytest-only-key', 30)]:
        response = client.post(f'/data/{endpoint}', headers={'X-API-Key': api_key}, json={key: [{**item, field: value}]})
        assert response.status_code == 200, response.text
    rows = db.query(model).order_by(model.restaurant_id).all()
    assert [(r.restaurant_id, getattr(r, field)) for r in rows] == [(101, 30), (202, 20)]


def test_sync_and_analysis(client, headers, db):
    payload = {key: [item] for _, key, item, _, _ in CASES}
    response = client.post('/data/sync', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {'status': 'success', 'sales_rows': 1, 'inventory_rows': 1, 'labor_rows': 1}
    assert [db.query(m).count() for m in (Sales, Inventory, Labor)] == [1, 1, 1]
    response = client.post('/run-analysis/101')
    assert response.status_code == 503, response.text
    assert response.json() == {'detail': 'OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE'}


def test_sync_failure_rolls_back_all_tables(client, headers, db):
    payload = {key: [item] for _, key, item, _, _ in CASES}
    payload['labor'] = [{**payload['labor'][0], 'date': 'bad-date'}]
    assert client.post('/data/sync', headers=headers, json=payload).status_code == 400
    assert [db.query(m).count() for m in (Sales, Inventory, Labor)] == [0, 0, 0]


def test_database_failure_is_http_error(client, headers, isolated_runtime, monkeypatch, db):
    session = isolated_runtime()
    def fail_commit():
        raise RuntimeError('simulated database failure')
    monkeypatch.setattr(session, 'commit', fail_commit)
    monkeypatch.setattr(pos, 'SessionLocal', lambda: session)
    response = client.post('/data/pos', headers=headers, json={'sales': [CASES[0][2]]})
    assert response.status_code == 500
    assert response.json() == {'detail': 'DATA_INGESTION_UNAVAILABLE'}
    assert db.query(Sales).count() == 0


def test_unconfigured_api_keys_fail_closed(client, monkeypatch, db):
    monkeypatch.delenv('RORI_API_KEYS')
    response = client.post('/data/pos', headers={'X-API-Key': 'anything'}, json={'sales': [CASES[0][2]]})
    assert response.status_code == 500
    assert 'not configured' in response.json()['detail']
    assert db.query(Sales).count() == 0


def test_legacy_analysis_and_recommendations(client):
    for method, path in [('GET', '/recommendations'), ('POST', '/run-analysis')]:
        response = client.request(method, path)
        assert response.status_code == 503
        assert response.json() == {'detail': 'OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE'}


def test_analysis_database_failure_is_not_success(client, monkeypatch):
    from app.services import analysis_service
    def fail_analysis(restaurant_id):
        raise RuntimeError('simulated analysis failure')
    monkeypatch.setattr(analysis_service, 'run_full_analysis', fail_analysis)
    response = client.post('/run-analysis/101')
    assert response.status_code == 503
    assert response.json() == {'detail': 'OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE'}
