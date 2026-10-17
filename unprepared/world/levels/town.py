"""The starter town: one cobbled main street running east-west inside a walled
100 x 64 yard, merchants along the north side, homes along the south side and
the guard house, watchtower and jail closing the east end.

    x -50 .............................................................. 50
    z -32  [wall]
         ore deposit                                           watchtower
      smithy  shed | The Drowsy Dragon (inn) | general store | tailor | guard house   (north: doors at z = -6)
    ================= main street (cobbles, z -6 .. 6, the well at 0,0) ====================
      Barnaby | Tamsin | hideout (Raz) | Fenwick | Lys & Dorran | Pell |   jail            (south: doors at z = 6/7)
    z  32  [wall]

Every door hinge sits on the building wall that faces the street; north-side
doors swing into the building, south-side doors swing out onto the street
(``Door`` leaves always span +x from the hinge and fold into -z). All yards are
measured so that nothing overlaps: walls are 0.5 thick and every piece of
furniture stands clear of them.

Named spots used by the schedules are module constants so tests and scenarios
can refer to them.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from ...entities import AIState, DoorKind
from ..level import (AreaDef, BuildingDef, ContainerDef, DoorDef, InnDef, InnRoomDef, ItemDef, JailDef, LevelDefinition,
                     LightDef, NPCDef, PropDef, RoadDef, StationDef, StockTier, TaskDef, WallDef)
from ..tower import build_tower

WALL = 0.5                       # wall thickness
STREET_NORTH, STREET_SOUTH = -6.0, 6.0

# --- named spots ------------------------------------------------------------------------------
WELL = (0.0, 0.0, 0.0)
# general store
SHOP_COUNTER = (1.0, 0.0, -12.2)
SHOP_FLOOR = (1.0, 0.0, -8.4)          # where a customer stands to be served
SHOP_BACKROOM = (4.6, 0.0, -12.85)      # beside the back-room table
SHOP_PORTER = (6.0, 0.0, -9.0)         # Dorran's spot as he fetches and carries
# inn
INN_BAR = (-22.0, 0.0, -12.8)          # Hilde behind the bar
INN_KITCHEN = (-21.9, 0.0, -14.0)       # between the kitchen table and the bar
INN_TABLES = ((-15.25, 0.0, -14.0), (-15.25, 0.0, -8.5), (-10.75, 0.0, -11.0))
# seats west of each table face +x (90), seats east of it face -x (270)
INN_SEATS = ((-16.6, 0.0, -14.0), (-16.6, 0.0, -8.5), (-12.1, 0.0, -11.0), (-13.9, 0.0, -14.0), (-13.9, 0.0, -8.5),
             (-9.4, 0.0, -11.0))
INN_KEEPER_BED = (-23.75, 0.0, -20.0)
INN_ROOM_BEDS = ((-19.25, 0.0, -20.0), (-14.75, 0.0, -20.0), (-10.25, 0.0, -20.0))
# smithy
ANVIL_SPOT = (-34.0, 0.0, -7.8)
FORGE_SPOT = (-32.6, 0.0, -8.9)        # at the forge, the coals in front of him
SMITH_BED = (-44.6, 0.0, -13.3)
SMITH_TABLE_SEAT = (-40.2, 0.0, -8.3)
ORE_DEPOSIT = (-34.5, 0.0, -19.5)
# tailor
TAILOR_COUNTER = (15.5, 0.0, -11.1)
TAILOR_FLOOR = (15.5, 0.0, -8.0)
TAILOR_BED = (19.25, 0.0, -12.5)
TAILOR_TABLE_SEAT = (16.6, 0.0, -7.6)
# homes (south side)
BARNABY_BED = (-37.25, 0.0, 13.25)
BARNABY_TABLE_SEAT = (-41.5, 0.0, 12.0)
TAMSIN_BED = (-31.75, 0.0, 11.25)
TAMSIN_TABLE_SEAT = (-28.25, 0.0, 10.2)
RAZ_DEN = (-16.0, 0.0, 12.0)
RAZ_BED = (-20.75, 0.0, 14.5)
RAZ_TABLE_SEAT = (-20.0, 0.0, 11.0)
FENWICK_BED = (-7.75, 0.0, 10.75)
FENWICK_TABLE_SEAT = (-3.75, 0.0, 10.1)
LYS_BED = (9.5, 0.0, 13.25)
DORRAN_BED = (9.5, 0.0, 10.25)
COUPLE_TABLE_SEATS = ((4.0, 0.0, 13.2), (5.8, 0.0, 11.6))      # Lys south of the table (faces -z), Dorran east (faces -x)
PELL_BED = (19.25, 0.0, 11.25)
PELL_TABLE_SEAT = (15.5, 0.0, 10.2)
# guards & jail
GUARD_BEDS = ((31.55, 0.0, -14.2), (31.55, 0.0, -11.2), (31.55, 0.0, -8.2), (35.0, 0.0, -14.5))   # the last one along the north wall
GUARD_TABLE_SEATS = ((36.3, 0.0, -10.5), (38.5, 0.0, -13.0), (40.7, 0.0, -10.5))
POST_DOOR = (36.5, 0.0, -4.0)          # outside the guard house door, watching the street
POST_WEST = (-12.0, 0.0, -4.0)         # by the inn's east corner, watching the west half of the street
TOWER_X1, TOWER_Z1, TOWER_X2, TOWER_Z2 = 35.5, -22.0, 41.5, -16.0   # the watchtower: behind the guard house, entered from it
TOWER_PLATFORM = 13.0                  # a third taller than the old solid tower (10)
TOWER_DOOR_X = 37.5                    # the doorway 37.5..39.5 in the guard house's north wall
WATCHTOWER = build_tower("watchtower", TOWER_X1, TOWER_Z1, TOWER_X2, TOWER_Z2, TOWER_PLATFORM, TOWER_DOOR_X, room="the watchtower")
TOWER_TOP = WATCHTOWER.stair.top       # the look-out spot on the platform
JAIL_POST = (34.8, 0.0, 10.5)          # in the jail office, facing the cell gate
JAIL_GUARD_BED = (33.55, 0.0, 8.0)
JAIL_CELL_BED = (40.75, 0.0, 14.5)
JAIL_CELL_SPOT = (39.0, 0.0, 13.0)
PATROL_ROUTE = ((30.0, 0.0, -2.0), (15.0, 0.0, 3.0), (3.0, 0.0, -3.0), (-12.0, 0.0, 3.0), (-28.0, 0.0, -2.0),
                (-42.0, 0.0, 2.0), (-28.0, 0.0, 3.5), (-12.0, 0.0, -3.0), (3.0, 0.0, 3.5), (15.0, 0.0, -3.0))
# where people stroll: a loop along the street with a stop at the well
STROLL_WEST = ((-30.0, 0.0, 2.0), (-18.0, 0.0, -2.5), (-6.0, 0.0, 3.0), (2.4, 0.0, 2.4), (-8.0, 0.0, -3.0), (-24.0, 0.0, 3.5))
STROLL_EAST = ((20.0, 0.0, 2.0), (8.0, 0.0, -3.0), (2.4, 0.0, -2.4), (-4.0, 0.0, 3.0), (10.0, 0.0, 3.5), (26.0, 0.0, -2.0))

# aliases kept for older tests / scenarios
HOME_BED, HOME_TABLE, RAZ_ALLEY, TOWN_SQUARE, ANVIL = BARNABY_BED, BARNABY_TABLE_SEAT, RAZ_DEN, WELL, ANVIL_SPOT

SHOP_OPEN_HOUR, SHOP_LUNCH_HOUR, SHOP_CLOSE_HOUR = 8, 13, 20
TAILOR_OPEN_HOUR, TAILOR_CLOSE_HOUR = 9, 18
INN_OPEN_HOUR, INN_CLOSE_HOUR = 5, 24
GUARD_GOLD, SHOPKEEPER_GOLD, FENCE_GOLD, INNKEEPER_GOLD, SMITH_GOLD, TAILOR_GOLD = 15.0, 400.0, 600.0, 250.0, 350.0, 300.0
TOWNSFOLK_GOLD = 30.0

GUARD_KEY = ItemDef("guard_key", "Guard House Key", value=1.0, is_key=True, key_door_id="guardhouse_door", for_sale=False,
                    category="key")
TOWER_KEY = ItemDef("tower_key", "Watchtower Key", value=1.0, is_key=True, key_door_id="tower_door", for_sale=False, category="key")
RATIONS = ItemDef("ration", "Guard's Ration", value=3.0, stackable=True, quantity=2, is_food=True, category="food")


def key_item(door_id: str, label: str) -> ItemDef:
    return ItemDef(f"{door_id}_key", label, value=1.0, is_key=True, key_door_id=door_id, for_sale=False, category="key")


# --- geometry helpers ---------------------------------------------------------------------------
def house_walls(x1: float, z1: float, x2: float, z2: float, door_x: float, door_side: str, texture: str = "building",
                door_width: float = 3.0, height: float = 4.0, door_x2: Optional[float] = None,
                door_width2: float = 3.0) -> List[WallDef]:
    """Four walls of a rectangular building with a door gap in the ``door_side`` ("north" = the
    z1 wall, "south" = the z2 wall) starting at ``door_x``; ``door_x2`` cuts a second doorway in
    the opposite wall (the guard house's way into the tower)."""
    walls = [
        WallDef((x1, 0, z1), (x1 + WALL, height, z2), texture=texture),            # west
        WallDef((x2 - WALL, 0, z1), (x2, height, z2), texture=texture),            # east
    ]
    for side, za, zb in (("north", z1, z1 + WALL), ("south", z2 - WALL, z2)):
        if side == door_side:
            walls.append(WallDef((x1, 0, za), (door_x, height, zb), texture=texture))
            walls.append(WallDef((door_x + door_width, 0, za), (x2, height, zb), texture=texture))
        elif door_x2 is not None:
            walls.append(WallDef((x1, 0, za), (door_x2, height, zb), texture=texture))
            walls.append(WallDef((door_x2 + door_width2, 0, za), (x2, height, zb), texture=texture))
        else:
            walls.append(WallDef((x1, 0, za), (x2, height, zb), texture=texture))
    return walls


def bed(name: str, centre: Tuple[float, float, float], along_x: bool = False) -> PropDef:
    cx, _, cz = centre
    hx, hz = (1.0, 0.75) if along_x else (0.75, 1.0)
    return PropDef(name, (cx - hx, 0, cz - hz), (cx + hx, 0.6, cz + hz))


def table(name: str, label: str, centre: Tuple[float, float, float], items=(), owner=None, size=(0.75, 0.5)) -> ContainerDef:
    cx, _, cz = centre
    hx, hz = size
    return ContainerDef(name, label, (cx - hx, 0, cz - hz), (cx + hx, 0.8, cz + hz), items=tuple(items), owner=owner,
                        texture="wood", kind="table")


def span(rng, state, text, pos, **kw) -> List[TaskDef]:
    """Tasks for a (start, end) hour range that may wrap past midnight."""
    start, end = rng
    if start < end:
        return [TaskDef(start, end, pos, state, text, **kw)]
    return [TaskDef(start, 24, pos, state, text, **kw), TaskDef(0, end, pos, state, text, **kw)]


def guard(name: str, patrol: tuple, meal: tuple, post: tuple, post_spot, sleep: tuple, bed_spot, meal_seat,
          post_facing: float = 270.0) -> NPCDef:
    """A guard with an 8-hour shift rotation."""
    tasks = []
    tasks += span(patrol, AIState.PATROL, f"{name} is patrolling the town.", PATROL_ROUTE[0],
                  patrol_points=PATROL_ROUTE, depart_text="Time for my rounds.")
    tasks += span(meal, AIState.EATING, f"{name} is eating at the guard house table.", meal_seat, facing=90.0,
                  food_container="guard_table")
    tasks += span(post, AIState.GUARDING, f"{name} is standing guard.", post_spot, facing=post_facing)   # facing down the street
    tasks += span(sleep, AIState.SLEEPING, f"{name} is asleep in the guard house.", bed_spot)
    return NPCDef(name, bed_spot, is_guard=True, inventory=(GUARD_KEY, TOWER_KEY, RATIONS), schedule=tuple(tasks),
                  inventory_reset_days=1, gold=GUARD_GOLD, role="guard")


def resident_tasks(name: str, home_door: str, bed_spot, table_seat, food: str, day: List[TaskDef],
                   wake: int = 7, bedtime: int = 21, facing: float = 0.0) -> Tuple[TaskDef, ...]:
    """Frame a resident's day: breakfast at home (unlocking the door), the ``day`` tasks, supper at
    home and bed (locking up). Everyone who is not a guard lives like this."""
    tasks = [
        TaskDef(0, wake, bed_spot, AIState.SLEEPING, f"{name} is asleep at home.", lock_doors=(home_door,)),
        TaskDef(wake, wake + 1, table_seat, AIState.EATING, f"{name} is having breakfast.", unlock_doors=(home_door,),
                facing=facing, food_container=food),
    ]
    tasks += day
    tasks += [
        TaskDef(bedtime - 1, bedtime, table_seat, AIState.EATING, f"{name} is having supper at home.",
                unlock_doors=(home_door,), facing=facing, food_container=food),
        TaskDef(bedtime, 24, bed_spot, AIState.SLEEPING, f"{name} locked up and went to bed.", lock_doors=(home_door,)),
    ]
    return tuple(tasks)


def stroll(start: int, end: int, name: str, route, text: str = None) -> TaskDef:
    return TaskDef(start, end, route[0], AIState.STROLLING, text or f"{name} is out for a stroll.", patrol_points=route)


def visit(start: int, end: int, spot, state: AIState, text: str, facing: float = 0.0, food: str = None) -> TaskDef:
    return TaskDef(start, end, spot, state, text, facing=facing, food_container=food)


# --- the level --------------------------------------------------------------------------------
def build_town_level() -> LevelDefinition:
    walls: List[WallDef] = [
        # perimeter (stone)
        WallDef((-50, 0, -32), (50, 5, -31), texture="wall"),
        WallDef((-50, 0, 31), (50, 5, 32), texture="wall"),
        WallDef((-50, 0, -32), (-49, 5, 32), texture="wall"),
        WallDef((49, 0, -32), (50, 5, 32), texture="wall"),
    ]
    walls += WATCHTOWER.walls                                                        # the watchtower behind the guard house
    # north side ------------------------------------------------------------------------------
    walls += house_walls(-46, -15, -38, -6, -43.5, "south")                         # smithy (home of the smith)
    walls += house_walls(-26, -22, -8, -6, -20.0, "south")                          # the inn
    walls += [                                                                       # inn: guest rooms along the north
        WallDef((-21.5, 0, -22), (-21.2, 4, -16.5)),
        WallDef((-17.0, 0, -22), (-16.7, 4, -16.5)),
        WallDef((-12.5, 0, -22), (-12.2, 4, -16.5)),
        WallDef((-25.5, 0, -16.8), (-23.2, 4, -16.5)), WallDef((-21.6, 0, -16.8), (-21.2, 4, -16.5)),    # keeper's room door 23.2..21.6
        WallDef((-21.2, 0, -16.8), (-20.1, 4, -16.5)), WallDef((-18.5, 0, -16.8), (-16.7, 4, -16.5)),    # room 1 door 20.1..18.5
        WallDef((-16.7, 0, -16.8), (-15.6, 4, -16.5)), WallDef((-14.0, 0, -16.8), (-12.2, 4, -16.5)),    # room 2 door 15.6..14.0
        WallDef((-12.2, 0, -16.8), (-11.1, 4, -16.5)), WallDef((-9.5, 0, -16.8), (-8.5, 4, -16.5)),      # room 3 door 11.1..9.5
    ]
    walls += house_walls(-4, -16, 8, -6, -1.0, "south")                             # general store
    walls += house_walls(11, -14, 21, -6, 14.0, "south")                            # the tailor
    # guard house; its north wall stops where the tower's own (taller, with the door in it) takes over
    walls += house_walls(30, -16, 42, -6, 35.5, "south", texture="wall", door_x2=TOWER_X1, door_width2=TOWER_X2 - TOWER_X1)
    # south side ------------------------------------------------------------------------------
    walls += house_walls(-44, 7, -36, 15, -41.5, "north")                           # Barnaby's house
    walls += house_walls(-34, 6, -27, 13, -31.0, "north")                           # Tamsin's cottage
    walls += house_walls(-23, 7.5, -13, 17, -19.5, "north")                         # the hideout (Raz)
    walls += house_walls(-10, 6, -2, 13, -7.5, "north")                             # Fenwick's cottage
    walls += house_walls(2, 7, 11, 16, 5.0, "north")                                # Lys & Dorran
    walls += house_walls(14, 6, 21, 13, 16.0, "north")                              # Pell's cottage
    walls += house_walls(32, 6, 42, 16, 35.5, "north", texture="wall")              # jail
    walls += [                                                                       # jail: the barred cell in the east
        # (the gate's open leaf folds north along x = 38 for 3 units, so the strip between the cell and
        # the jail's north wall is kept wide enough to walk around it)
        WallDef((37.0, 0, 11.5), (37.5, 4, 15.5), texture="wall"),                  # cell west wall
        WallDef((37.0, 0, 11.5), (38.0, 4, 12.0), texture="wall"),                  # cell north wall stubs; bars gap 38..41
        WallDef((41.0, 0, 11.5), (41.5, 4, 12.0), texture="wall"),
    ]
    # the smith's shed: a roof on four posts
    walls += [WallDef((x, 0, z), (x + 0.3, 4, z + 0.3)) for x, z in ((-37.0, -14.0), (-30.3, -14.0), (-37.0, -6.3), (-30.3, -6.3))]

    buildings = (
        BuildingDef("smithy", (-46.0, -15.0), (-38.0, -6.0)),
        BuildingDef("smithy_shed", (-37.0, -14.0), (-30.0, -6.0), roof_texture="roof_slate", open_sides=True),
        BuildingDef("inn", (-26.0, -22.0), (-8.0, -6.0)),
        BuildingDef("shop", (-4.0, -16.0), (8.0, -6.0)),
        BuildingDef("tailor", (11.0, -14.0), (21.0, -6.0)),
        BuildingDef("guard_house", (30.0, -16.0), (42.0, -6.0), roof_texture="roof_slate"),
        BuildingDef("watchtower", (TOWER_X1, TOWER_Z1), (TOWER_X2, TOWER_Z2), wall_height=WATCHTOWER.wall_top, floor_texture="stone",
                    open_top=True),
        BuildingDef("barnaby_house", (-44.0, 7.0), (-36.0, 15.0)),
        BuildingDef("tamsin_house", (-34.0, 6.0), (-27.0, 13.0)),
        BuildingDef("hideout", (-23.0, 7.5), (-13.0, 17.0)),
        BuildingDef("fenwick_house", (-10.0, 6.0), (-2.0, 13.0)),
        BuildingDef("couple_house", (2.0, 7.0), (11.0, 16.0)),
        BuildingDef("pell_house", (14.0, 6.0), (21.0, 13.0)),
        BuildingDef("jail", (32.0, 6.0), (42.0, 16.0), roof_texture="roof_slate"),
    )

    roads = (
        RoadDef((-48.5, STREET_NORTH), (48.5, STREET_SOUTH)),                      # main street
        RoadDef((-37.5, -14.5), (-29.5, STREET_NORTH)),                             # the smith's yard under the shed
        RoadDef((-36.5, -22.0), (-32.5, -14.5)),                                    # path to the ore deposit
    )

    props = (
        PropDef("well", (-1.3, 0, -1.3), (1.3, 1.0, 1.3), texture="wall", kind="well"),
        # smithy
        bed("smith_bed", SMITH_BED),
        PropDef("forge", (-33.5, 0, -11.2), (-31.7, 1.0, -9.9), texture="stone", kind="forge", facing=180.0),   # mouth to the south
        # inn
        PropDef("inn_bar", (-26.0 + WALL, 0, -11.8), (-21.0, 1.0, -11.2), texture="wood"),      # the bar; staff pass at its east end
        PropDef("inn_oven", (-25.5, 0, -16.3), (-23.7, 1.5, -14.7), texture="stone", kind="oven", facing=180.0),   # mouth to the south
        # shop signs hung beside the doors (bracketed to the wall, the board standing out from it)
        PropDef("sign_smith", (-40.1, 2.3, -5.7), (-39.3, 3.1, -4.9), texture="sign_smith", kind="sign", facing=270.0, solid=False),
        PropDef("sign_inn", (-16.6, 2.3, -5.7), (-15.8, 3.1, -4.9), texture="sign_inn", kind="sign", facing=270.0, solid=False),
        PropDef("sign_store", (2.4, 2.3, -5.7), (3.2, 3.1, -4.9), texture="sign_store", kind="sign", facing=270.0, solid=False),
        PropDef("sign_tailor", (17.4, 2.3, -5.7), (18.2, 3.1, -4.9), texture="sign_tailor", kind="sign", facing=270.0, solid=False),
        bed("inn_keeper_bed", INN_KEEPER_BED),
        bed("inn_room_1_bed", INN_ROOM_BEDS[0]),
        bed("inn_room_2_bed", INN_ROOM_BEDS[1]),
        bed("inn_room_3_bed", INN_ROOM_BEDS[2]),
        # general store
        PropDef("shop_counter", (-2.0, 0, -11.2), (4.0, 1.0, -10.6), texture="wall"),
        PropDef("shop_table", (5.5, 0, -13.6), (7.0, 0.8, -12.1)),
        # tailor
        PropDef("tailor_counter", (13.0, 0, -10.2), (18.0, 1.0, -9.6), texture="wall"),
        bed("tailor_bed", TAILOR_BED),
        # guard house & jail
        bed("guard_bed_1", GUARD_BEDS[0]), bed("guard_bed_2", GUARD_BEDS[1]), bed("guard_bed_3", GUARD_BEDS[2]),
        bed("guard_bed_4", GUARD_BEDS[3], along_x=True),
        *WATCHTOWER.props,
        bed("jail_guard_bed", JAIL_GUARD_BED),
        bed("jail_cell_bed", JAIL_CELL_BED),
        # homes
        bed("barnaby_bed", BARNABY_BED),
        bed("tamsin_bed", TAMSIN_BED),
        bed("raz_bed", RAZ_BED),
        bed("fenwick_bed", FENWICK_BED),
        bed("lys_bed", LYS_BED), bed("dorran_bed", DORRAN_BED),
        bed("pell_bed", PELL_BED),
    )

    stew = lambda n: ItemDef("stew", "Pot of Stew", value=4.0, stackable=True, quantity=n, is_food=True, category="food")  # noqa: E731
    bread = lambda n: ItemDef("bread", "Fresh Bread", value=3.0, stackable=True, quantity=n, is_food=True, category="food")  # noqa: E731
    ale = lambda n: ItemDef("ale", "Mug of Ale", value=3.0, stackable=True, quantity=n, is_food=True, category="food")  # noqa: E731

    containers = (
        # general store
        ContainerDef("shop_shelf_west", "Shop Shelf", (-3.5, 0, -15.5), (-0.5, 1.8, -14.7), owner="Shopkeeper Barnaby",
                     crime_name="Shoplifting",
                     items=(ItemDef("candlestick", "Silver Candlestick", value=45.0),
                            ItemDef("wine", "Bottle of Wine", value=12.0, stackable=True, quantity=3, category="food"),
                            ItemDef("thread", "Spool of Silk Thread", value=4.0, stackable=True, quantity=5))),
        ContainerDef("shop_shelf_east", "Shop Shelf", (4.5, 0, -15.5), (7.5, 1.8, -14.7), owner="Shopkeeper Barnaby",
                     crime_name="Shoplifting",
                     items=(ItemDef("lantern", "Brass Lantern", value=30.0),
                            ItemDef("honey", "Jar of Honey", value=9.0, stackable=True, quantity=2, category="food"),
                            ItemDef("plate", "Pewter Plate", value=18.0),
                            ItemDef("pickaxe", "Pickaxe", value=35.0, category="tool"),
                            ItemDef("mallet", "Mallet", value=12.0, category="tool"))),
        # smithy: the rack under the shed and the smith's own chest
        ContainerDef("smithy_rack", "Weapon Rack", (-36.4, 0, -13.9), (-33.2, 1.8, -13.2), owner="Gareth the Smith",
                     crime_name="Theft", texture="shelf",
                     items=(ItemDef("iron_dagger", "Iron Dagger", value=40.0, category="weapon"),
                            ItemDef("short_sword", "Short Sword", value=90.0, category="weapon"),
                            ItemDef("leather_cap", "Leather Cap", value=25.0, category="armor"),
                            ItemDef("iron_helm", "Iron Helm", value=70.0, category="armor"),
                            ItemDef("chain_shirt", "Chain Shirt", value=150.0, category="armor", noise_modifier=0.15),
                            ItemDef("iron_ore", "Iron Ore", value=6.0, stackable=True, quantity=4, category="ore"),
                            ItemDef("mallet", "Mallet", value=12.0, category="tool"))),
        table("smith_table", "Kitchen Table", (-40.2, 0.0, -9.6), items=[stew(14)], owner="Gareth the Smith"),
        # the tailor's rack
        ContainerDef("tailor_rack", "Clothes Rack", (12.0, 0, -13.5), (16.0, 1.8, -12.7), owner="Mirelle the Tailor",
                     crime_name="Shoplifting", texture="shelf",
                     items=(ItemDef("wool_cloak", "Wool Cloak", value=35.0, category="clothing", noise_modifier=-0.05),
                            ItemDef("silk_gloves", "Silk Gloves", value=60.0, category="clothing", noise_modifier=-0.1),
                            ItemDef("soft_slippers", "Soft Slippers", value=45.0, category="clothing", noise_modifier=-0.1),
                            ItemDef("needles", "Steel Needles", value=6.0, stackable=True, quantity=3, category="tool"))),
        table("tailor_table_food", "Side Table", (18.5, 0.0, -7.6), items=[bread(11)], owner="Mirelle the Tailor"),
        # the inn: kitchen table and three dining tables
        table("inn_kitchen_table", "Kitchen Table", (-23.5, 0.0, -13.5), items=[stew(12), bread(10), ale(12)],
              owner="Hilde the Innkeeper"),
        table("inn_table_1", "Inn Table", INN_TABLES[0], items=[ale(3)], owner="Hilde the Innkeeper"),
        table("inn_table_2", "Inn Table", INN_TABLES[1], items=[ale(3)], owner="Hilde the Innkeeper"),
        table("inn_table_3", "Inn Table", INN_TABLES[2], items=[bread(2)], owner="Hilde the Innkeeper"),
        # homes
        table("barnaby_table", "Kitchen Table", (-41.5, 0.0, 10.4), items=[stew(8)], owner="Shopkeeper Barnaby"),
        table("tamsin_table", "Kitchen Table", (-28.25, 0.0, 8.6), items=[stew(14)], owner="Tamsin"),
        table("raz_table", "Table", (-20.0, 0.0, 9.5), owner="Raz the Fence",
              items=[ItemDef("dried_meat", "Dried Meat", value=5.0, stackable=True, quantity=8, is_food=True, category="food")]),
        table("fenwick_table", "Kitchen Table", (-3.75, 0.0, 8.5), items=[stew(11)], owner="Fenwick"),
        table("couple_table", "Kitchen Table", (4.0, 0.0, 11.6), items=[stew(24)], owner="Lys", size=(0.75, 0.9)),
        table("pell_table", "Kitchen Table", (15.5, 0.0, 8.6), items=[bread(11)], owner="Pell"),
        # guards
        table("guard_table", "Guard Table", (38.5, 0.0, -10.5), owner="guards", size=(1.5, 1.2),
              items=[ItemDef("ration", "Guard's Ration", value=3.0, stackable=True, quantity=16, is_food=True, category="food")]),
        # the confiscation lockbox: the cell key opens it too; unlocked for a released prisoner
        ContainerDef("jail_storage", "Confiscation Lockbox", (32.8, 0, 13.5), (34.3, 1.0, 15.0), owner="guards",
                     texture="lockbox", kind="lockbox", locked=True, lock_difficulty=3, key_id="cell_door"),
    )

    stations = (
        StationDef("ore_deposit", "Ore Deposit", (-36.0, 0, -21.0), (-33.0, 1.6, -18.0), texture="ore",
                   yields=ItemDef("iron_ore", "Iron Ore", value=6.0, stackable=True, category="ore"),
                   requires_item_id="pickaxe", tool_label="a pickaxe", xp=10.0),
        StationDef("anvil", "Anvil", (-34.5, 0, -9.4), (-33.5, 0.8, -8.6), texture="stone",
                   consumes=("iron_ore", 1), consumes_label="1 Iron Ore", requires_item_id="mallet", tool_label="a mallet",
                   produces=ItemDef("iron_lockpick", "Iron Lockpick", value=5.0, is_lockpick=True, stackable=True, quantity=3,
                                    category="tool"),
                   xp=40.0),
    )

    areas = (
        # merchants (north)
        AreaDef("the smithy", (-46.0, -15.0), (-38.0, -6.0), owner="Gareth the Smith", restricted=True),
        AreaDef("the smith's yard", (-37.5, -14.5), (-29.5, -6.0), owner="Gareth the Smith"),
        AreaDef("the inn kitchen", (-26.0, -16.5), (-21.2, -11.0), owner="Hilde the Innkeeper", restricted=True),   # behind the bar
        AreaDef("the keeper's room", (-26.0, -22.0), (-21.5, -16.5), owner="Hilde the Innkeeper", restricted=True),
        AreaDef("room one", (-21.5, -22.0), (-17.0, -16.5), owner="Hilde the Innkeeper", restricted=True),
        AreaDef("room two", (-17.0, -22.0), (-12.5, -16.5), owner="Hilde the Innkeeper", restricted=True),
        AreaDef("room three", (-12.5, -22.0), (-8.0, -16.5), owner="Hilde the Innkeeper", restricted=True),
        AreaDef("the inn", (-26.0, -22.0), (-8.0, -6.0), owner="Hilde the Innkeeper", restricted=True,
                public_hours=(INN_OPEN_HOUR, INN_CLOSE_HOUR)),
        AreaDef("behind the counter", (-4.0, -16.0), (8.0, -10.6), owner="Shopkeeper Barnaby", restricted=True),
        AreaDef("the shop", (-4.0, -10.6), (8.0, -6.0), owner="Shopkeeper Barnaby", restricted=True,
                public_hours=(SHOP_OPEN_HOUR, SHOP_CLOSE_HOUR)),
        AreaDef("the tailor's back room", (11.0, -14.0), (21.0, -9.6), owner="Mirelle the Tailor", restricted=True),
        AreaDef("the tailor's", (11.0, -9.6), (21.0, -6.0), owner="Mirelle the Tailor", restricted=True,
                public_hours=(TAILOR_OPEN_HOUR, TAILOR_CLOSE_HOUR)),
        AreaDef("the watchtower", (TOWER_X1, TOWER_Z1), (TOWER_X2, TOWER_Z2), owner="guards", restricted=True),
        AreaDef("the guard house", (30.0, -16.0), (42.0, -6.0), owner="guards", restricted=True),
        # homes (south)
        AreaDef("Barnaby's house", (-44.0, 7.0), (-36.0, 15.0), owner="Shopkeeper Barnaby", restricted=True),
        AreaDef("Tamsin's cottage", (-34.0, 6.0), (-27.0, 13.0), owner="Tamsin", restricted=True),
        AreaDef("the hideout", (-23.0, 7.5), (-13.0, 17.0), owner="Raz the Fence", restricted=True,
                trusted_by=("Raz the Fence",), curfew_hours=(22, 6)),
        AreaDef("Fenwick's cottage", (-10.0, 6.0), (-2.0, 13.0), owner="Fenwick", restricted=True),
        AreaDef("Lys and Dorran's house", (2.0, 7.0), (11.0, 16.0), owner="Lys", restricted=True),
        AreaDef("Pell's cottage", (14.0, 6.0), (21.0, 13.0), owner="Pell", restricted=True),
        AreaDef("the jail cell", (37.0, 11.5), (42.0, 16.0), owner="guards", restricted=True),
        AreaDef("the jail", (32.0, 6.0), (42.0, 16.0), owner="guards"),
        AreaDef("the well", (-6.0, -6.0), (6.0, 6.0)),
        AreaDef("main street", (-48.5, -6.0), (48.5, 6.0)),
    )

    doors = (
        # north side: hinges on the south walls, leaves swing into the buildings
        DoorDef("smithy_door", (-43.5, 0.0, -6.0), is_locked=True, key_id="smithy_door_key", owners=("Gareth the Smith",), lock_difficulty=2),
        DoorDef("inn_door", (-20.0, 0.0, -6.0), is_locked=False, key_id="inn_door_key", owners=("Hilde the Innkeeper",), lock_difficulty=2),
        DoorDef("keeper_room_door", (-23.2, 0.0, -16.5), is_locked=True, key_id="keeper_room_door_key", width=1.6,
                owners=("Hilde the Innkeeper",), lock_difficulty=2),
        DoorDef("inn_room_1_door", (-20.1, 0.0, -16.5), is_locked=True, key_id="inn_room_1_door_key", width=1.6,
                owners=("Hilde the Innkeeper",), lock_difficulty=2),
        DoorDef("inn_room_2_door", (-15.6, 0.0, -16.5), is_locked=True, key_id="inn_room_2_door_key", width=1.6,
                owners=("Hilde the Innkeeper",), lock_difficulty=2),
        DoorDef("inn_room_3_door", (-11.1, 0.0, -16.5), is_locked=True, key_id="inn_room_3_door_key", width=1.6,
                owners=("Hilde the Innkeeper",), lock_difficulty=2),
        DoorDef("shop_door", (-1.0, 0.0, -6.0), is_locked=True, key_id="shop_key", owners=("Shopkeeper Barnaby",), lock_difficulty=2),
        DoorDef("tailor_door", (14.0, 0.0, -6.0), is_locked=True, key_id="tailor_door_key", owners=("Mirelle the Tailor",), lock_difficulty=2),
        DoorDef("guardhouse_door", (35.5, 0.0, -6.0), is_locked=True, key_id="guard_key", owners=("guards",), lock_difficulty=3),
        DoorDef("tower_door", (TOWER_DOOR_X, 0.0, -16.0), is_locked=True, key_id="tower_key", owners=("guards",), lock_difficulty=2,
                width=2.0, swing_out=True),           # opens into the guard house: the stair starts right inside
        # south side: hinges on the north walls
        DoorDef("home_door", (-41.5, 0.0, 7.0), is_locked=True, key_id="home_key", owners=("Shopkeeper Barnaby",), lock_difficulty=2),
        DoorDef("tamsin_door", (-31.0, 0.0, 6.0), is_locked=True, key_id="tamsin_door_key", owners=("Tamsin",), lock_difficulty=1),
        DoorDef("hideout_door", (-19.5, 0.0, 7.5), is_locked=False, key_id="hideout_door_key", owners=("Raz the Fence",)),
        DoorDef("fenwick_door", (-7.5, 0.0, 6.0), is_locked=True, key_id="fenwick_door_key", owners=("Fenwick",), lock_difficulty=1),
        DoorDef("couple_door", (5.0, 0.0, 7.0), is_locked=True, key_id="couple_door_key", owners=("Lys", "Dorran"), lock_difficulty=2),
        DoorDef("pell_door", (16.0, 0.0, 6.0), is_locked=True, key_id="pell_door_key", owners=("Pell",), lock_difficulty=1),
        # the jail house is open to all (nobody owns - i.e. locks - its door); the cell is a barred gate
        DoorDef("jail_door", (35.5, 0.0, 6.0), is_locked=False, key_id="guard_key", lock_difficulty=3),
        DoorDef("cell_door", (38.0, 0.0, 12.0), is_locked=True, key_id="cell_key", owners=("guards",), lock_difficulty=3,
                kind=DoorKind.BARS),
    )

    stock_tiers = (
        StockTier(2, (ItemDef("fine_lockpick", "Fine Steel Lockpick", value=15.0, is_lockpick=True, stackable=True, quantity=3,
                              category="tool"),), container="shop_shelf_east"),
        StockTier(4, (ItemDef("jeweled_dagger", "Jeweled Dagger", value=180.0, category="weapon"),), container="shop_shelf_west"),
        StockTier(6, (ItemDef("ruby_necklace", "Ruby Necklace", value=320.0),), container="shop_shelf_east"),
    )
    tailor_tiers = (
        StockTier(3, (ItemDef("velvet_cloak", "Velvet Cloak", value=140.0, noise_modifier=-0.15, category="clothing"),),
                  container="tailor_rack"),
        StockTier(6, (ItemDef("shadow_boots", "Shadow Boots", value=260.0, noise_modifier=-0.2, category="clothing"),),
                  container="tailor_rack"),
    )
    smith_tiers = (
        StockTier(3, (ItemDef("steel_sword", "Steel Sword", value=220.0, category="weapon"),), container="smithy_rack"),
        StockTier(5, (ItemDef("plate_cuirass", "Plate Cuirass", value=400.0, category="armor", noise_modifier=0.3),),
                  container="smithy_rack"),
    )

    npcs = (
        # ---- merchants -------------------------------------------------------------------------
        NPCDef(
            "Shopkeeper Barnaby", BARNABY_BED, can_trade=True, role="shopkeeper",
            shop_containers=("shop_shelf_west", "shop_shelf_east"), restock_days=3, restock_tiers=stock_tiers,
            inventory_reset_days=3, gold=SHOPKEEPER_GOLD,
            inventory=(
                ItemDef("shop_key", "Store Backroom Key", value=1.0, is_key=True, key_door_id="shop_door", for_sale=False, category="key"),
                ItemDef("home_key", "Barnaby's House Key", value=1.0, is_key=True, key_door_id="home_door", for_sale=False, category="key"),
                ItemDef("bread_1", "Fresh Bread", value=15.0, stackable=True, quantity=4, is_food=True, category="food"),
                ItemDef("apple_1", "Crisp Apple", value=8.0, stackable=True, quantity=6, is_food=True, category="food"),
                ItemDef("torch_item", "Portable Torch", value=25.0, category="tool"),
            ),
            schedule=resident_tasks("Barnaby", "home_door", BARNABY_BED, BARNABY_TABLE_SEAT, "barnaby_table", [
                TaskDef(SHOP_OPEN_HOUR, SHOP_LUNCH_HOUR, SHOP_COUNTER, AIState.SHOPKEEPING,
                        "Barnaby opened the shop for business.", unlock_doors=("shop_door",),
                        depart_text="Time to open up the shop.", facing=180.0),
                TaskDef(SHOP_LUNCH_HOUR, SHOP_LUNCH_HOUR + 1, SHOP_BACKROOM, AIState.EATING,
                        "Barnaby is having lunch in the back room.", facing=90.0),
                TaskDef(SHOP_LUNCH_HOUR + 1, SHOP_CLOSE_HOUR, SHOP_COUNTER, AIState.SHOPKEEPING,
                        "Barnaby is back behind the counter.", facing=180.0),
            ], wake=7, bedtime=21),
        ),
        NPCDef(
            "Hilde the Innkeeper", INN_KEEPER_BED, can_trade=True, role="innkeeper",
            shop_containers=("inn_kitchen_table",), restock_days=3, inventory_reset_days=1, gold=INNKEEPER_GOLD,
            inventory=(
                key_item("inn_door", "Inn Key"), key_item("keeper_room_door", "Keeper's Room Key"),
                key_item("inn_room_1_door", "Room One Key"), key_item("inn_room_2_door", "Room Two Key"),
                key_item("inn_room_3_door", "Room Three Key"),
                ItemDef("rent_night", "A Room for the Night", value=10.0, category="service"),
                ItemDef("rent_week", "A Room for the Week", value=50.0, category="service"),
                ItemDef("candle_stub", "Tallow Candle", value=2.0, stackable=True, quantity=6),
                ItemDef("soap", "Lye Soap", value=4.0, stackable=True, quantity=3),
            ),
            schedule=(
                TaskDef(0, 5, INN_KEEPER_BED, AIState.SLEEPING, "Hilde is asleep in the room behind the bar.",
                        lock_doors=("keeper_room_door",)),
                TaskDef(5, 6, INN_KITCHEN, AIState.WORKING, "Hilde is lighting the stove and setting the kitchen to rights.",
                        unlock_doors=("keeper_room_door",), facing=0.0, depart_text="Up with the lark. Bread won't bake itself."),
                TaskDef(6, 10, INN_BAR, AIState.SHOPKEEPING, "Hilde is behind the bar of the Drowsy Dragon.", facing=180.0),
                TaskDef(10, 11, INN_SEATS[0], AIState.CLEANING, "Hilde is wiping down the tables.",
                        patrol_points=(INN_SEATS[0], INN_SEATS[2], INN_SEATS[1])),
                TaskDef(11, 15, INN_BAR, AIState.SHOPKEEPING, "Hilde is back behind the bar.", facing=180.0),
                TaskDef(15, 16, INN_SEATS[1], AIState.CLEANING, "Hilde is clearing the tables.",
                        patrol_points=(INN_SEATS[1], INN_SEATS[2], INN_SEATS[0])),
                TaskDef(16, 20, INN_BAR, AIState.SHOPKEEPING, "Hilde is pouring for the evening crowd.", facing=180.0),
                TaskDef(20, 21, INN_SEATS[2], AIState.CLEANING, "Hilde is sweeping around the tables.",
                        patrol_points=(INN_SEATS[2], INN_SEATS[0], INN_SEATS[1])),
                TaskDef(21, 24, INN_BAR, AIState.SHOPKEEPING, "Hilde keeps the bar open for the late crowd.", facing=180.0),
            ),
        ),
        NPCDef(
            "Gareth the Smith", SMITH_BED, can_trade=True, role="smith", trade_categories=("weapon", "armor", "ore", "tool"),
            shop_containers=("smithy_rack",), restock_days=3, restock_tiers=smith_tiers, inventory_reset_days=3, gold=SMITH_GOLD,
            inventory=(key_item("smithy_door", "Smithy Key"),
                       ItemDef("hammer", "Smith's Hammer", value=20.0, for_sale=False, category="tool"),
                       ItemDef("mallet", "Mallet", value=12.0, for_sale=False, category="tool"),
                       ItemDef("pickaxe", "Pickaxe", value=35.0, for_sale=False, category="tool")),
            schedule=resident_tasks("Gareth", "smithy_door", SMITH_BED, SMITH_TABLE_SEAT, "smith_table", [
                TaskDef(8, 12, ANVIL_SPOT, AIState.WORKING, "Gareth is hammering at the anvil.", facing=0.0,
                        depart_text="Right. Iron won't shape itself."),
                TaskDef(12, 13, SMITH_TABLE_SEAT, AIState.EATING, "Gareth is eating at his table.", facing=0.0,
                        food_container="smith_table"),
                TaskDef(13, 16, FORGE_SPOT, AIState.WORKING, "Gareth is working the forge.", facing=0.0),
                TaskDef(16, 18, ANVIL_SPOT, AIState.WORKING, "Gareth is back at the anvil.", facing=0.0),
                TaskDef(18, 19, SMITH_TABLE_SEAT, AIState.EATING, "Gareth is having supper.", facing=0.0, food_container="smith_table"),
                visit(19, 20, INN_SEATS[3], AIState.DRINKING, "Gareth is having an ale at the Drowsy Dragon.", facing=270.0),
            ], wake=7, bedtime=21),
        ),
        NPCDef(
            "Mirelle the Tailor", TAILOR_BED, can_trade=True, role="tailor", trade_categories=("clothing", "tool"),
            shop_containers=("tailor_rack",), restock_days=3, restock_tiers=tailor_tiers, inventory_reset_days=3, gold=TAILOR_GOLD,
            inventory=(key_item("tailor_door", "Tailor's Key"),
                       ItemDef("thimble", "Silver Thimble", value=12.0, category="tool")),
            schedule=(
                TaskDef(0, 8, TAILOR_BED, AIState.SLEEPING, "Mirelle is asleep in her back room.", lock_doors=("tailor_door",)),
                TaskDef(8, TAILOR_OPEN_HOUR, TAILOR_TABLE_SEAT, AIState.EATING, "Mirelle is having breakfast.", facing=90.0,
                        food_container="tailor_table_food"),
                TaskDef(TAILOR_OPEN_HOUR, 13, TAILOR_COUNTER, AIState.SHOPKEEPING, "Mirelle opened the tailor's shop.",
                        unlock_doors=("tailor_door",), facing=180.0),
                TaskDef(13, 14, TAILOR_TABLE_SEAT, AIState.EATING, "Mirelle is having lunch.", facing=90.0, food_container="tailor_table_food"),
                TaskDef(14, TAILOR_CLOSE_HOUR, TAILOR_COUNTER, AIState.SHOPKEEPING, "Mirelle is back at her counter.", facing=180.0),
                stroll(TAILOR_CLOSE_HOUR, 19, "Mirelle", STROLL_EAST, "Mirelle is stretching her legs after a day's sewing."),
                visit(19, 20, INN_SEATS[4], AIState.DRINKING, "Mirelle is taking a cup of wine at the inn.", facing=270.0),
                TaskDef(20, 21, TAILOR_TABLE_SEAT, AIState.EATING, "Mirelle is having a late supper.", facing=90.0,
                        food_container="tailor_table_food"),
                TaskDef(21, 24, TAILOR_BED, AIState.SLEEPING, "Mirelle locked up and went to bed.", lock_doors=("tailor_door",)),
            ),
        ),
        NPCDef(
            "Raz the Fence", RAZ_DEN, is_fence=True, can_trade=True, inventory_reset_days=3, gold=FENCE_GOLD, role="fence",
            inventory=(
                key_item("hideout_door", "Hideout Key"),
                ItemDef("lockpick_pack", "Master Lockpick", value=20.0, is_lockpick=True, stackable=True, quantity=3, category="tool"),
                ItemDef("gold_ring", "Gold Ring", value=150.0),
                ItemDef("dried_meat", "Dried Meat", value=5.0, stackable=True, quantity=4, is_food=True, for_sale=False, category="food"),
            ),
            schedule=(
                TaskDef(0, 6, RAZ_BED, AIState.SLEEPING, "Raz is asleep in the hideout."),
                TaskDef(6, 7, RAZ_TABLE_SEAT, AIState.EATING, "Raz is eating at his table.", facing=0.0, food_container="raz_table"),
                TaskDef(7, 22, RAZ_DEN, AIState.SHOPKEEPING, "Raz is in his den, ready to deal in stolen goods.", facing=0.0),
                TaskDef(22, 23, RAZ_TABLE_SEAT, AIState.EATING, "Raz is having a late supper.", facing=0.0,
                        food_container="raz_table"),
                TaskDef(23, 24, RAZ_BED, AIState.SLEEPING, "Raz turned in for the night."),
            ),
        ),
        # ---- townsfolk -------------------------------------------------------------------------
        NPCDef(
            "Tamsin", TAMSIN_BED, role="widow", gold=TOWNSFOLK_GOLD, inventory_reset_days=3,
            inventory=(key_item("tamsin_door", "Cottage Key"), ItemDef("locket", "Silver Locket", value=55.0, for_sale=False)),
            schedule=resident_tasks("Tamsin", "tamsin_door", TAMSIN_BED, TAMSIN_TABLE_SEAT, "tamsin_table", [
                stroll(8, 10, "Tamsin", STROLL_WEST),
                visit(10, 11, SHOP_FLOOR, AIState.SHOPPING, "Tamsin is picking over Barnaby's shelves."),
                TaskDef(11, 13, TAMSIN_TABLE_SEAT, AIState.EATING, "Tamsin is having a bite at home.", unlock_doors=("tamsin_door",),
                        facing=0.0, food_container="tamsin_table"),
                stroll(13, 15, "Tamsin", STROLL_EAST, "Tamsin is taking the afternoon air."),
                visit(15, 16, TAILOR_FLOOR, AIState.SHOPPING, "Tamsin is admiring Mirelle's cloth."),
                visit(16, 18, INN_SEATS[4], AIState.DRINKING, "Tamsin is sharing gossip over a cup at the inn.", facing=270.0),
                TaskDef(18, 20, TAMSIN_TABLE_SEAT, AIState.EATING, "Tamsin is home for the evening.", unlock_doors=("tamsin_door",),
                        facing=0.0, food_container="tamsin_table"),
            ], wake=7, bedtime=21),
        ),
        NPCDef(
            "Fenwick", FENWICK_BED, role="elder", gold=TOWNSFOLK_GOLD, inventory_reset_days=3,
            inventory=(key_item("fenwick_door", "Cottage Key"), ItemDef("pipe", "Clay Pipe", value=9.0, for_sale=False)),
            schedule=resident_tasks("Fenwick", "fenwick_door", FENWICK_BED, FENWICK_TABLE_SEAT, "fenwick_table", [
                visit(9, 12, INN_SEATS[2], AIState.DRINKING, "Fenwick has his usual seat at the Drowsy Dragon.", facing=90.0),
                stroll(12, 14, "Fenwick", STROLL_WEST, "Fenwick is walking off his ale."),
                TaskDef(14, 15, FENWICK_TABLE_SEAT, AIState.EATING, "Fenwick is having a bite at home.", unlock_doors=("fenwick_door",),
                        facing=0.0, food_container="fenwick_table"),
                stroll(15, 18, "Fenwick", STROLL_EAST, "Fenwick is ambling along the street."),
                visit(18, 20, INN_SEATS[2], AIState.DRINKING, "Fenwick is back at the inn for the evening.", facing=90.0),
            ], wake=8, bedtime=21),
        ),
        NPCDef(
            "Lys", LYS_BED, role="cook", gold=TOWNSFOLK_GOLD, inventory_reset_days=3,
            inventory=(key_item("couple_door", "House Key"), ItemDef("ladle", "Wooden Ladle", value=3.0, for_sale=False)),
            schedule=resident_tasks("Lys", "couple_door", LYS_BED, COUPLE_TABLE_SEATS[0], "couple_table", [
                TaskDef(8, 14, INN_KITCHEN, AIState.WORKING, "Lys is helping in the inn kitchen.", facing=270.0,
                        depart_text="Off to the inn - Hilde will want the pots on."),
                visit(14, 15, SHOP_FLOOR, AIState.SHOPPING, "Lys is buying provisions at the store."),
                stroll(15, 17, "Lys", STROLL_EAST, "Lys is enjoying a walk in the afternoon sun."),
                TaskDef(17, 20, COUPLE_TABLE_SEATS[0], AIState.EATING, "Lys is cooking supper at home.", unlock_doors=("couple_door",),
                        facing=0.0, food_container="couple_table"),
            ], wake=7, bedtime=21),
        ),
        NPCDef(
            "Dorran", DORRAN_BED, role="porter", gold=TOWNSFOLK_GOLD, inventory_reset_days=3,
            inventory=(key_item("couple_door", "House Key"), ItemDef("whetstone", "Whetstone", value=6.0, for_sale=False)),
            schedule=resident_tasks("Dorran", "couple_door", DORRAN_BED, COUPLE_TABLE_SEATS[1], "couple_table", facing=270.0, day=[
                TaskDef(8, 12, SHOP_PORTER, AIState.WORKING, "Dorran is hauling crates for Barnaby.", facing=270.0,
                        depart_text="Barnaby's crates won't carry themselves."),
                TaskDef(12, 13, COUPLE_TABLE_SEATS[1], AIState.EATING, "Dorran is home for his midday meal.", unlock_doors=("couple_door",),
                        facing=270.0, food_container="couple_table"),
                TaskDef(13, 17, SHOP_PORTER, AIState.WORKING, "Dorran is back at work in the store.", facing=270.0),
                visit(17, 19, INN_SEATS[3], AIState.DRINKING, "Dorran is having an ale after work.", facing=270.0),
                TaskDef(19, 20, COUPLE_TABLE_SEATS[1], AIState.EATING, "Dorran is home for supper.", unlock_doors=("couple_door",),
                        facing=270.0, food_container="couple_table"),
            ], wake=7, bedtime=21),
        ),
        NPCDef(
            "Pell", PELL_BED, role="lad", gold=TOWNSFOLK_GOLD, inventory_reset_days=3,
            inventory=(key_item("pell_door", "Cottage Key"), ItemDef("sling", "Leather Sling", value=7.0, for_sale=False, category="weapon")),
            schedule=resident_tasks("Pell", "pell_door", PELL_BED, PELL_TABLE_SEAT, "pell_table", [
                stroll(8, 11, "Pell", STROLL_EAST, "Pell is kicking about the street."),
                visit(11, 12, TAILOR_FLOOR, AIState.SHOPPING, "Pell is eyeing a new cloak he cannot afford."),
                TaskDef(12, 13, PELL_TABLE_SEAT, AIState.EATING, "Pell is home for a bite.", unlock_doors=("pell_door",),
                        facing=0.0, food_container="pell_table"),
                stroll(13, 17, "Pell", STROLL_WEST, "Pell is wandering down to the smithy and back."),
                visit(17, 20, INN_SEATS[5], AIState.DRINKING, "Pell is nursing a small ale at the inn.", facing=270.0),
            ], wake=7, bedtime=21),
        ),
        # ---- the watch -------------------------------------------------------------------------
        guard("Guard Captain Vance", patrol=(6, 14), meal=(14, 15), post=(15, 22), post_spot=POST_WEST, post_facing=90.0,
              sleep=(22, 6), bed_spot=GUARD_BEDS[0], meal_seat=GUARD_TABLE_SEATS[0]),
        # the tower watch: up the winding stair at dawn, down for a meal, back up until bedtime
        NPCDef(
            "Guard Aldric", GUARD_BEDS[3], is_guard=True, inventory=(GUARD_KEY, TOWER_KEY, RATIONS), inventory_reset_days=1, gold=GUARD_GOLD,
            role="guard",
            schedule=(
                TaskDef(0, 6, GUARD_BEDS[3], AIState.SLEEPING, "Guard Aldric is asleep in the guard house."),
                TaskDef(6, 7, GUARD_TABLE_SEATS[1], AIState.EATING, "Guard Aldric is eating at the guard house table.",
                        facing=180.0, food_container="guard_table"),
                TaskDef(7, 14, TOWER_TOP, AIState.GUARDING, "Guard Aldric is on watch at the top of the tower.", facing=225.0,
                        depart_text="Up the tower. Forty steps, every morning."),
                TaskDef(14, 15, GUARD_TABLE_SEATS[1], AIState.EATING, "Guard Aldric is eating at the guard house table.",
                        facing=180.0, food_container="guard_table"),
                TaskDef(15, 22, TOWER_TOP, AIState.GUARDING, "Guard Aldric is back on watch up the tower.", facing=225.0),
                TaskDef(22, 24, GUARD_BEDS[3], AIState.SLEEPING, "Guard Aldric is asleep in the guard house."),
            ),
        ),
        guard("Guard Orrin", patrol=(14, 22), meal=(22, 23), post=(6, 14), post_spot=POST_DOOR,
              sleep=(23, 6), bed_spot=GUARD_BEDS[1], meal_seat=GUARD_TABLE_SEATS[1]),
        guard("Guard Mira", patrol=(22, 6), meal=(6, 7), post=(14, 22), post_spot=POST_DOOR,
              sleep=(7, 14), bed_spot=GUARD_BEDS[2], meal_seat=GUARD_TABLE_SEATS[2]),
        NPCDef(
            "Jailer Hesk", JAIL_GUARD_BED, is_guard=True, inventory_reset_days=1, gold=GUARD_GOLD, role="jailer",
            inventory=(GUARD_KEY, ItemDef("cell_key", "Cell Key", value=1.0, is_key=True, key_door_id="cell_door", for_sale=False,
                                          category="key"), RATIONS),
            schedule=(
                TaskDef(0, 6, JAIL_GUARD_BED, AIState.SLEEPING, "Hesk is asleep in the jail office."),
                TaskDef(6, 7, (35.5, 0.0, 8.5), AIState.EATING, "Hesk is having breakfast at the jail.", facing=0.0),
                TaskDef(7, 22, JAIL_POST, AIState.GUARDING, "Hesk is keeping watch over the cells.", facing=135.0),
                TaskDef(22, 24, JAIL_GUARD_BED, AIState.SLEEPING, "Hesk turned in for the night."),
            ),
        ),
    )

    lights = (
        LightDef("fire", (-32.6, 1.1, -10.55), room="the smith's yard", range=9.0),      # the forge's coals
        *WATCHTOWER.lights,
    )

    return LevelDefinition(
        name="town",
        walls=tuple(walls),
        doors=doors,
        npcs=npcs,
        anvil_position=ANVIL_SPOT,
        player_spawn=(-18.0, 0.0, 3.0),
        props=props,
        containers=containers,
        stations=stations,
        areas=areas,
        buildings=buildings,
        roads=roads,
        lights=lights,
        stairs=(WATCHTOWER.stair,),
        jail=JailDef(cell_door_id="cell_door", storage="jail_storage", cell_area="the jail cell", jail_area="the jail",
                     cell_spot=JAIL_CELL_SPOT, jailer="Jailer Hesk", post=JAIL_POST),
        inn=InnDef(keeper="Hilde the Innkeeper", rooms=(
            InnRoomDef("room one", "inn_room_1_door", INN_ROOM_BEDS[0]),
            InnRoomDef("room two", "inn_room_2_door", INN_ROOM_BEDS[1]),
            InnRoomDef("room three", "inn_room_3_door", INN_ROOM_BEDS[2]),
        )),
        bounds=(-50.0, -32.0, 50.0, 32.0),
        ground_half_size=60.0,
        ground_texture_repeat=12.0,
        player_gold=50.0,
        player_inventory=(
            ItemDef("iron_lockpick", "Iron Lockpick", value=5.0, noise_modifier=0.0, is_lockpick=True, stackable=True, category="tool"),
            ItemDef("soft_shoes", "Soft Leather Boots", value=30.0, noise_modifier=-0.05, category="clothing"),
            ItemDef("silver_goblet", "Silver Goblet", value=120.0, is_stolen=True),
        ),
        default_area="the streets",
        intro_message="Tutorial started: Explore merchants, trade wares, and open doors!",
    )
