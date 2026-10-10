"""Conduit fill (358.22 / Chapter 9) and ampacity adjustment (310.15(C)(1))."""

from __future__ import annotations

import re
import warnings
from typing import Any

from pigtail import raceway
from pigtail.fill import required_cu_in
from pigtail.models.house import House
from pigtail.nec import NECUnchecked, NECViolation
from pigtail.outputs.diagram import circuit_diagram


def _run(
    cid: str, to: str, trade: str, awg: int, pulled: list[dict[str, Any]], **kw: Any
) -> dict[str, Any]:
    return {
        "id": cid,
        "type": "EMT",
        "trade_size": trade,
        "size_awg": awg,
        "to": to,
        "pulled": pulled,
        **kw,
    }


def _wire(name: str, role: str, color: str, **kw: Any) -> dict[str, Any]:
    return {"name": name, "role": role, "color": color, **kw}


def _house(
    breakers: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    landings: list[dict[str, Any]],
    boxes: tuple[str, ...] = ("B", "C"),
) -> House:
    return House.from_dict(
        {
            "meta": {"project": "x"},
            "boxes": [
                {
                    "id": b,
                    "type": "junction",
                    "material": "metal",
                    "volume_cu_in": 42.0,
                    "depth_in": 2.125,
                }
                for b in boxes
            ],
            "panelboards": [
                {"id": "MP", "branch_circuits": breakers, "cables": runs, "splices": landings}
            ],
        }
    )


def _land(run: dict[str, Any], cid: str, poles: int = 1, **terminals: str) -> list[dict[str, Any]]:
    """The panelboard landings of a run: its hots on circuit ``cid``'s LOAD
    terminal(s) in order, its neutral and EGCs on the busbars; ``terminals``
    names any wire's landing instead.
    """
    loads = iter(("LOAD",) if poles == 1 else ("LOAD1", "LOAD2"))
    bus = {"neutral": "MP.NEUTRAL", "egc": "MP.EGC"}
    out = {"egc": "MP.EGC"}  # the tubing, bonded to the cabinet
    for w in run["pulled"]:
        name = w["name"]
        if name in terminals:
            out[name] = terminals[name]
        else:
            out[name] = f"{cid}.{next(loads)}" if w["role"] == "ungrounded" else bus[w["role"]]
    return [{"join": [f"{run['id']}.{name}", end]} for name, end in out.items()]


def _one_circuit(breaker: dict[str, Any], run: dict[str, Any]) -> House:
    return _house(
        [{"id": "C", "circuit_breaker": breaker}], [run], _land(run, "C", breaker.get("poles", 1))
    )


def _to_receptacle(run: str) -> list[dict[str, Any]]:
    """A 14-50R ``R`` on a run's l1 / l2 / n."""
    return [
        {"join": [f"{run}.l1", "R.LINE1"]},
        {"join": [f"{run}.l2", "R.LINE2"]},
        {"join": [f"{run}.n", "R.NEUTRAL"]},
        {"join": [f"{run}.egc", "R.EGC"]},
    ]


def _caps(cid: str, names: list[str]) -> list[dict[str, Any]]:
    return [{"join": [f"{cid}.{n}"]} for n in names]


def _violations(house: House) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        house.check()
    return [str(w.message) for w in caught if issubclass(w.category, NECViolation)]


def _ev(trade: str) -> House:
    """50 A, 120/240 V: 3 x 6 AWG (two hots, a neutral) -- a NEMA 14-50R run."""
    pulled = [
        _wire("l1", "ungrounded", "black"),
        _wire("l2", "ungrounded", "red"),
        _wire("n", "neutral", "white"),
    ]
    ev = _run(
        "EV1",
        "B",
        trade,
        6,
        pulled,
        devices=[{"id": "R", "type": "receptacle", "poles": 2, "nema": "14-50R"}],
        splices=_to_receptacle("EV1"),
    )
    return _house(
        [{"id": "EV", "circuit_breaker": {"poles": 2, "ampere_rating": 50}}],
        [ev],
        _land(ev, "EV", 2),
    )


def test_six_awg_x3_overfills_half_inch_and_fits_three_quarter() -> None:
    assert any(
        m.startswith(
            '358.22: tube EV1 -- 3 wires, 0.1521 of 0.304 sq in (50.0%) in 1/2" EMT; Chapter 9 Table 1 allows 40%'
        )
        for m in _violations(_ev("1/2"))
    )
    filled = raceway.fill(_ev("3/4").cable("EV1"))
    assert filled is not None
    used, allowed = filled
    assert round(used, 2) == 0.29 and allowed == 0.40
    assert not any(m.startswith("358.22") for m in _violations(_ev("3/4")))


def test_120_240_neutral_is_not_current_carrying() -> None:
    house = _ev("3/4")
    assert raceway.current_carrying(house, house.cable("EV1")) == 2  # 310.15(E)(1)


def test_fourteen_fifty_has_a_neutral_terminal() -> None:
    assert _ev("3/4").device("R").terminals == ("LINE1", "LINE2", "NEUTRAL", "EGC")


def _two_lamps(n12: bool) -> House:
    """C5 (L1) and C12 (L2) hots in one run to box B, a lamp on each; the white
    returns both (a multiwire branch circuit), or ``n12`` gives C12 its own.
    """
    pulled = [
        _wire("hot", "ungrounded", "red"),
        _wire("h12", "ungrounded", "black"),
        _wire("n", "neutral", "white"),
    ]
    splices = [{"join": ["E1.hot", "LA.LINE"]}, {"join": ["E1.h12", "LB.LINE"]}]
    if n12:
        pulled.append(_wire("n12", "neutral", "gray"))
        splices += [{"join": ["E1.n", "LA.NEUTRAL"]}, {"join": ["E1.n12", "LB.NEUTRAL"]}]
    else:
        splices.append({"join": ["E1.n", "LA.NEUTRAL", "LB.NEUTRAL"]})
    lamps = [{"id": i, "type": "luminaire", "load_va": 60} for i in ("LA", "LB")]
    run = _run("E1", "B", "1/2", 12, pulled, devices=lamps, splices=splices)
    breakers = [
        {"id": "C5", "circuit_breaker": {"line": "L1", "ampere_rating": 15}},
        {"id": "C12", "circuit_breaker": {"line": "L2", "ampere_rating": 20}},
    ]
    return _house(breakers, [run], _land(run, "C5", h12="C12.LOAD"))


def test_shared_neutral_of_a_multiwire_circuit_is_not_counted() -> None:
    house = _two_lamps(n12=False)
    assert raceway.current_carrying(house, house.cable("E1")) == 2  # the white: unbalanced only
    house = _two_lamps(n12=True)
    assert raceway.current_carrying(house, house.cable("E1")) == 4  # each white: its lamp's return


def test_a_capped_neutral_carries_nothing_and_an_untraced_one_counts() -> None:
    def count(onward: dict[str, Any] | None) -> int:
        pulled = [_wire("hot", "ungrounded", "black"), _wire("n", "neutral", "white")]
        splices = _caps("E1", ["hot", "n"])
        cables = []
        if onward is not None:
            splices = [{"join": ["E1.hot", "E2.hot"]}, {"join": ["E1.n", "E2.n"]}]
            cables = [onward]
        run = _run("E1", "B", "1/2", 12, pulled, splices=splices, cables=cables)
        house = _one_circuit({"line": "L1", "ampere_rating": 20}, run)
        return raceway.current_carrying(house, house.cable("E1"))

    stub = {k: v for k, v in _run("E2", "C", "1/2", 12, []).items() if k != "to"}
    stub["pulled"] = [_wire("hot", "ungrounded", "black"), _wire("n", "neutral", "white")]
    assert count(None) == 1  # capped in B: no load returns on it
    assert count(stub) == 2  # on into a run whose far end is not traced


def test_a_stub_neutral_is_reported_not_checked() -> None:
    pulled = [_wire("hot", "ungrounded", "black"), _wire("n", "neutral", "white")]
    stub = {k: v for k, v in _run("E2", "C", "1/2", 12, pulled).items() if k != "to"}
    run = _run(
        "E1",
        "B",
        "1/2",
        12,
        pulled,
        splices=[{"join": ["E1.hot", "E2.hot"]}, {"join": ["E1.n", "E2.n"]}],
        cables=[stub],
    )
    house = _one_circuit({"line": "L1", "ampere_rating": 20}, run)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        house.check()
    assert any(
        str(w.message).startswith("210.4(B) / 200.4(A): cable E2 -- far end not traced")
        and issubclass(w.category, NECUnchecked)
        for w in caught
    )


def test_ten_current_carrying_conductors_derate_12_awg_below_20_a() -> None:
    hots = [_wire(f"h{i}", "ungrounded", "black") for i in range(9)]
    home = _run(
        "E1",
        "B",
        "1",
        12,
        [_wire("hot", "ungrounded", "black"), _wire("n", "neutral", "white")],
        splices=[{"join": ["E1.hot", *(f"E2.h{i}" for i in range(9))]}, {"join": ["E1.n", "E2.n"]}],
        cables=[
            _run(
                "E2",
                "C",
                "1",
                12,
                [*hots, _wire("n", "neutral", "white")],
                devices=[{"id": "L", "type": "luminaire", "load_va": 60}],
                splices=[
                    *_caps("E2", [f"h{i}" for i in range(1, 9)]),
                    {"join": ["E2.h0", "L.LINE"]},
                    {"join": ["E2.n", "L.NEUTRAL"]},
                ],
            )
        ],
    )
    house = _one_circuit({"line": "L1", "ampere_rating": 20}, home)
    assert raceway.current_carrying(house, house.cable("E2")) == 10
    found = _violations(house)
    assert any(
        m.startswith(
            "310.15(C)(1): cable E2 -- E2.h0 (12 AWG THHN 90 C; 10 current-carrying in the tube, 50%"
        )
        for m in found
    )
    assert "E2" in house.raceway_schedule() and "50%" in house.raceway_schedule()


def _shared_tube(ev_awg: int, *, ev_terminal: int = 75, stranding: str = "stranded") -> House:
    """One 3/4" tube from the panel to box B: C5 (red + white #12) to lamp LA,
    C12 (black + white #12) to lamp LB, and a 50 A EV circuit (3 x ev_awg) to
    a 14-50R -- three circuits, separate neutrals.
    """
    ev = {"size_awg": ev_awg, "stranding": stranding}
    pulled = [
        _wire("hot", "ungrounded", "red"),
        _wire("n5", "neutral", "white"),
        _wire("h12", "ungrounded", "black"),
        _wire("n12", "neutral", "white"),
        _wire("l1", "ungrounded", "black", **ev),
        _wire("l2", "ungrounded", "red", **ev),
        _wire("n", "neutral", "white", **ev),
    ]
    devices = [
        {"id": "LA", "type": "luminaire", "load_va": 60},
        {"id": "LB", "type": "luminaire", "load_va": 60},
        {"id": "R", "type": "receptacle", "poles": 2, "nema": "14-50R", "terminal_c": ev_terminal},
    ]
    splices = [
        {"join": ["C5-E1.hot", "LA.LINE"]},
        {"join": ["C5-E1.n5", "LA.NEUTRAL"]},
        {"join": ["C5-E1.h12", "LB.LINE"]},
        {"join": ["C5-E1.n12", "LB.NEUTRAL"]},
        *_to_receptacle("C5-E1"),
    ]
    run = _run("C5-E1", "B", "3/4", 12, pulled, devices=devices, splices=splices)
    breakers = [
        {"id": "C5", "circuit_breaker": {"line": "L1", "ampere_rating": 15}},
        {"id": "C12", "circuit_breaker": {"line": "L2", "ampere_rating": 20}},
        {
            "id": "EV",
            "circuit_breaker": {"poles": 2, "ampere_rating": 50, "gfci": True, "terminal_c": 75},
        },
    ]
    landings = _land(run, "C5", h12="C12.LOAD", l1="EV.LOAD1", l2="EV.LOAD2")
    return _house(breakers, [run], landings)


def test_three_circuits_in_one_tube_fill_and_derate_together() -> None:
    house = _shared_tube(6)
    run = house.cable("C5-E1")
    assert [bc.id for bc in house.trace.run_circuits(run)] == ["C5", "C12", "EV"]
    filled = raceway.fill(run)
    assert filled is not None
    assert round(filled[0], 3) == 0.385  # 3 x #6 + 4 x #12 in 3/4" EMT
    assert (
        raceway.current_carrying(house, run) == 6
    )  # 4 hots + two 2-wire neutrals; not the 14-50's
    assert [m for m in _violations(house) if not m.startswith(("210.12", "314"))] == []
    assert "C5-E1" in house.raceway_schedule()


def test_eight_awg_cannot_take_50_a_in_the_shared_tube() -> None:
    found = _violations(_shared_tube(8))  # 55 x 0.8 = 44 A; next standard size 45 A < 50 A
    assert any(
        m.startswith(
            "310.15(C)(1): cable C5-E1 -- C5-E1.l1 (8 AWG THHN 90 C; 6 current-carrying in the tube, 80%"
        )
        for m in found
    )


def test_terminal_rating_sets_the_ends() -> None:
    def dedicated(terminal: int) -> list[str]:
        wires = [
            _wire("l1", "ungrounded", "black"),
            _wire("l2", "ungrounded", "red"),
            _wire("n", "neutral", "white"),
        ]
        run = _run(
            "EV1",
            "B",
            "1/2",
            8,
            wires,
            devices=[
                {
                    "id": "R",
                    "type": "receptacle",
                    "poles": 2,
                    "nema": "14-50R",
                    "terminal_c": terminal,
                }
            ],
            splices=[
                {"join": ["EV1.l1", "R.LINE1"]},
                {"join": ["EV1.l2", "R.LINE2"]},
                {"join": ["EV1.n", "R.NEUTRAL"]},
            ],
        )
        breaker = {"poles": 2, "ampere_rating": 50, "terminal_c": 75}
        return _violations(
            _house([{"id": "EV", "circuit_breaker": breaker}], [run], _land(run, "EV", 2))
        )

    assert not any("cable EV1" in m for m in dedicated(75))  # #8 at 75 C terminals: 50 A
    assert any(
        m.startswith("110.14(C)(1): cable EV1 -- EV1.l1 (8 AWG") for m in dedicated(60)
    )  # 40 A


def test_solid_eight_and_larger_in_a_raceway_is_flagged() -> None:
    found = _violations(_shared_tube(6, stranding="solid"))
    assert any(m.startswith("310.3(C): cable C5-E1 -- C5-E1.l1 is solid 6 AWG") for m in found)


def test_small_neutral_must_be_white_or_gray() -> None:
    run = _run(
        "E1",
        "B",
        "1/2",
        12,
        [_wire("hot", "ungrounded", "red"), _wire("n", "neutral", "black")],
        splices=_caps("E1", ["hot", "n"]),
    )
    found = _violations(_one_circuit({"line": "L1", "ampere_rating": 20}, run))
    assert any(m.startswith("200.6(A): cable E1 -- neutral E1.n is black") for m in found)


def test_ambient_correction() -> None:
    assert raceway.correction(30, 90) == 1.0
    assert raceway.correction(50, 90) == 0.82
    assert raceway.correction(50, 60) == 0.58


def test_a_shared_tube_is_bought_once() -> None:
    assert re.search(r'EMT 3/4"\s+1 run\(s\)', _shared_tube(6).bom())  # three circuits, one tube


def test_continuous_load_needs_125_percent() -> None:
    def ev(amps: int, load_va: float) -> list[str]:
        wires = [
            _wire("l1", "ungrounded", "black"),
            _wire("l2", "ungrounded", "red"),
            _wire("n", "neutral", "white"),
        ]
        run = _run(
            "EV1",
            "B",
            "3/4",
            6,
            wires,
            devices=[
                {
                    "id": "R",
                    "type": "receptacle",
                    "poles": 2,
                    "nema": "14-50R",
                    "load_va": load_va,
                    "continuous": True,
                    "terminal_c": 75,
                }
            ],
            splices=_to_receptacle("EV1"),
        )
        return _violations(_one_circuit({"poles": 2, "ampere_rating": amps, "terminal_c": 75}, run))

    assert not any(
        m.startswith(("210.20(A)", "210.19(A)(1)")) for m in ev(50, 9600)
    )  # 40 A x 1.25 = 50
    assert any(
        m.startswith("210.20(A): circuit C -- 40 A breaker, under 125 % of 40 A continuous")
        for m in ev(40, 9600)
    )


def test_receptacle_rating_against_its_circuit() -> None:
    def circuit(nema: str, amps: int) -> list[str]:
        run = _run(
            "E1",
            "B",
            "1/2",
            12,
            [_wire("hot", "ungrounded", "black"), _wire("n", "neutral", "white")],
            devices=[{"id": "R", "type": "receptacle", "nema": nema}],
            splices=[{"join": ["E1.hot", "R.LINE"]}, {"join": ["E1.n", "R.NEUTRAL"]}],
        )
        return _violations(_one_circuit({"line": "L1", "ampere_rating": amps}, run))

    assert any(
        m.startswith("210.21(B)(1): receptacle R -- 15 A (5-15R) alone")
        for m in circuit("5-15R", 20)
    )
    assert not any(m.startswith("210.21") for m in circuit("5-20R", 20))


def test_wire_egc_sized_by_table_250_122() -> None:
    wires = [
        _wire("hot", "ungrounded", "black"),
        _wire("n", "neutral", "white"),
        _wire("g", "egc", "green", size_awg=14),
    ]
    run = _run("E1", "B", "3/4", 6, wires, splices=_caps("E1", ["hot", "n", "g"]))
    found = _violations(_one_circuit({"line": "L1", "ampere_rating": 50}, run))
    assert any(
        m.startswith("Table 250.122: cable E1 -- EGC E1.g is 14 AWG; a 50 A circuit needs 10 AWG")
        for m in found
    )


def test_bends_over_360_degrees() -> None:
    run = _run(
        "E1",
        "B",
        "1/2",
        12,
        [_wire("hot", "ungrounded", "black"), _wire("n", "neutral", "white")],
        bends_deg=450,
        splices=_caps("E1", ["hot", "n"]),
    )
    assert any(
        m.startswith("358.26: cable E1 -- 450 degrees")
        for m in _violations(_one_circuit({"line": "L1", "ampere_rating": 20}, run))
    )


def test_voltage_drop_from_lengths() -> None:
    def ev(length: float) -> tuple[House, list[str]]:
        wires = [
            _wire("l1", "ungrounded", "black"),
            _wire("l2", "ungrounded", "red"),
            _wire("n", "neutral", "white"),
        ]
        run = _run(
            "EV1",
            "B",
            "3/4",
            6,
            wires,
            length_ft=length,
            devices=[
                {
                    "id": "R",
                    "type": "receptacle",
                    "poles": 2,
                    "nema": "14-50R",
                    "load_va": 9600,
                    "continuous": True,
                }
            ],
            splices=_to_receptacle("EV1"),
        )
        house = _one_circuit({"poles": 2, "ampere_rating": 50}, run)
        return house, _violations(house)

    house, found = ev(40)  # 2 x 40 ft x 40 A x 0.491 ohm/kft = 1.57 V of 240
    assert round(raceway.voltage_drop(house, house.branch_circuit("C"))["R"], 4) == 0.0065
    assert not any(m.startswith("210.19(A) IN No. 4") for m in found)
    assert any(
        m.startswith("210.19(A) IN No. 4: circuit C -- 3.3% voltage drop at R") for m in ev(200)[1]
    )


def test_unmarked_terminals_follow_110_14_c_1() -> None:
    small = _one_circuit(
        {"line": "L1", "ampere_rating": 20},
        _run(
            "E1",
            "B",
            "1/2",
            12,
            [_wire("h", "ungrounded", "black"), _wire("n", "neutral", "white")],
            splices=_caps("E1", ["h", "n"]),
        ),
    )
    assert raceway.terminal_rating(small.branch_circuit("C")) == 60


def test_old_tw_wire_is_60_c() -> None:
    run = _run(
        "E1",
        "B",
        "1/2",
        12,
        [
            _wire("h", "ungrounded", "black", insulation="TW"),
            _wire("n", "neutral", "white", insulation="TW"),
        ],
        splices=_caps("E1", ["h", "n"]),
    )
    house = _one_circuit({"line": "L1", "ampere_rating": 20}, run)
    assert raceway.insulation_rating(house.cable("E1").wire("h")) == 60


def test_a_wire_through_a_box_counts_once() -> None:
    def fill(through: bool) -> float | None:
        wires = [
            _wire("l1", "ungrounded", "black"),
            _wire("l2", "ungrounded", "red"),
            _wire("n", "neutral", "white"),
        ]
        e2 = _run("E2", "C", "3/4", 6, wires, splices=_caps("E2", ["l1", "l2", "n"]))
        e1 = _run(
            "E1",
            "B",
            "3/4",
            6,
            wires,
            cables=[e2],
            splices=[
                {"join": [f"E1.{n}", f"E2.{n}"], "through": through} for n in ("l1", "l2", "n")
            ],
        )
        house = _one_circuit({"poles": 2, "ampere_rating": 50}, e1)
        return required_cu_in(house, "B")

    assert fill(False) == 30.0  # 6 x 5.0: three spliced wires, in and out
    assert fill(True) == 15.0  # three wires straight through, once each


def test_mixed_sizes_in_one_run_are_labelled_and_bought_per_size() -> None:
    wires = [
        _wire("hot", "ungrounded", "red"),
        _wire("h12", "ungrounded", "black", size_awg=12),
        _wire("n", "neutral", "white"),
    ]
    run = _run("E1", "B", "3/4", 14, wires, length_ft=20, splices=_caps("E1", ["hot", "h12", "n"]))
    breakers = [
        {"id": "C5", "circuit_breaker": {"line": "L1", "ampere_rating": 15}},
        {"id": "C12", "circuit_breaker": {"line": "L2", "ampere_rating": 20}},
    ]
    house = _house(breakers, [run], _land(run, "C5", h12="C12.LOAD"))
    assert house.cable("E1").spec_label == "EMT 2×14 + 1×12"
    dot = circuit_diagram(house)
    assert 'EMT 3/4" · 20 ft' in dot  # the header: trade size, length
    assert "> 12 AWG </font>" in dot and "> 14 AWG </font>" in dot  # every wire its own gauge
    bom = house.bom()
    assert re.search(r"14 AWG THHN\s+~\s+42 ft", bom) and re.search(r"12 AWG THHN\s+~\s+21 ft", bom)


def _unchecked(house: House) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        house.check()
    return [str(w.message) for w in caught if issubclass(w.category, NECUnchecked)]


def test_a_hardwired_appliance_behind_its_switch() -> None:
    """A furnace hardwired in a box with its switch: on the circuit through the
    switch, no yoke allowance of its own, its load not recorded -- the circuit's
    load and voltage drop are then not checked.
    """
    run = _run(
        "E1",
        "B",
        "1/2",
        12,
        [_wire("black", "ungrounded", "black"), _wire("white", "neutral", "white")],
        devices=[{"id": "S", "type": "snap_switch"}, {"id": "F", "type": "appliance"}],
        splices=[
            {"join": ["E1.black", "S.LINE"]},
            {"join": ["S.LOAD", "F.LINE"]},
            {"join": ["E1.white", "F.NEUTRAL"]},
            {"join": ["E1.egc", "S.EGC", "F.EGC"]},
        ],
    )
    house = _one_circuit({"line": "L1", "ampere_rating": 20}, run)
    assert [d.id for d in house.branch_circuit("C").devices()] == ["S", "F"]
    assert house.device("F").terminals == ("LINE", "NEUTRAL", "EGC")
    assert required_cu_in(house, "B") == 2 * 2.25 + 2 * 2.25  # two #12, one yoke (the switch)
    unchecked = _unchecked(house)
    assert (
        "210.20(A): circuit C -- load not recorded for F; the breaker's load is not checked"
        in unchecked
    )
    assert any(
        m.startswith("210.19(A) IN No. 4: circuit C -- voltage drop not checked") for m in unchecked
    )


def test_a_receptacle_without_its_configuration_is_not_checked() -> None:
    run = _run(
        "E1",
        "B",
        "1/2",
        12,
        [_wire("hot", "ungrounded", "black"), _wire("n", "neutral", "white")],
        devices=[{"id": "R", "type": "receptacle"}],
        splices=[{"join": ["E1.hot", "R.LINE"]}, {"join": ["E1.n", "R.NEUTRAL"]}],
    )
    house = _one_circuit({"line": "L1", "ampere_rating": 20}, run)
    assert _unchecked(house) == [
        "210.21(B): receptacle R -- configuration (NEMA) not recorded; its rating against "
        "circuit C's 20 A is not checked"
    ]
    assert not any(m.startswith("210.21") for m in _violations(house))


def test_a_lone_receptacle_on_a_circuit_running_on_untraced_is_not_checked() -> None:
    """One 15 A receptacle on a 20 A circuit whose hot also runs into an untraced
    run: alone it breaks 210.21(B)(1), with others it meets (B)(3) -- unknown.
    """
    pulled = [_wire("hot", "ungrounded", "black"), _wire("n", "neutral", "white")]
    stub = {k: v for k, v in _run("E2", "C", "1/2", 12, pulled).items() if k != "to"}
    run = _run(
        "E1",
        "B",
        "1/2",
        12,
        pulled,
        devices=[{"id": "R", "type": "receptacle", "nema": "5-15R"}],
        splices=[
            {"join": ["E1.hot", "R.LINE", "E2.hot"]},
            {"join": ["E1.n", "R.NEUTRAL", "E2.n"]},
        ],
        cables=[stub],
    )
    house = _one_circuit({"line": "L1", "ampere_rating": 20}, run)
    assert not any(m.startswith("210.21") for m in _violations(house))
    assert any(
        m.startswith("210.21(B): receptacle R -- 15 A (5-15R) on circuit C's 20 A, which continues")
        for m in _unchecked(house)
    )
    bc = house.branch_circuit("C")
    assert raceway.untraced(bc)
    assert (
        raceway.largest_breaker(house.cable("E1").wire("hot"), bc, 22) == 20
    )  # no 240.4(B) round-up
