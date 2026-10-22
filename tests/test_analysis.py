import datetime
import json

import pytest
from sqlalchemy import text

from app.models.models import Sales, Inventory, Labor
from app.services.analysis_service import run_analysis, run_full_analysis
from app.rules.engine import check_waste, labor_efficiency
from app.core.logger import log_analysis_run


def test_database_round_trip(db):
    assert db.scalar(text('SELECT 1')) == 1
    db.add(Inventory(restaurant_id=101, item_name='Burger', quantity_in_stock=30, cost_per_unit=2))
    db.commit()
    db.expire_all()
    assert db.query(Inventory).one().quantity_in_stock == 30


def test_logging(tmp_path):
    recs = [{'type': 'waste', 'priority': 'high', 'meta': {'units': 12}}]
    log_analysis_run(recs)
    files = list((tmp_path / 'logs').glob('analysis_*.json'))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data['recommendations'] == recs
    assert datetime.datetime.fromisoformat(data['timestamp'])


def test_analysis_contract_sorting_and_tenant_isolation(db, tmp_path):
    db.add_all([
        Sales(restaurant_id=101, date=datetime.date(2026, 1, 1), item_name='Burger', quantity_sold=10, revenue=100),
        Inventory(restaurant_id=101, item_name='Burger', quantity_in_stock=40, cost_per_unit=2),
        Labor(restaurant_id=101, date=datetime.date(2026, 1, 1), hours_worked=4, total_labor_cost=50),
        Inventory(restaurant_id=202, item_name='Other tenant', quantity_in_stock=999, cost_per_unit=99),
    ])
    db.commit()
    raw = run_analysis(101)
    assert [r['type'] for r in raw] == ['waste', 'low_sales', 'labor']
    for rec in raw:
        assert set(rec) == {'type', 'message', 'impact', 'priority', 'meta'}
        assert rec['message'] and 'cost exposure' in rec['impact']
        assert rec['priority'] in {'high', 'medium', 'low'}
        assert isinstance(rec['meta'], dict)
        assert 'Other tenant' not in rec['message']
    assert raw[0]['meta']['flags'][0]['estimated_weekly_loss_usd'] == 9
    assert raw[2]['meta']['over_labor_vs_target_usd'] == 20
    sorted_recs = run_full_analysis(101)
    assert [r['type'] for r in sorted_recs] == ['labor', 'waste', 'low_sales']
    assert sorted_recs == sorted(raw, key=lambda r: {'high': 0, 'medium': 1, 'low': 2}[r['priority']])
    logged = json.loads(next((tmp_path / 'logs').glob('analysis_*.json')).read_text())
    assert logged['recommendations'] == sorted_recs


@pytest.mark.parametrize('stock,expected', [(29, False), (30, True)])
def test_waste_ratio_boundary(db, stock, expected):
    db.add(Sales(restaurant_id=101, date=datetime.date(2026, 1, 1), item_name='Burger', quantity_sold=10, revenue=100))
    db.add(Inventory(restaurant_id=101, item_name='Burger', quantity_in_stock=stock, cost_per_unit=2))
    db.commit()
    assert bool(check_waste(db, 101)) is expected


@pytest.mark.parametrize('cost,impact', [(30, 'low'), (31, 'high')])
def test_labor_threshold(db, cost, impact):
    db.add(Sales(restaurant_id=101, date=datetime.date(2026, 1, 1), item_name='Burger', quantity_sold=10, revenue=100))
    db.add(Labor(restaurant_id=101, date=datetime.date(2026, 1, 1), hours_worked=2, total_labor_cost=cost))
    db.commit()
    assert labor_efficiency(db, 101)[0]['impact'] == impact


def test_empty_database_has_explicit_no_revenue_result():
    recs = {r['type']: r for r in run_analysis(101)}
    assert recs['waste']['meta']['flags'] == []
    assert recs['low_sales']['meta']['bottom_items'] == []
    assert recs['labor']['meta']['labor_to_revenue_pct'] is None
    assert recs['labor']['priority'] == 'high'
