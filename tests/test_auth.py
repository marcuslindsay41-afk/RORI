import datetime

import pytest
from jose import jwt

from app.core import auth


def test_password_hashing():
    hashed = auth.get_password_hash('test-only-password')
    assert hashed != 'test-only-password'
    assert auth.verify_password('test-only-password', hashed)
    assert not auth.verify_password('wrong-password', hashed)


def test_real_jwt_me_and_logout(client):
    token = auth.create_access_token({'user_id': 'test-user', 'restaurant_id': 101})
    headers = {'Authorization': f'Bearer {token}'}
    response = client.get('/auth/me', headers=headers)
    assert response.status_code == 200
    assert response.json() == {'user_id': 'test-user', 'restaurant_id': 101, 'authenticated': True}
    response = client.post('/auth/logout', headers=headers)
    assert response.status_code == 200
    assert response.json() == {'message': 'Logged out successfully'}


@pytest.mark.parametrize('kind', ['malformed', 'expired', 'wrong_signature', 'missing_claims'])
def test_invalid_jwt_is_rejected(client, kind):
    payload = {'user_id': 'test-user', 'restaurant_id': 101}
    if kind == 'malformed': token = 'invalid-token'
    elif kind == 'expired': token = auth.create_access_token(payload, datetime.timedelta(seconds=-10))
    elif kind == 'wrong_signature': token = jwt.encode(payload, 'wrong-test-secret', algorithm='HS256')
    else: token = auth.create_access_token({'user_id': 'test-user'})
    for path, method in [('/auth/me', client.get), ('/auth/logout', client.post)]:
        response = method(path, headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 401
        assert 'access_token' not in response.json()


@pytest.mark.parametrize('authorization', [None, 'Basic invalid'])
def test_missing_bearer_is_rejected(client, authorization):
    headers = {} if authorization is None else {'Authorization': authorization}
    for method, path in [(client.get, '/auth/me'), (client.post, '/auth/logout')]:
        response = method(path, headers=headers)
        # HTTPBearer used 403 before FastAPI 0.122; newer releases use 401.
        # Both must deny access, with no authenticated data or token.
        assert response.status_code in {401, 403}
        detail = ('Invalid authentication credentials'
                  if response.status_code == 403 and authorization is not None
                  else 'Not authenticated')
        assert response.json() == {'detail': detail}
        if response.status_code == 401:
            assert response.headers['www-authenticate'] == 'Bearer'


@pytest.mark.parametrize('path,payload', [
    ('/auth/signup', {'email': 'user@example.com', 'password': 'test-only-password', 'restaurant_name': 'Test'}),
    ('/auth/login', {'email': 'user@example.com', 'password': 'test-only-password'}),
])
def test_missing_supabase_is_explicit_failure(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 500
    assert 'SUPABASE_URL environment variable is not set' in response.json()['detail']
    assert 'access_token' not in response.json()


@pytest.mark.parametrize('path', ['/auth/signup', '/auth/login'])
def test_invalid_auth_payload(client, path):
    response = client.post(path, json={'email': 'not-an-email'})
    assert response.status_code == 422


@pytest.mark.external
def test_live_supabase_login(client, monkeypatch):
    """Read-only login with a pre-provisioned user in a dedicated TEST project.

    Never falls back to .env or production variables; never creates users/data.
    """
    from tests.integration_config import supabase_config
    config, expected_restaurant_id = supabase_config()
    monkeypatch.setenv('SUPABASE_URL', config['URL'])
    monkeypatch.setenv('SUPABASE_KEY', config['KEY'])
    response = client.post('/auth/login', json={'email': config['EMAIL'], 'password': config['PASSWORD']})
    # Avoid response bodies/credentials in assertion reports.
    if response.status_code != 200:
        pytest.fail(f'Live Supabase login failed (HTTP {response.status_code}); no credentials or body logged', pytrace=False)
    data = response.json()
    if not data.get('access_token') or data.get('restaurant_id') != expected_restaurant_id:
        pytest.fail('Live login returned missing token or unexpected tenant', pytrace=False)
    me = client.get('/auth/me', headers={'Authorization': f"Bearer {data['access_token']}"})
    if me.status_code != 200 or me.json().get('user_id') != data.get('user_id'):
        pytest.fail('Live login token did not authenticate /auth/me', pytrace=False)
