from __future__ import annotations

from dataclasses import dataclass

from sc2_agent.observation.burnysc2_adapter import BurnySC2ObservationAdapter


@dataclass(frozen=True)
class FakeTypeId:
    name: str


@dataclass(frozen=True)
class FakePosition:
    x: float
    y: float


@dataclass(frozen=True)
class FakeOrder:
    ability: object
    progress: float = 0
    target: object | None = None


@dataclass(frozen=True)
class FakeArea:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class FakeUnit:
    tag: int
    type_id: FakeTypeId
    position: FakePosition
    health: float
    shield: float = 0
    is_idle: bool = False
    build_progress: float = 1
    is_mine: bool = True
    is_enemy: bool = False
    orders: tuple[FakeOrder, ...] = ()


class FakeBot:
    time = 12.5
    minerals = 75
    vespene = 25
    supply_used = 13
    supply_cap = 23
    game_info = type(
        "FakeGameInfo",
        (),
        {"map_size": FakePosition(200, 180), "playable_area": FakeArea(10, 12, 160, 140)},
    )()
    expansion_locations_list = [FakePosition(30, 30), FakePosition(80, 80)]
    state = type("FakeState", (), {"upgrades": [FakeTypeId("STIMPACK")]})()

    units = [
        FakeUnit(tag=1, type_id=FakeTypeId("SCV"), position=FakePosition(1.5, 2.5), health=45, is_idle=True),
        FakeUnit(
            tag=2,
            type_id=FakeTypeId("MARINE"),
            position=FakePosition(9, 9),
            health=45,
            is_mine=False,
            is_enemy=True,
        ),
    ]
    structures = [
        FakeUnit(
            tag=101,
            type_id=FakeTypeId("COMMANDCENTER"),
            position=FakePosition(3, 4),
            health=1500,
            build_progress=0.75,
            orders=(FakeOrder(FakeTypeId("COMMANDCENTERTRAIN_SCV"), 0.25),),
        )
    ]


def test_burnysc2_adapter_maps_botai_fields_to_observation_snapshot() -> None:
    snapshot = BurnySC2ObservationAdapter(FakeBot()).snapshot()

    assert snapshot.game_time == 12.5
    assert snapshot.minerals == 75
    assert snapshot.gas == 25
    assert snapshot.supply_used == 13
    assert snapshot.supply_cap == 23
    assert snapshot.units[0].type_name == "SCV"
    assert snapshot.units[0].x == 1.5
    assert snapshot.units[0].is_idle is True
    assert snapshot.units[1].type_name == "Marine"
    assert snapshot.units[1].alliance == "enemy"
    assert snapshot.structures[0].type_name == "CommandCenter"
    assert snapshot.structures[0].build_progress == 0.75
    assert snapshot.structures[0].orders == [
        {"ability": "COMMANDCENTERTRAIN_SCV", "progress": 0.25, "target": None}
    ]
    assert snapshot.map_width == 200
    assert snapshot.map_height == 180
    assert snapshot.playable_area == {"x": 10.0, "y": 12.0, "width": 160.0, "height": 140.0}
    assert snapshot.expansions == [{"id": 0, "x": 30.0, "y": 30.0}, {"id": 1, "x": 80.0, "y": 80.0}]
    assert snapshot.upgrades == ["STIMPACK"]
