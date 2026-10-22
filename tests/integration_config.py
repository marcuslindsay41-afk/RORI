"""Validate explicit test-only Supabase settings without logging their values."""
import os

import pytest


def supabase_config():
    if os.getenv('RORI_TEST_SUPABASE_ALLOW') != '1':
        pytest.skip('Live Supabase auth is disabled; enable only for a dedicated test project')
    names = ('URL', 'KEY', 'EMAIL', 'PASSWORD', 'RESTAURANT_ID')
    config = {name: os.getenv(f'RORI_TEST_SUPABASE_{name}') for name in names}
    missing = [f'RORI_TEST_SUPABASE_{name}' for name, value in config.items()
               if not value or not value.strip()]
    if missing:
        pytest.fail('Live Supabase auth enabled but missing: ' + ', '.join(missing), pytrace=False)
    try:
        expected_id = int(config['RESTAURANT_ID'])
    except ValueError:
        pytest.fail('RORI_TEST_SUPABASE_RESTAURANT_ID must be a positive integer', pytrace=False)
    if expected_id <= 0:
        pytest.fail('RORI_TEST_SUPABASE_RESTAURANT_ID must be a positive integer', pytrace=False)
    return config, expected_id
