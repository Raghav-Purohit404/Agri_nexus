"""Hand-checkable scientific and domain contract tests for P01–P08."""

from datetime import datetime, timezone

import pytest

from farm_twin.core.provenance import Provenance, Quantified, ValueSource, assert_no_provenance_upgrade
from farm_twin.models.finance.cashflow import irr, npv
from farm_twin.models.soil.amendments import gypsum_requirement_kg_ha
from farm_twin.models.soil.rothc import decay_pool
from farm_twin.models.soil.salinity import extra_water_mm, leaching_requirement, salt_kg_ha


def _prov(source: ValueSource) -> Provenance:
    now = datetime.now(timezone.utc)
    return Provenance(source=source, source_name="test", observed_at=now, retrieved_at=now)


def test_measured_observation_cannot_be_upgraded_or_replaced():
    measured = Quantified(value=12.0, unit="mg/kg", prov=_prov(ValueSource.MEASURED))
    predicted = Quantified(value=12.0, unit="mg/kg", prov=_prov(ValueSource.MODEL_PREDICTED))
    with pytest.raises(Exception):
        assert_no_provenance_upgrade(measured, predicted)
    with pytest.raises(Exception):
        assert_no_provenance_upgrade(predicted, measured)


def test_salt_mass_unit_conversion():
    assert salt_kg_ha(1.0, 10.0) == pytest.approx(64.0)


def test_leaching_requirement_and_extra_water():
    lr = leaching_requirement(1.5, 6.0)
    assert lr == pytest.approx(1.5 / 28.5)
    assert extra_water_mm(100.0, lr) == pytest.approx(100.0 / 18.0)


def test_finance_textbook_npv_and_irr():
    flows = [-1000.0, 300.0, 300.0, 300.0, 300.0, 300.0]
    assert npv(flows, 0.10) == pytest.approx(137.24, abs=0.01)
    assert irr(flows) == pytest.approx(0.1524, abs=0.0001)


def test_rothc_pool_decay_is_mass_conserving():
    remaining, loss = decay_pool(100.0, k_per_year=0.5, dt_years=1.0)
    assert remaining + loss == pytest.approx(100.0)
    assert 0 <= remaining <= 100.0


def test_gypsum_requirement_fixture_value():
    assert gypsum_requirement_kg_ha(
        cec_cmolc_kg=10.0,
        esp_initial=10.0,
        esp_target=0.0,
        depth_m=0.15,
        bulk_density_t_m3=1.4,
        purity_fraction=1.0,
        efficiency=1.0,
    ) == pytest.approx(1808.1, rel=0.002)
