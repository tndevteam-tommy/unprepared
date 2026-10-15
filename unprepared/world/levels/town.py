"""The starter town: a walled 80x80 square with a shop, the shopkeeper's house,
the player's hideout, a guard house with a watchtower and a jail against the
east wall, and six NPCs.

Layout (x to the right, z downwards; all doors sit on a south wall and swing into -z):

    shop         x  5..15      z -10..0    door hinge (8.5, 0)     counter across the middle, shelves behind it
    house        x 10..18      z  10..18   door hinge (13, 10)
    hideout      x -18.5..-9.5 z 4.5..15.5 door hinge (-14.5, 5)
    guard house  x 30..39      z -8..4     door hinge (33, 4)      3 beds, table; tower x 35..39 z -14..-10
    jail         x 30..39      z 12..22    door hinge (33, 22)     office west (public, never locked),
                                                                 barred cell east (bars hinge (35.5, 18.5))
    anvil (-3, -8)   ore deposit (-36.5, -36.5)   town square (0, 0)   perimeter at +-39..40
"""
from __future__ import annotations

from ...entities import AIState, DoorKind
from ..level import (AreaDef, BuildingDef, ContainerDef, DoorDef, ItemDef, JailDef, LevelDefinition, NPCDef, PropDef,
                     StationDef, StockTier, TaskDef, WallDef)

# Named spots used by schedules
SHOP_COUNTER = (10.0, 0.0, -6.2)
SHOP_BACKROOM = (6.5, 0.0, -5.2)
HOME_BED = (16.5, 0.0, 16.25)
HOME_TABLE = (12.0, 0.0, 13.5)
TOWN_SQUARE = (0.0, 0.0, 0.0)
RAZ_ALLEY = (-12.0, 0.0, 13.0)
RAZ_BED = (-17.05, 0.0, 13.5)
RAZ_TABLE = (-16.5, 0.0, 8.8)
ORE_DEPOSIT = (-36.5, 0.0, -36.5)
ANVIL = (-3.0, 0.0, -8.0)
GUARD_BEDS = ((31.55, 0.0, -6.2), (31.55, 0.0, -3.2), (31.55, 0.0, -0.2))
GUARD_TABLE_SEATS = ((33.8, 0.0, -3.5), (36.2, 0.0, -1.3), (37.0, 0.0, -5.7))
POST_DOOR = (34.5, 0.0, 6.0)       # outside the guard house door, watching the square
POST_TOWER = (37.0, 0.0, -9.0)     # at the foot of the watchtower
JAIL_POST = (33.8, 0.0, 16.5)      # inside the jail office, facing the cell
JAIL_GUARD_BED = (31.55, 0.0, 20.0)
JAIL_CELL_BED = (37.7, 0.0, 14.5)
JAIL_CELL_SPOT = (36.0, 0.0, 16.5)
PATROL_ROUTE = ((0.0, 0.0, 0.0), (10.0, 0.0, 3.0), (14.5, 0.0, 7.0), (20.0, 0.0, 15.0), (34.5, 0.0, 8.0),
                (25.0, 0.0, -15.0), (0.0, 0.0, -15.0), (-13.0, 0.0, 2.0), (-3.0, 0.0, -5.0))

SHOP_OPEN_HOUR, SHOP_LUNCH_HOUR, SHOP_CLOSE_HOUR = 8, 13, 20
GUARD_KEY = ItemDef("guard_key", "Guard House Key", value=1.0, is_key=True, key_door_id="guardhouse_door", for_sale=False)
RATIONS = ItemDef("ration", "Guard's Ration", value=3.0, stackable=True, quantity=2, is_food=True)
GUARD_GOLD, SHOPKEEPER_GOLD, FENCE_GOLD = 15.0, 400.0, 600.0    # a guard's wages vs the traders' buying purses


def guard(name: str, patrol: tuple, meal: tuple, post: tuple, post_spot, sleep: tuple, bed, meal_seat) -> NPCDef:
    """A guard with an 8-hour shift rotation. Each of ``patrol``/``post``/``sleep`` is a
    (start, end) hour range that may wrap past midnight; ``meal`` is a one-hour slot."""
    def span(rng, state, text, pos, **kw):
        start, end = rng
        if start < end:
            return [TaskDef(start, end, pos, state, text, **kw)]
        return [TaskDef(start, 24, pos, state, text, **kw), TaskDef(0, end, pos, state, text, **kw)]

    tasks = []
    tasks += span(patrol, AIState.PATROL, f"{name} is patrolling the town.", PATROL_ROUTE[0],
                  patrol_points=PATROL_ROUTE, depart_text="Time for my rounds.")
    tasks += span(meal, AIState.EATING, f"{name} is eating at the guard house table.", meal_seat, facing=90.0,
                  food_container="guard_table")
    tasks += span(post, AIState.GUARDING, f"{name} is standing guard.", post_spot, facing=270.0)   # facing the town
    tasks += span(sleep, AIState.SLEEPING, f"{name} is asleep in the guard house.", bed)
    return NPCDef(name, bed, is_guard=True, inventory=(GUARD_KEY, RATIONS), schedule=tuple(tasks), inventory_reset_days=1,
                  gold=GUARD_GOLD)


def build_town_level() -> LevelDefinition:
    walls = (
        # Perimeter (stone)
        WallDef((-40, 0, -40), (40, 5, -39), texture="wall"),
        WallDef((-40, 0, 39), (40, 5, 40), texture="wall"),
        WallDef((-40, 0, -40), (-39, 5, 40), texture="wall"),
        WallDef((39, 0, -40), (40, 5, 40), texture="wall"),
        # Shop building
        WallDef((5, 0, -10), (15, 4, -9.5)),
        WallDef((5, 0, -10), (5.5, 4, 0)),
        WallDef((14.5, 0, -10), (15, 4, 0)),
        WallDef((5, 0, -0.5), (8.5, 4, 0)),
        WallDef((11.5, 0, -0.5), (15, 4, 0)),
        # Player hideout
        WallDef((-18, 0, 15), (-10, 4, 15.5)),
        WallDef((-18.5, 0, 5), (-18, 4, 15)),
        WallDef((-10, 0, 5), (-9.5, 4, 15)),
        WallDef((-18, 0, 4.5), (-14.5, 4, 5)),
        WallDef((-11.5, 0, 4.5), (-10, 4, 5)),
        # Barnaby's house
        WallDef((10, 0, 18), (18, 4, 18.5)),
        WallDef((9.5, 0, 10), (10, 4, 18)),
        WallDef((18, 0, 10), (18.5, 4, 18)),
        WallDef((10, 0, 9.5), (13, 4, 10)),
        WallDef((16, 0, 9.5), (18, 4, 10)),
        # Guard house (its east side is the town wall) and the watchtower
        WallDef((30, 0, -8), (39, 4, -7.5), texture="wall"),
        WallDef((30, 0, -8), (30.5, 4, 4), texture="wall"),
        WallDef((30, 0, 3.5), (33, 4, 4), texture="wall"),
        WallDef((36, 0, 3.5), (39, 4, 4), texture="wall"),
        WallDef((35, 0, -14), (39, 10, -10), texture="wall"),
        # Jail: office on the west, barred cell on the east
        WallDef((30, 0, 12), (39, 4, 12.5), texture="wall"),
        WallDef((30, 0, 12), (30.5, 4, 22), texture="wall"),
        WallDef((30, 0, 21.5), (33, 4, 22), texture="wall"),
        WallDef((36, 0, 21.5), (39, 4, 22), texture="wall"),
        WallDef((35, 0, 12.5), (35.5, 4, 18.5), texture="wall"),       # cell west wall (office is x 30.5..35)
        WallDef((38.5, 0, 18), (39, 4, 18.5), texture="wall"),         # cell south wall stub; door gap 35.5..38.5
    )

    buildings = (
        BuildingDef("shop", (5.0, -10.0), (15.0, 0.0)),
        BuildingDef("house", (9.5, 9.5), (18.5, 18.5)),
        BuildingDef("hideout", (-18.5, 4.5), (-9.5, 15.5)),
        BuildingDef("guard_house", (30.0, -8.0), (39.0, 4.0), roof_texture="roof_slate"),
        BuildingDef("jail", (30.0, 12.0), (39.0, 22.0), roof_texture="roof_slate"),
    )

    props = (
        PropDef("barnaby_bed", (15.5, 0, 15.0), (17.5, 0.6, 17.5)),
        PropDef("shop_counter", (8.0, 0, -5.2), (12.0, 1.0, -4.6), texture="wall"),
        PropDef("shop_table", (5.7, 0, -7.5), (7.2, 0.8, -6.0)),
        PropDef("guard_bed_1", (30.8, 0, -7.2), (32.3, 0.6, -5.2)),
        PropDef("guard_bed_2", (30.8, 0, -4.2), (32.3, 0.6, -2.2)),
        PropDef("guard_bed_3", (30.8, 0, -1.2), (32.3, 0.6, 0.8)),
        PropDef("raz_bed", (-17.8, 0, 12.5), (-16.3, 0.6, 14.5)),
        PropDef("raz_table", (-17.5, 0, 7.0), (-15.5, 0.8, 8.0)),
        PropDef("jail_guard_bed", (30.8, 0, 19.0), (32.3, 0.6, 21.0)),
        PropDef("jail_cell_bed", (36.9, 0, 13.5), (38.4, 0.6, 15.5)),
    )

    containers = (
        ContainerDef(
            "shop_shelf_west", "Shop Shelf", (5.5, 0, -9.5), (8.5, 1.8, -8.7), owner="Shopkeeper Barnaby", crime_name="Shoplifting",
            items=(ItemDef("candlestick", "Silver Candlestick", value=45.0),
                   ItemDef("wine", "Bottle of Wine", value=12.0, stackable=True, quantity=3),
                   ItemDef("thread", "Spool of Silk Thread", value=4.0, stackable=True, quantity=5)),
        ),
        ContainerDef(
            "shop_shelf_east", "Shop Shelf", (11.5, 0, -9.5), (14.5, 1.8, -8.7), owner="Shopkeeper Barnaby", crime_name="Shoplifting",
            items=(ItemDef("lantern", "Brass Lantern", value=30.0),
                   ItemDef("honey", "Jar of Honey", value=9.0, stackable=True, quantity=2),
                   ItemDef("plate", "Pewter Plate", value=18.0),
                   ItemDef("pickaxe", "Pickaxe", value=35.0)),
        ),
        ContainerDef("barnaby_table", "Kitchen Table", (11.0, 0, 11.5), (13.0, 0.8, 12.5), owner="Shopkeeper Barnaby",
                     texture="wood", kind="table",
                     items=(ItemDef("stew", "Pot of Stew", value=4.0, stackable=True, quantity=6, is_food=True),)),
        ContainerDef("guard_table", "Guard Table", (34.5, 0, -5.0), (38.0, 0.8, -2.0), owner="guards", texture="wood", kind="table",
                     items=(ItemDef("ration", "Guard's Ration", value=3.0, stackable=True, quantity=8, is_food=True),)),
        # The confiscation lockbox: locked (the jailer's cell key opens it; it is unlocked for a released prisoner).
        ContainerDef("jail_storage", "Confiscation Lockbox", (30.8, 0, 13.0), (32.3, 1.0, 14.5), owner="guards",
                     texture="lockbox", kind="lockbox", locked=True, lock_difficulty=3, key_id="cell_key"),
    )

    stations = (
        StationDef("ore_deposit", "Ore Deposit", (-38.0, 0, -38.0), (-35.0, 1.6, -35.0), texture="ore",
                   yields=ItemDef("iron_ore", "Iron Ore", value=6.0, stackable=True),
                   requires_item_id="pickaxe", tool_label="a pickaxe", xp=10.0),
        StationDef("anvil", "Anvil", (-3.5, 0, -8.4), (-2.5, 0.8, -7.6), texture="stone",
                   consumes=("iron_ore", 1), consumes_label="1 Iron Ore",
                   produces=ItemDef("iron_lockpick", "Iron Lockpick", value=5.0, is_lockpick=True, stackable=True, quantity=3),
                   xp=40.0),
    )

    areas = (
        AreaDef("behind the counter", (5.0, -10.0), (15.0, -4.6), owner="Shopkeeper Barnaby", restricted=True),
        AreaDef("the shop", (5.0, -4.6), (15.0, 0.5), owner="Shopkeeper Barnaby", restricted=True,
                public_hours=(SHOP_OPEN_HOUR, SHOP_CLOSE_HOUR)),
        AreaDef("Barnaby's house", (9.5, 9.5), (18.5, 18.5), owner="Shopkeeper Barnaby", restricted=True),
        AreaDef("the hideout", (-18.5, 4.5), (-9.5, 15.5), owner="Raz the Fence", restricted=True, trusted_by=("Raz the Fence",),
                curfew_hours=(22, 6)),          # Raz puts even his partner out when he turns in
        AreaDef("the guard house", (30.0, -8.0), (39.0, 4.5), owner="guards", restricted=True),
        AreaDef("the jail cell", (35.0, 12.5), (39.0, 18.5), owner="guards", restricted=True),
        AreaDef("the jail", (30.0, 12.0), (39.0, 22.5), owner="guards"),       # the jail house itself is public
        AreaDef("the town square", (-8.0, -8.0), (8.0, 8.0)),
    )

    doors = (
        DoorDef("hideout_door", (-14.5, 0.0, 5.0), is_locked=False, key_id="hideout_key", owners=("Raz the Fence",)),
        DoorDef("shop_door", (8.5, 0.0, 0.0), is_locked=True, key_id="shop_key", owners=("Shopkeeper Barnaby",), lock_difficulty=2),
        DoorDef("home_door", (13.0, 0.0, 10.0), is_locked=True, key_id="home_key", owners=("Shopkeeper Barnaby",), lock_difficulty=2),
        DoorDef("guardhouse_door", (33.0, 0.0, 4.0), is_locked=True, key_id="guard_key", owners=("guards",), lock_difficulty=3),
        # The jail house is open to all (nobody owns - i.e. locks - its door); the cell is a barred gate.
        DoorDef("jail_door", (33.0, 0.0, 22.0), is_locked=False, key_id="guard_key", lock_difficulty=3),
        DoorDef("cell_door", (35.5, 0.0, 18.5), is_locked=True, key_id="cell_key", owners=("guards",), lock_difficulty=3,
                kind=DoorKind.BARS),
    )

    # Better (and pricier) goods Barnaby starts stocking as the player grows notorious.
    stock_tiers = (
        StockTier(2, (ItemDef("fine_lockpick", "Fine Steel Lockpick", value=15.0, is_lockpick=True, stackable=True, quantity=3),
                      ItemDef("silk_gloves", "Silk Gloves", value=60.0, noise_modifier=-0.1)), container="shop_shelf_east"),
        StockTier(4, (ItemDef("jeweled_dagger", "Jeweled Dagger", value=180.0),
                      ItemDef("velvet_cloak", "Velvet Cloak", value=140.0, noise_modifier=-0.15)), container="shop_shelf_west"),
        StockTier(6, (ItemDef("ruby_necklace", "Ruby Necklace", value=320.0),
                      ItemDef("shadow_boots", "Shadow Boots", value=260.0, noise_modifier=-0.2)), container="shop_shelf_east"),
    )

    npcs = (
        NPCDef(
            "Shopkeeper Barnaby", HOME_BED, can_trade=True,
            shop_containers=("shop_shelf_west", "shop_shelf_east"), restock_days=3, restock_tiers=stock_tiers,
            inventory_reset_days=3, gold=SHOPKEEPER_GOLD,
            inventory=(
                ItemDef("shop_key", "Store Backroom Key", value=1.0, is_key=True, key_door_id="shop_door", for_sale=False),
                ItemDef("home_key", "Barnaby's House Key", value=1.0, is_key=True, key_door_id="home_door", for_sale=False),
                ItemDef("bread_1", "Fresh Bread", value=15.0, stackable=True, quantity=4, is_food=True),
                ItemDef("apple_1", "Crisp Apple", value=8.0, stackable=True, quantity=6, is_food=True),
                ItemDef("torch_item", "Portable Torch", value=25.0),
            ),
            schedule=(
                TaskDef(0, 7, HOME_BED, AIState.SLEEPING, "Barnaby is snoring loudly in bed.", lock_doors=("home_door",)),
                TaskDef(7, SHOP_OPEN_HOUR, HOME_TABLE, AIState.EATING, "Barnaby is eating breakfast at home.",
                        unlock_doors=("home_door",), facing=0.0, food_container="barnaby_table"),
                TaskDef(SHOP_OPEN_HOUR, SHOP_LUNCH_HOUR, SHOP_COUNTER, AIState.SHOPKEEPING,
                        "Barnaby opened the shop for business.", unlock_doors=("shop_door",),
                        depart_text="Time to open up the shop.", facing=180.0),
                TaskDef(SHOP_LUNCH_HOUR, SHOP_LUNCH_HOUR + 1, SHOP_BACKROOM, AIState.EATING,
                        "Barnaby is having lunch in the back room.", facing=0.0),
                TaskDef(SHOP_LUNCH_HOUR + 1, SHOP_CLOSE_HOUR, SHOP_COUNTER, AIState.SHOPKEEPING,
                        "Barnaby is back behind the counter.", facing=180.0),
                TaskDef(SHOP_CLOSE_HOUR, SHOP_CLOSE_HOUR + 1, HOME_TABLE, AIState.EATING,
                        "Barnaby is having dinner at home.", unlock_doors=("home_door",),
                        depart_text="Closing time. Off home for supper.", facing=0.0, food_container="barnaby_table"),
                TaskDef(SHOP_CLOSE_HOUR + 1, 24, HOME_BED, AIState.SLEEPING, "Barnaby locked up and went to bed.",
                        lock_doors=("home_door",)),
            ),
        ),
        NPCDef(
            "Raz the Fence", RAZ_ALLEY, is_fence=True, can_trade=True, inventory_reset_days=3, gold=FENCE_GOLD,
            inventory=(
                ItemDef("lockpick_pack", "Master Lockpick", value=20.0, is_lockpick=True, stackable=True, quantity=3),
                ItemDef("gold_ring", "Gold Ring", value=150.0),
                ItemDef("dried_meat", "Dried Meat", value=5.0, stackable=True, quantity=4, is_food=True, for_sale=False),
            ),
            schedule=(
                TaskDef(0, 6, RAZ_BED, AIState.SLEEPING, "Raz is asleep in the hideout."),
                TaskDef(6, 7, RAZ_TABLE, AIState.EATING, "Raz is eating at his table.", facing=0.0),
                TaskDef(7, 22, RAZ_ALLEY, AIState.SHOPKEEPING, "Raz is in his den, ready to deal in stolen goods.",
                        facing=0.0),
                TaskDef(22, 23, RAZ_TABLE, AIState.EATING, "Raz is having a late supper.", facing=0.0),
                TaskDef(23, 24, RAZ_BED, AIState.SLEEPING, "Raz turned in for the night."),
            ),
        ),
        # Three guards on rotating 8-hour shifts: at any hour one patrols, one stands post and one rests.
        guard("Guard Captain Vance", patrol=(6, 14), meal=(14, 15), post=(15, 22), post_spot=POST_TOWER,
              sleep=(22, 6), bed=GUARD_BEDS[0], meal_seat=GUARD_TABLE_SEATS[0]),
        guard("Guard Orrin", patrol=(14, 22), meal=(22, 23), post=(6, 14), post_spot=POST_DOOR,
              sleep=(23, 6), bed=GUARD_BEDS[1], meal_seat=GUARD_TABLE_SEATS[1]),
        guard("Guard Mira", patrol=(22, 6), meal=(6, 7), post=(14, 22), post_spot=POST_DOOR,
              sleep=(7, 14), bed=GUARD_BEDS[2], meal_seat=GUARD_TABLE_SEATS[2]),
        # The jailer keeps the cell and the confiscation chest.
        NPCDef(
            "Jailer Hesk", JAIL_GUARD_BED, is_guard=True, inventory_reset_days=1, gold=GUARD_GOLD,
            inventory=(GUARD_KEY, ItemDef("cell_key", "Cell Key", value=1.0, is_key=True, key_door_id="cell_door", for_sale=False),
                       RATIONS),
            schedule=(
                TaskDef(0, 6, JAIL_GUARD_BED, AIState.SLEEPING, "Hesk is asleep in the jail office."),
                TaskDef(6, 7, (33.8, 0.0, 20.5), AIState.EATING, "Hesk is having breakfast at the jail.", facing=0.0),
                TaskDef(7, 22, JAIL_POST, AIState.GUARDING, "Hesk is keeping watch over the cells.", facing=90.0),
                TaskDef(22, 24, JAIL_GUARD_BED, AIState.SLEEPING, "Hesk turned in for the night."),
            ),
        ),
    )

    return LevelDefinition(
        name="town",
        walls=walls,
        doors=doors,
        npcs=npcs,
        anvil_position=ANVIL,
        player_spawn=(-12.0, 1.0, -6.0),
        props=props,
        containers=containers,
        stations=stations,
        areas=areas,
        buildings=buildings,
        jail=JailDef(cell_door_id="cell_door", storage="jail_storage", cell_area="the jail cell", jail_area="the jail",
                     cell_spot=JAIL_CELL_SPOT, jailer="Jailer Hesk", post=JAIL_POST),
        bounds=(-40.0, -40.0, 40.0, 40.0),
        ground_half_size=50.0,
        player_gold=50.0,
        player_inventory=(
            ItemDef("iron_lockpick", "Iron Lockpick", value=5.0, noise_modifier=0.0, is_lockpick=True, stackable=True),
            ItemDef("soft_shoes", "Soft Leather Boots", value=30.0, noise_modifier=-0.05),
            ItemDef("silver_goblet", "Silver Goblet", value=120.0, is_stolen=True),
        ),
        intro_message="Tutorial started: Explore merchants, trade wares, and open doors!",
    )
