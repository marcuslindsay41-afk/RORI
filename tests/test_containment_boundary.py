"""Direct imports, serializers, persistence and cold-start containment."""
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest

from app.core import flatten, logger
from app.core.recommendation_containment import OperationalRecommendationsUnavailable
from app.rules import engine
from scripts import simulate_restaurants as real_simulation
from scripts import simulate_restaurants_mock as mock_simulation

ENTRIES = [
    (engine.check_waste, ('session', 202)),
    (engine.low_performing_items, ('session', 202)),
    (engine.labor_efficiency, ('session', 202)),
    (engine._worst_impact, ('payload',)),
    (engine._format_public_impact, ('high',)),
    (engine._combine_messages, ('payload', 'fallback')),
    (engine._waste_rule_meta, ('payload',)),
    (engine._merge_low_sales_meta, ('payload',)),
    (engine._merge_labor_meta, ('payload',)),
    (logger.log_analysis_run, ('payload',)),
    (flatten.flatten_recommendation, ('payload',)),
    (flatten._flatten_dict, ('payload',)),
    (real_simulation.simulate_restaurant, (202,)),
    (real_simulation.simulate_restaurants, ()),
    (real_simulation.simulate_restaurants_concurrent, ()),
    (mock_simulation.mock_run_full_analysis, ()),
    (mock_simulation.mock_seed_database, ()),
    (mock_simulation.simulate_restaurants, ()),
]


@pytest.mark.parametrize('entry,args', ENTRIES, ids=lambda value: getattr(value, '__name__', None))
def test_direct_boundary_denies_before_data_payload_or_io(entry, args, tmp_path):
    touched = Mock(side_effect=AssertionError('Forbidden input or side effect'))
    class Poison:
        def __getattribute__(self, name):
            raise AssertionError('Input inspected before denial')
        def __iter__(self):
            raise AssertionError('Payload iterated before denial')
    arguments = tuple(Poison() if isinstance(a, str) and a in ('session', 'payload') else a for a in args)
    with patch('builtins.open', touched), patch('os.makedirs', touched), \
         patch('threading.Thread', touched), patch('builtins.print', touched):
        with pytest.raises(OperationalRecommendationsUnavailable) as exc:
            entry(*arguments)
    assert str(exc.value) == 'OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE'
    touched.assert_not_called()
    assert not (tmp_path / 'logs').exists()


@pytest.mark.parametrize('http_application', [False, True])
def test_cold_start_without_operational_credentials(tmp_path, http_application):
    root = Path(__file__).resolve().parents[1]
    code = r'''
import os, sys, socket
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected database or external-network dependency')
socket.socket.connect = forbidden
# Existing app/__init__.py loads .env. Intercept it before the FIRST app import;
# this protects the test from real configuration, not an authorization switch.
with patch('dotenv.load_dotenv', return_value=False):
    from app.core.recommendation_containment import OperationalRecommendationsUnavailable
    from app.services import analysis_service as service
    from app.rules import engine
    from app.core import logger, flatten
    from scripts import simulate_restaurants as simulation
    from scripts import simulate_restaurants_mock as mock
    entries = [(getattr(service,n),(202,)) for n in
        ('run_analysis','run_full_analysis','get_latest_recommendations','run_background_analysis')]
    entries += [(getattr(engine,n),(None,202)) for n in
        ('check_waste','low_performing_items','labor_efficiency','run_all_rules')]
    entries += [(logger.log_analysis_run,([],)),(flatten.flatten_recommendation,({},)),
        (simulation.simulate_restaurant,(202,)),(simulation.simulate_restaurants,()),
        (simulation.simulate_restaurants_concurrent,()),(mock.mock_run_full_analysis,()),
        (mock.simulate_restaurants,()),(mock.mock_seed_database,())]
    assert 'app.models.models' not in sys.modules
    from app.rules.calculations import inventory_metrics, labor_metrics, revenue_metrics
    assert inventory_metrics(40,10,2)['estimated_weekly_loss_usd']==9
    assert labor_metrics(100,50)['over_labor_vs_target_usd']==20
    assert revenue_metrics(())['avg_revenue_usd'] is None
    assert 'sqlalchemy' not in sys.modules
    for entry,args in entries:
        try: entry(*args)
        except OperationalRecommendationsUnavailable as exc:
            assert str(exc)=='OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE'
        else: raise AssertionError('Cold-start entry did not deny')
    assert 'app.models.models' not in sys.modules
    if sys.argv[2]=='http':
        # Full ingestion application requires a DB URL to import. Supply only a
        # synthetic in-memory SQLite URL; no API keys, JWT or Supabase settings.
        os.environ['DATABASE_URL']='sqlite://'
        from app.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            for method,path in [('POST','/run-analysis'),('GET','/recommendations'),
                ('POST','/run-analysis/202'),('POST','/analysis/run-analysis/202')]:
                response=client.request(method,path)
                assert response.status_code==503
                assert response.json()=={'detail':'OPERATIONAL_RECOMMENDATIONS_UNAVAILABLE'}
print('cold-start containment verified')
'''
    env = {k: v for k, v in os.environ.items() if not k.startswith(('RORI_', 'SUPABASE_'))
           and k not in ('DATABASE_URL', 'JWT_SECRET_KEY')}
    result = subprocess.run([sys.executable, '-c', code, str(root), 'http' if http_application else 'internal'],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'cold-start containment verified'
