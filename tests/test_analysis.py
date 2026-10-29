import datetime

import pytest
from sqlalchemy import text

from app.models.models import Sales, Inventory, Labor
from app.services.analysis_service import run_analysis, run_full_analysis
from app.rules.engine import check_waste, labor_efficiency, low_performing_items
from app.rules.calculations import inventory_metrics, labor_metrics, revenue_metrics
from app.core.recommendation_containment import OperationalRecommendationsUnavailable
from app.core.logger import log_analysis_run


def test_database_round_trip(db):
    assert db.scalar(text('SELECT 1')) == 1
    db.add(Inventory(restaurant_id=101, item_name='Burger', quantity_in_stock=30, cost_per_unit=2))
    db.commit()
    db.expire_all()
    assert db.query(Inventory).one().quantity_in_stock == 30


def test_logging_denies_without_creating_files(tmp_path):
    recs = [{'type': 'waste', 'priority': 'high', 'meta': {'units': 12}}]
    with pytest.raises(OperationalRecommendationsUnavailable):
        log_analysis_run(recs)
    assert not (tmp_path / 'logs').exists()


def test_offline_calculations_and_tenant_isolation(db, tmp_path):
    db.add_all([
        Sales(restaurant_id=101, date=datetime.date(2026, 1, 1), item_name='Burger', quantity_sold=10, revenue=100),
        Inventory(restaurant_id=101, item_name='Burger', quantity_in_stock=40, cost_per_unit=2),
        Labor(restaurant_id=101, date=datetime.date(2026, 1, 1), hours_worked=4, total_labor_cost=50),
        Inventory(restaurant_id=202, item_name='Other tenant', quantity_in_stock=999, cost_per_unit=99),
    ])
    db.commit()
    # The test supplies observations explicitly; no calculation interface reads
    # a tenant/session or invents observations from absent database rows.
    assert inventory_metrics(40, 10, 2)['estimated_weekly_loss_usd'] == 9
    assert labor_metrics(100, 50)['over_labor_vs_target_usd'] == 20
    assert revenue_metrics((100,))['avg_revenue_usd'] == 100
    for entry in (check_waste, low_performing_items, labor_efficiency):
        with pytest.raises(OperationalRecommendationsUnavailable): entry(db, 202)
    for entry in (run_analysis, run_full_analysis):
        with pytest.raises(OperationalRecommendationsUnavailable): entry(101)
    assert not list((tmp_path / 'logs').glob('analysis_*.json'))
    assert [(r.restaurant_id, r.quantity_in_stock) for r in
            db.query(Inventory).order_by(Inventory.restaurant_id).all()] == [(101, 40), (202, 999)]


@pytest.mark.parametrize('stock,expected', [(29, False), (30, True)])
def test_waste_ratio_boundary(db, stock, expected):
    db.add(Sales(restaurant_id=101, date=datetime.date(2026, 1, 1), item_name='Burger', quantity_sold=10, revenue=100))
    db.add(Inventory(restaurant_id=101, item_name='Burger', quantity_in_stock=stock, cost_per_unit=2))
    db.commit()
    assert (inventory_metrics(stock, 10, 2) is not None) is expected


@pytest.mark.parametrize('cost,key,amount', [(30, 'headroom_under_cap_usd', 0), (31, 'over_labor_vs_target_usd', 1)])
def test_labor_threshold(db, cost, key, amount):
    db.add(Sales(restaurant_id=101, date=datetime.date(2026, 1, 1), item_name='Burger', quantity_sold=10, revenue=100))
    db.add(Labor(restaurant_id=101, date=datetime.date(2026, 1, 1), hours_worked=2, total_labor_cost=cost))
    db.commit()
    assert labor_metrics(100, cost)[key] == amount


def test_empty_database_has_explicit_no_revenue_result(db):
    assert db.query(Sales).count() == 0
    assert revenue_metrics(())['bottom_items'] == ()
    assert revenue_metrics(())['avg_revenue_usd'] is None
    # Explicitly supplied observed zero is distinct from unknown (None).
    assert labor_metrics(0, 0)['labor_to_revenue_pct'] is None
