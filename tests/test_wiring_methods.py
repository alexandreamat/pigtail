"""Knob-and-tube (no EGC) and EMT (raceway is the EGC) wiring methods."""

from __future__ import annotations

from pathlib import Path

import pytest

from pigtail.models.house import House

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def kt_house() -> House:
    return House.from_yaml(EXAMPLES / "knob_and_tube.yaml")


@pytest.fixture
def emt_house() -> House:
    return House.from_yaml(EXAMPLES / "emt_conduit.yaml")


def test_knob_and_tube_has_no_egc(kt_house: House) -> None:
    k1 = kt_house.cable("K1")
    assert k1.has_egc is False
    assert [w.role for w in k1.wires] == ["ungrounded", "neutral"]
    with pytest.raises(KeyError):
        k1.wire("egc")


def test_knob_and_tube_device_ground_pin_floats(kt_house: House) -> None:
    """The receptacle has an EGC terminal, but nothing lands on it."""
    assert kt_house.device("BR1-R1").part["EGC"].net is None


def test_knob_and_tube_splice_to_missing_egc_is_rejected() -> None:
    data = {
        "meta": {"project": "x"},
        "boxes": [
            {
                "id": "B",
                "type": "device",
                "material": "nonmetallic",
                "volume_cu_in": 18.0,
                "depth_in": 2.75,
            }
        ],
        "panelboards": [
            {
                "id": "MP",
                "branch_circuits": [
                    {"id": "C", "circuit_breaker": {"line": "L1", "poles": 1, "ampere_rating": 15}}
                ],
                "cables": [
                    {
                        "id": "K",
                        "type": "knob_and_tube",
                        "size_awg": 14,
                        "conductors": 2,
                        "to": "B",
                        "devices": [{"id": "R", "type": "receptacle"}],
                        "splices": [{"join": ["K.egc", "R.EGC"]}],
                    }
                ],
            }
        ],
    }
    with pytest.raises(Exception, match="egc"):
        House.from_dict(data)


def test_emt_raceway_is_the_egc(emt_house: House) -> None:
    egc = emt_house.cable("E1").wire("egc")
    assert egc.raceway is True
    panel_egc = emt_house.panelboard("MP").egc_net
    assert egc.net.is_attached(panel_egc)


def test_emt_downstream_device_grounds_through_raceway(emt_house: House) -> None:
    panel_egc = emt_house.panelboard("MP").egc_net
    assert emt_house.device("GAR-R6").part["EGC"].net.is_attached(panel_egc)


def test_spec_label(kt_house: House, emt_house: House) -> None:
    assert kt_house.cable("K1").spec_label == "K&T 14"
    assert emt_house.cable("E1").spec_label == "EMT 12/2"


# --- re-identification (NEC 200.7(C)(1) / 250.119) -------------------


def test_reidentified_conductor_plays_its_taped_role() -> None:
    house = House.from_yaml(EXAMPLES / "ev_charger.yaml")
    white = house.cable("EV1").wire("neutral")  # still addressed by its position
    assert white.reidentified_as == "ungrounded"
    assert white.tape == "black"
    assert white.played_role == "ungrounded"


def _ev_data(tape: str) -> dict[str, object]:
    return {
        "meta": {"project": "x"},
        "boxes": [
            {
                "id": "B",
                "type": "device",
                "material": "metal",
                "volume_cu_in": 22.5,
                "depth_in": 2.5,
            }
        ],
        "panelboards": [
            {
                "id": "MP",
                "branch_circuits": [
                    {"id": "C", "circuit_breaker": {"poles": 2, "ampere_rating": 20}}
                ],
                "cables": [
                    {
                        "id": "K",
                        "type": "NM-B",
                        "size_awg": 12,
                        "conductors": 2,
                        "to": "B",
                        "reidentify": [
                            {"conductor": "neutral", "plays": "ungrounded", "tape": tape}
                        ],
                        "devices": [{"id": "R", "type": "receptacle", "poles": 2}],
                        "splices": [
                            {"join": ["K.ungrounded", "R.LINE1"]},
                            {"join": ["K.neutral", "R.LINE2"]},
                            {"join": ["K.egc", "R.EGC"]},
                        ],
                    }
                ],
                "splices": [
                    {"join": ["K.ungrounded", "C.LOAD1"]},
                    {"join": ["K.neutral", "C.LOAD2"]},
                    {"join": ["K.egc", "MP.EGC"]},
                ],
            }
        ],
    }


def test_reidentification_tape_may_not_be_white_gray_or_green() -> None:
    House.from_dict(_ev_data("black"))  # fine
    for bad in ("white", "gray", "green"):
        with pytest.raises(Exception, match="unlawful"):
            House.from_dict(_ev_data(bad))
