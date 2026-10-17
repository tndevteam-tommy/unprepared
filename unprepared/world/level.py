"""Declarative level description.

A level is plain data (dataclasses) that ``World`` turns into live entities.
Adding a new map means writing a new ``LevelDefinition`` in ``world/levels`` -
no gameplay or rendering code needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Tuple

from ..core.math3d import BoundingBox3D, Vector3D
from ..entities import AIState, Door, DoorKind, DoorSchedule, Item, NPC, Outfit, ScheduleTask
from ..entities.inventory import add_item

if TYPE_CHECKING:  # pragma: no cover
    from .tower import StairDef

Vec = Tuple[float, float, float]


@dataclass(frozen=True)
class WallDef:
    min_point: Vec
    max_point: Vec
    texture: str = "building"      # key into the texture registry

    def build(self) -> "Wall":
        return Wall(BoundingBox3D(Vector3D(*self.min_point), Vector3D(*self.max_point)), self.texture)


class Wall(BoundingBox3D):
    """A solid AABB with a texture key; usable anywhere a BoundingBox3D is (collision / line of sight)."""

    def __init__(self, box: BoundingBox3D, texture: str = "building"):
        super().__init__(box.min_point, box.max_point)
        self.texture = texture

    def __repr__(self) -> str:
        return f"Wall({self.min_point}, {self.max_point}, texture={self.texture!r})"


@dataclass(frozen=True)
class PropDef:
    """Solid decorative box (bed, table, anvil...). Blocks movement and NPC paths. ``kind`` picks
    how it is drawn: a plain box, or a modelled structure ("well", "forge", "oven", "sign") that
    fills the same footprint; ``facing`` is the yaw a modelled structure turns to (0 = its front
    looks along -z). ``solid=False`` props are decoration only (a hanging sign)."""
    name: str
    min_point: Vec
    max_point: Vec
    texture: str = "building"
    kind: str = "box"
    facing: float = 0.0
    solid: bool = True
    owner: Optional[str] = None          # a bed's owner; "player" for one the player may sleep in

    def build(self) -> "Prop":
        return Prop(self.name, BoundingBox3D(Vector3D(*self.min_point), Vector3D(*self.max_point)), self.texture,
                    self.kind, self.facing, self.solid, self.owner)


class Prop(BoundingBox3D):
    def __init__(self, name: str, box: BoundingBox3D, texture: str = "building", kind: str = "box",
                 facing: float = 0.0, solid: bool = True, owner: Optional[str] = None):
        super().__init__(box.min_point, box.max_point)
        self.name = name
        self.texture = texture
        self.kind = kind
        self.facing = facing
        self.solid = solid
        self.owner = owner

    @property
    def is_bed(self) -> bool:
        return "bed" in self.name

    def __repr__(self) -> str:
        return f"Prop({self.name!r}, {self.min_point}, {self.max_point})"


@dataclass(frozen=True)
class ItemDef:
    id: str
    name: str
    value: float = 50.0
    is_stolen: bool = False
    noise_modifier: float = 0.0
    is_key: bool = False
    key_door_id: Optional[str] = None
    is_lockpick: bool = False
    for_sale: bool = True
    stackable: bool = False
    quantity: int = 1
    is_food: bool = False
    category: str = "goods"      # "weapon", "armor", "ore", "food", "clothing", "tool", "key", "service", "goods"

    def build(self) -> Item:
        return Item(self.id, self.name, self.value, self.is_stolen, self.noise_modifier,
                    self.is_key, self.key_door_id, self.is_lockpick, self.for_sale, self.stackable, self.quantity,
                    self.is_food, category=self.category)


@dataclass(frozen=True)
class ContainerDef:
    """A solid box holding items the player can take from / put into (shop shelf, chest...).
    ``owner`` makes taking items a crime (``crime_name``) reported to witnesses - except
    items tagged as the player's own property. A container may be ``locked`` (a lockbox):
    it is opened with the key item ``key_id`` or picked like a door (``lock_difficulty``)."""
    name: str
    label: str
    min_point: Vec
    max_point: Vec
    items: Tuple[ItemDef, ...] = ()
    texture: str = "building"
    owner: Optional[str] = None
    crime_name: str = "Theft"
    locked: bool = False
    lock_difficulty: int = 1
    key_id: Optional[str] = None
    kind: str = "box"                # "box", "table" (drawn with four legs), "lockbox", "shelf"

    def build(self) -> "Container":
        c = Container(self.name, self.label, BoundingBox3D(Vector3D(*self.min_point), Vector3D(*self.max_point)),
                      self.texture, self.owner, self.crime_name, self.locked, self.lock_difficulty, self.key_id, self.kind)
        for i in self.items:
            add_item(c.inventory, i.build())
        return c


class Container(BoundingBox3D):
    def __init__(self, name: str, label: str, box: BoundingBox3D, texture: str = "building",
                 owner: Optional[str] = None, crime_name: str = "Theft", locked: bool = False,
                 lock_difficulty: int = 1, key_id: Optional[str] = None, kind: str = "box"):
        super().__init__(box.min_point, box.max_point)
        self.name = name
        self.label = label
        self.texture = texture
        self.owner = owner
        self.crime_name = crime_name
        self.inventory: list = []
        self.is_locked = locked
        self.lock_difficulty = lock_difficulty
        self.key_id = key_id
        self.kind = kind

    # lockable interface shared with Door (lockpicking / keys)
    @property
    def lock_id(self) -> str:
        return self.name

    def unlock_and_open(self) -> None:
        self.is_locked = False

    def lock_and_close(self) -> None:
        self.is_locked = True

    @property
    def center(self) -> Vector3D:
        return Vector3D((self.min_point.x + self.max_point.x) / 2, (self.min_point.y + self.max_point.y) / 2,
                        (self.min_point.z + self.max_point.z) / 2)

    def to_dict(self) -> dict:
        return {"name": self.name, "inventory": [i.to_dict() for i in self.inventory], "is_locked": self.is_locked}

    def load_dict(self, data: dict) -> None:
        if "inventory" in data:
            self.inventory = [Item.from_dict(i) for i in data["inventory"]]
        self.is_locked = data.get("is_locked", self.is_locked)

    def __repr__(self) -> str:
        return f"Container({self.name!r}, {len(self.inventory)} items)"


@dataclass(frozen=True)
class DoorDef:
    door_id: str
    hinge_position: Vec
    is_locked: bool = True
    key_id: str = "shop_key"
    width: float = 3.0
    height: float = 3.5
    texture: str = "building"
    open_hour: Optional[int] = None
    close_hour: Optional[int] = None
    open_message: Optional[str] = None
    close_message: Optional[str] = None
    owners: Tuple[str, ...] = ()         # NPC names / faction tags responsible for the door (they shut and lock it)
    lock_difficulty: int = 1
    kind: DoorKind = DoorKind.LEAF       # BARS: a see-through gate nobody shuts as a side effect (jail cells)
    swing_out: bool = False              # the leaf folds into +z (towards the street for a north-wall door) when open

    def build(self) -> Door:
        schedule = None
        if self.open_hour is not None or self.close_hour is not None:
            schedule = DoorSchedule(self.open_hour if self.open_hour is not None else -1,
                                    self.close_hour if self.close_hour is not None else -1,
                                    self.open_message, self.close_message)
        return Door(self.door_id, Vector3D(*self.hinge_position), width=self.width, height=self.height,
                    is_locked=self.is_locked, key_id=self.key_id, schedule=schedule, owners=self.owners,
                    lock_difficulty=self.lock_difficulty, kind=self.kind, swing_out=self.swing_out)


@dataclass(frozen=True)
class TaskDef:
    start_hour: int
    end_hour: int
    target_pos: Vec
    state: AIState
    action_text: str
    unlock_doors: Tuple[str, ...] = ()
    close_doors: Tuple[str, ...] = ()
    lock_doors: Tuple[str, ...] = ()
    lock_doors_on_departure: Tuple[str, ...] = ()
    depart_text: Optional[str] = None
    patrol_points: Tuple[Vec, ...] = ()
    open_doors: Tuple[str, ...] = ()
    facing: Optional[float] = None
    food_container: Optional[str] = None

    def build(self) -> ScheduleTask:
        return ScheduleTask(self.start_hour, self.end_hour, Vector3D(*self.target_pos), self.state, self.action_text,
                            self.unlock_doors, self.close_doors, self.lock_doors, self.lock_doors_on_departure,
                            self.depart_text, tuple(Vector3D(*p) for p in self.patrol_points), self.open_doors,
                            self.facing, self.food_container)


@dataclass(frozen=True)
class AreaDef:
    """A named region of the map.

    Used for crime reports ('the shop', 'the guard house'...) and for *trust*:
    ``owner`` (an NPC name or a faction tag) may object to the player being
    there when ``restricted`` - unless the player is in ``trusted_by`` (e.g. Raz
    trusts the player in the hideout) or ``public_hours`` cover the current hour
    (a shop floor during business hours).
    """
    name: str
    min_xz: Tuple[float, float]
    max_xz: Tuple[float, float]
    owner: Optional[str] = None
    restricted: bool = False
    public_hours: Optional[Tuple[int, int]] = None     # (start, end) hours when anybody may be there
    trusted_by: Tuple[str, ...] = ()                   # NPC names that trust the player here (overrides restriction)
    curfew_hours: Optional[Tuple[int, int]] = None     # (start, end; may wrap midnight) when even a welcome guest is
    #                                                    asked to leave and, if they linger, shown the door

    def contains(self, x: float, z: float) -> bool:
        return self.min_xz[0] <= x <= self.max_xz[0] and self.min_xz[1] <= z <= self.max_xz[1]

    def curfew_active(self, hour: int) -> bool:
        if self.curfew_hours is None:
            return False
        start, end = self.curfew_hours
        return start <= hour < end if start < end else (hour >= start or hour < end)

    def is_open_to_public(self, hour: int) -> bool:
        if not self.restricted:
            return True
        if self.public_hours is not None:
            start, end = self.public_hours
            return start <= hour < end
        return False


@dataclass(frozen=True)
class BuildingDef:
    """Footprint of a roofed building: used to draw its floor, ceiling and gabled roof, and
    to tell indoors from outdoors. ``open_sides`` marks a roof on posts (a shed): it is drawn
    but counts as outdoors - no walls to muffle sound or stop light, no lantern of its own."""
    name: str
    min_xz: Tuple[float, float]
    max_xz: Tuple[float, float]
    wall_height: float = 4.0
    roof_height: float = 1.6
    roof_texture: str = "roof"
    floor_texture: str = "wood"
    open_sides: bool = False
    open_top: bool = False           # no ceiling or roof (a tower with a look-out platform)


@dataclass(frozen=True)
class RoadDef:
    """A paved rectangle (cobbles) drawn on the ground with soft, grass-blended edges."""
    min_xz: Tuple[float, float]
    max_xz: Tuple[float, float]
    texture: str = "cobble"


@dataclass(frozen=True)
class LightDef:
    """An indoor light fixture: a wall-mounted lantern or a table candle. Levels may list
    them explicitly; ``World`` also generates one lantern per room and a candle per table
    (the standing rule for every building)."""
    kind: str                    # "lantern" or "candle"
    position: Vec                # flame position (lanterns: just off the wall; candles: on the table top)
    facing: float = 0.0          # lanterns: yaw the bracket points into the room (0 = -z, 90 = +x)
    room: str = ""               # area / building it lights
    range: float = 7.0           # light reach in world units


@dataclass(frozen=True)
class StationDef:
    """A solid box the player can use with [E]: a mine (needs a tool, yields an item) or a
    crafting station such as the anvil (consumes ``consumes`` units of an item, produces ``produces``)."""
    name: str
    label: str
    min_point: Vec
    max_point: Vec
    texture: str = "stone"
    yields: Optional[ItemDef] = None             # mining: the item produced per use
    requires_item_id: Optional[str] = None       # tool that must be in the player's inventory (a pickaxe to mine, a mallet to forge)
    tool_label: str = "a tool"
    consumes: Optional[Tuple[str, int]] = None   # crafting: (item id, count) used up per batch
    consumes_label: str = "materials"
    produces: Optional[ItemDef] = None           # crafting: the batch produced (quantity = batch size)
    xp: float = 10.0

    def build(self) -> "Station":
        return Station(self)


class Station(BoundingBox3D):
    def __init__(self, definition: StationDef):
        d = definition
        super().__init__(Vector3D(*d.min_point), Vector3D(*d.max_point))
        self.definition = d
        self.name, self.label, self.texture = d.name, d.label, d.texture
        self.uses = 0

    @property
    def is_mine(self) -> bool:
        return self.definition.yields is not None

    @property
    def center(self) -> Vector3D:
        return Vector3D((self.min_point.x + self.max_point.x) / 2, (self.min_point.y + self.max_point.y) / 2,
                        (self.min_point.z + self.max_point.z) / 2)

    def __repr__(self) -> str:
        return f"Station({self.name!r})"


@dataclass(frozen=True)
class JailDef:
    """Everything the justice system needs to lock someone up in this level.

    The cell is sealed off by a ``DoorKind.BARS`` door; confiscated belongings go into
    the ``storage`` container (a lockbox the jailer unlocks on release); ``cell_spot`` is
    where the prisoner is put; ``jailer`` keeps watch from ``post`` and waits there until
    a released prisoner has left ``jail_area``. ``cell_area`` is the restricted cell,
    ``jail_area`` the (public) jail house around it.
    """
    cell_door_id: str
    storage: str
    cell_area: str
    jail_area: str
    cell_spot: Vec
    jailer: Optional[str] = None
    post: Optional[Vec] = None


@dataclass(frozen=True)
class InnRoomDef:
    area: str            # the room's AreaDef name
    door_id: str         # its (lockable) door
    bed: Vec             # where a guest may rest


@dataclass(frozen=True)
class InnDef:
    """An inn: the keeper rents ``rooms`` for ``night_price`` a night or ``week_price`` a week
    (bought like goods from the keeper's stock), unlocks the room for the stay and shows a guest
    the door once the rent has run out (after ``checkout_hour`` on the last day)."""
    keeper: str
    rooms: Tuple[InnRoomDef, ...]
    night_price: float = 10.0
    week_price: float = 50.0
    checkout_hour: int = 12
    area: str = "the inn"


@dataclass(frozen=True)
class StockTier:
    """Extra stock a shopkeeper starts carrying once the player has reached ``min_player_level``."""
    min_player_level: int
    items: Tuple[ItemDef, ...]
    container: Optional[str] = None      # shelf to put them on; None = the shopkeeper's own stock


@dataclass(frozen=True)
class NPCDef:
    name: str
    home_pos: Vec
    is_guard: bool = False
    is_fence: bool = False
    can_trade: bool = False
    inventory: Tuple[ItemDef, ...] = ()
    schedule: Tuple[TaskDef, ...] = ()
    texture: Optional[str] = None   # defaults to "guard" / "npc" by role
    faction: Optional[str] = None   # defaults to "guards" for guards
    # shopkeepers: the containers whose contents they also sell and keep stock of
    shop_containers: Tuple[str, ...] = ()
    restock_days: int = 3
    restock_tiers: Tuple[StockTier, ...] = ()
    inventory_reset_days: int = 1        # personal items (keys, rations) are replaced after this many days
    gold: float = 0.0                    # coins carried; topped back up to this every ``restock_days``
    trade_categories: Tuple[str, ...] = ()    # a specialist only buys/sells these item categories (empty = anything)
    role: str = ""                       # flavour for dialogue: "smith", "innkeeper", "tailor", "shopkeeper", ...
    outfit: Optional[Outfit] = None      # what they wear; None picks one for the role (see entities/outfit.py)

    def build(self, perception_settings=None, npc_settings=None) -> NPC:
        npc = NPC(self.name, self.is_guard, self.is_fence, self.can_trade, Vector3D(*self.home_pos),
                  settings=perception_settings, npc_settings=npc_settings, faction=self.faction)
        npc.gold = npc.base_gold = float(self.gold)
        npc.trade_categories = tuple(self.trade_categories)
        npc.role_tag = self.role
        npc.outfit = self.outfit
        for i in self.inventory:
            add_item(npc.inventory, i.build())
        npc.shop_containers = list(self.shop_containers)
        npc.restock_days = self.restock_days
        npc.restock_tiers = list(self.restock_tiers)
        npc.base_stock = [i for i in self.inventory if i.for_sale]
        npc.base_inventory = list(self.inventory)
        npc.inventory_reset_days = self.inventory_reset_days
        if npc.is_fence:
            for item in npc.inventory:
                item.is_stolen = False       # a fence's goods are never 'hot' while in the fence's hands
        npc.schedule = [t.build() for t in self.schedule]
        return npc


@dataclass(frozen=True)
class LevelDefinition:
    name: str
    walls: Tuple[WallDef, ...]
    doors: Tuple[DoorDef, ...]
    npcs: Tuple[NPCDef, ...]
    anvil_position: Vec
    player_spawn: Vec
    props: Tuple[PropDef, ...] = ()
    containers: Tuple[ContainerDef, ...] = ()
    stations: Tuple[StationDef, ...] = ()
    areas: Tuple[AreaDef, ...] = ()
    buildings: Tuple[BuildingDef, ...] = ()
    jail: Optional[JailDef] = None
    lights: Tuple[LightDef, ...] = ()          # extra fixtures on top of the generated ones
    auto_lights: bool = True                   # a lantern per room and a candle per table
    roads: Tuple[RoadDef, ...] = ()            # paving; doorsteps are added automatically for doors set back from it
    inn: Optional["InnDef"] = None
    stairs: Tuple["StairDef", ...] = ()       # stairs NPCs climb by their waypoints (see world/tower.py)
    default_area: str = "the streets"
    bounds: Tuple[float, float, float, float] = (-25.0, -25.0, 25.0, 25.0)   # walkable area: min_x, min_z, max_x, max_z
    player_gold: float = 50.0
    player_inventory: Tuple[ItemDef, ...] = ()
    ground_half_size: float = 50.0
    ground_texture_repeat: float = 10.0
    ground_texture: str = "ground"
    intro_message: Optional[str] = None
