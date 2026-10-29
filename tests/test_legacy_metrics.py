"""Pure numerical observations do not become operational recommendations."""
import pytest

from app.rules.calculations import inventory_metrics, revenue_metrics, labor_metrics


@pytest.mark.parametrize('stock,sold,cost,loss', [
    (40, 10, 2, 9), (30, 10, 2, 6), (29, 10, 2, None),
    (20, 0, 2, None), (21, 0, 2, 3.36), (0, 0, 0, None),
])
def test_inventory_arithmetic_and_original_thresholds(stock, sold, cost, loss):
    result = inventory_metrics(stock, sold, cost)
    if loss is None: assert result is None
    else: assert result['estimated_weekly_loss_usd'] == loss


def test_revenue_observations_ranking_and_clamped_percentages():
    result = revenue_metrics((100, 50, 150, 0))
    assert result['avg_revenue_usd'] == 75
    assert result['items_in_menu'] == 4
    assert [v['index'] for v in result['bottom_items']] == [3, 1, 0]
    assert [v['pct_below_period_avg'] for v in result['bottom_items']] == [100, 33, 0]
    assert revenue_metrics(())['avg_revenue_usd'] is None
    assert revenue_metrics((0,))['avg_revenue_usd'] == 0


@pytest.mark.parametrize('revenue,cost,key,amount', [
    (100, 50, 'over_labor_vs_target_usd', 20),
    (100, 30, 'headroom_under_cap_usd', 0),
    (100, 29, 'headroom_under_cap_usd', 1),
    (0, 50, 'labor_to_revenue_pct', None),
])
def test_labor_arithmetic_preserves_original_boundary(revenue, cost, key, amount):
    result = labor_metrics(revenue, cost)
    assert result[key] == amount
    assert result['threshold_pct'] == 30


@pytest.mark.parametrize('value', [None, True, '1', -1, float('nan'), float('inf')])
def test_unknown_invalid_values_are_not_observed_zero(value):
    with pytest.raises(ValueError): inventory_metrics(40, 10, value)
    with pytest.raises(ValueError): revenue_metrics((value,))
    with pytest.raises(ValueError): labor_metrics(value, 50)


@pytest.mark.parametrize('args', [(None, 0, 2), (0, None, 2), (True, 0, 2), (1.5, 0, 2)])
def test_inventory_requires_explicit_integer_observations(args):
    with pytest.raises(ValueError): inventory_metrics(*args)


def test_no_session_tenant_source_handle_or_operational_fields():
    with pytest.raises(TypeError): inventory_metrics(40, 10, 2, restaurant_id=101)
    with pytest.raises(TypeError): labor_metrics(100, 50, decision_eligible=True)
    with pytest.raises(ValueError): revenue_metrics(iter((100, 50)))
    forbidden = {'message', 'impact', 'priority', 'decision_eligible', 'recommended_value',
                 'suggested_order_reduction_pct', 'authorization', 'verification_status'}
    for result in (inventory_metrics(40, 10, 2), revenue_metrics((100, 50)), labor_metrics(100, 50)):
        assert not forbidden.intersection(result)


@pytest.mark.parametrize('calculate,args', [
    (inventory_metrics, (100, 0, 1e308)),
    (revenue_metrics, ((1e308, 1e308),)),
    (labor_metrics, (1e-308, 1e308)),
])
def test_nonfinite_derived_statistics_fail_explicitly(calculate, args):
    with pytest.raises(ValueError): calculate(*args)
