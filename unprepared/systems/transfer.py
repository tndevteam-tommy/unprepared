"""Two-sided item transfer sessions: trading, pickpocketing, containers.

A :class:`TransferSession` shows two inventories side by side (left: the other
party, right: the player), lets the player switch sides with Tab, move a cursor
within the active side and "confirm" the selected item, which moves one unit of
it across.  What a move *means* (price, theft, crime report...) is decided by a
:class:`TransferPolicy`; the session and the HUD widget are shared by every kind
of exchange, so new uses (lockboxes, corpses, stashes) only need a policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional

import random

from ..config import EconomySettings, ProgressionSettings, SkillRewards, StealthSettings
from ..entities import AIState, Item, NPC, Player, SkillType
from ..entities.inventory import add_item, take_item
from . import commerce, progression
from .stealth import pickpocket_chance, roll, stealing_chance

COIN_ITEM_ID = "gold_coins"

Notify = Optional[Callable[[str], None]]
CrimeReport = Optional[Callable[[str], list]]     # returns the NPCs who witnessed the crime


class Side(Enum):
    LEFT = "left"     # the other party (merchant stock, victim's pockets, container)
    RIGHT = "right"   # the player


class TransferOutcome(Enum):
    MOVED = "moved"
    NOT_ENOUGH_GOLD = "not_enough_gold"
    MERCHANT_BROKE = "merchant_broke"   # the merchant cannot afford what the player is selling
    REFUSED_STOLEN = "refused_stolen"   # merchant calls the guards; session must end
    CAUGHT = "caught"                   # failed pickpocket: the victim noticed; session must end
    NOTHING = "nothing"                 # cursor on no item


@dataclass(frozen=True)
class TransferResult:
    outcome: TransferOutcome
    item: Optional[Item] = None
    price: float = 0.0
    side: Optional[Side] = None         # side the item was taken from
    close_session: bool = False


def move_one(src: List[Item], dst: List[Item], item: Item, mutate: Optional[Callable[[Item], None]] = None) -> Item:
    """Move one unit of ``item`` from ``src`` to ``dst`` (stack-aware); ``mutate`` may adjust the moved unit first."""
    moved = take_item(src, item, 1)
    if mutate is not None:
        mutate(moved)
    return add_item(dst, moved)


# ----------------------------------------------------------------------------- policies
class TransferPolicy:
    """Rules for one kind of exchange. Subclasses override the hooks they need."""
    title = "TRANSFER"
    left_label = "THEIRS"
    right_label = "YOURS"
    help_text = "[TAB] switch side, [UP/DOWN] select, [ENTER] move item, [ESC] close"

    def visible_left(self, items: List[Item]) -> List[Item]:
        return list(items)

    def row_text(self, item: Item, side: Side, session: "TransferSession") -> str:
        return item.display_name

    def take(self, session: "TransferSession", item: Item) -> TransferResult:   # left -> right
        move_one(session.left_items, session.right_items, item)
        return TransferResult(TransferOutcome.MOVED, item, side=Side.LEFT)

    def give(self, session: "TransferSession", item: Item) -> TransferResult:   # right -> left
        move_one(session.right_items, session.left_items, item)
        return TransferResult(TransferOutcome.MOVED, item, side=Side.RIGHT)


class TradePolicy(TransferPolicy):
    """Buying from a merchant's stock (for-sale items only) and selling to them.

    Merchants pay out of their own purse (``NPC.gold``) and pocket what the player
    spends. Every deal trains Barter: the pricier the goods the more XP, less and
    less as the skill grows; a good haggler sells dearer and buys cheaper."""
    left_label = "MERCHANT STOCK (BUY)"
    right_label = "YOUR INVENTORY (SELL)"

    def __init__(self, merchant: NPC, player: Player, economy: EconomySettings, notify: Notify = None,
                 rewards: Optional[SkillRewards] = None, progression_settings: Optional[ProgressionSettings] = None):
        self.merchant, self.player, self.economy, self.notify = merchant, player, economy, notify
        self.rewards = rewards or SkillRewards()
        self.progression = progression_settings or ProgressionSettings()

    @property
    def title(self) -> str:
        return f"TRADING WITH: {self.merchant.name}   (purse: {self.merchant.gold:.0f}g)"

    def visible_left(self, items: List[Item]) -> List[Item]:
        return [i for i in items if i.for_sale]

    @property
    def barter_bonus(self) -> float:
        level = self.player.skills.level(SkillType.BARTER)
        return min(self.economy.barter_bonus_cap, self.economy.barter_bonus_per_level * (level - 1))

    def buy_price(self, item: Item) -> float:
        return round(item.value * (1.0 - self.barter_bonus), 1)

    def sell_price(self, item: Item) -> float:
        return round(item.sell_value(self.economy.stolen_goods_multiplier) * (1.0 + self.barter_bonus), 1)

    def row_text(self, item: Item, side: Side, session: "TransferSession") -> str:
        if side is Side.LEFT:
            return f"{item.display_name} - {self.buy_price(item):g}g"
        return f"{item.display_name} ({self.sell_price(item):g}g)"

    def _train(self, price: float) -> None:
        progression.grant(self.player, SkillType.BARTER, self.rewards.barter + progression.value_xp(price, self.progression),
                          notify=self.notify, s=self.progression)

    def take(self, session, item):
        price = self.buy_price(item)
        if self.player.gold < price:
            self._say("Not enough gold to buy this item!")
            return TransferResult(TransferOutcome.NOT_ENOUGH_GOLD, item, price, Side.LEFT)
        self.player.gold -= price
        self.merchant.gold += price
        move_one(session.left_items, session.right_items, item, lambda unit: setattr(unit, "owner", Item.PLAYER_OWNER))
        commerce.note_sale(self.merchant, item, -1)
        self._say(f"Bought {item.name} for {price:g}g.")
        self._train(price)
        return TransferResult(TransferOutcome.MOVED, item, price, Side.LEFT)

    def give(self, session, item):
        if item.is_stolen and not self.merchant.is_fence:
            self._say(f"({self.merchant.name}): \"That {item.name} is stolen! Guards!\"")
            self.merchant.state = AIState.REPORTING
            return TransferResult(TransferOutcome.REFUSED_STOLEN, item, side=Side.RIGHT, close_session=True)
        price = self.sell_price(item)
        if self.merchant.gold < price:
            self._say(f"({self.merchant.name}): \"I can't afford that right now - I've only {self.merchant.gold:.0f}g in the till.\"")
            return TransferResult(TransferOutcome.MERCHANT_BROKE, item, price, Side.RIGHT)
        self.player.gold += price
        self.merchant.gold -= price

        def hand_over(unit: Item) -> None:
            unit.is_stolen = False          # a fence launders what it buys: no longer 'hot' once it changes hands
            unit.owner = None
        move_one(session.right_items, session.left_items, item, hand_over)
        commerce.note_sale(self.merchant, item, +1)
        self._say(f"Sold {item.name} for {price:g}g.")
        self._train(price)
        return TransferResult(TransferOutcome.MOVED, item, price, Side.RIGHT)

    def _say(self, msg: str) -> None:
        if self.notify:
            self.notify(msg)


def coin_purse(gold: float) -> Item:
    """The victim's coins shown as a row in their pockets (a handful is lifted per success)."""
    return Item(COIN_ITEM_ID, "Gold Coins", value=1.0, for_sale=False, stackable=True, quantity=int(gold))


class PickpocketPolicy(TransferPolicy):
    """Lifting items (and handfuls of coin) from, or planting them on, an NPC. Every
    lift is a crime the bystanders may witness; stolen goods are flagged and reward
    Pickpocket XP - more for valuable things and awake or armed victims, less and
    less as the skill grows."""
    right_label = "YOUR INVENTORY (PLANT)"

    def __init__(self, victim: NPC, player: Player, rewards: SkillRewards, notify: Notify = None,
                 report_crime: CrimeReport = None, rng: Optional[random.Random] = None,
                 stealth: Optional[StealthSettings] = None, on_caught: Optional[Callable[[NPC], None]] = None,
                 economy: Optional[EconomySettings] = None, progression_settings: Optional[ProgressionSettings] = None):
        self.victim, self.player, self.rewards, self.notify, self.report_crime = victim, player, rewards, notify, report_crime
        self.rng = rng or random.Random()
        self.stealth = stealth or StealthSettings()
        self.economy = economy or EconomySettings()
        self.progression = progression_settings or ProgressionSettings()
        self.on_caught = on_caught
        self.title = f"PICKPOCKETING: {victim.name}"
        self.left_label = "THEIR POCKETS (STEAL)"

    @property
    def chance(self) -> float:
        return pickpocket_chance(self.player, self.victim, self.stealth, self.progression)

    def visible_left(self, items: List[Item]) -> List[Item]:
        rows = list(items)
        if self.victim.gold >= 1.0:
            rows.insert(0, coin_purse(self.victim.gold))
        return rows

    def row_text(self, item, side, session):
        if item.id == COIN_ITEM_ID and side is Side.LEFT:
            return f"{item.display_name}  (grab up to {self.economy.purse_grab})"
        return f"{item.display_name} ({item.value}g)"

    def _xp_magnitude(self, value: float) -> float:
        magnitude = self.rewards.pickpocket + progression.value_xp(value, self.progression)
        if self.victim.is_asleep:
            magnitude *= self.stealth.pickpocket_asleep_xp_multiplier
        if self.victim.is_guard:
            magnitude *= self.stealth.pickpocket_guard_xp_multiplier
        return magnitude

    def take(self, session, item):
        if self.report_crime:
            self.report_crime("Pickpocketing")
        if not roll(self.rng, self.chance):
            # Fumbled: the victim feels the hand in their pocket.
            progression.grant(self.player, SkillType.PICKPOCKET,
                              self._xp_magnitude(item.value) * self.stealth.pickpocket_fail_xp_multiplier,
                              notify=self.notify, s=self.progression)
            if self.notify:
                self.notify(f"Fumbled! {self.victim.name} catches your hand in their pocket.")
            if self.on_caught:
                self.on_caught(self.victim)
            return TransferResult(TransferOutcome.CAUGHT, item, side=Side.LEFT, close_session=True)

        if item.id == COIN_ITEM_ID:
            grabbed = float(min(self.economy.purse_grab, int(self.victim.gold)))
            self.victim.gold -= grabbed
            self.player.gold += grabbed
            progression.grant(self.player, SkillType.PICKPOCKET, self._xp_magnitude(grabbed), notify=self.notify,
                              s=self.progression)
            if self.notify:
                self.notify(f"Lifted {grabbed:.0f} gold from {self.victim.name}'s purse!")
            return TransferResult(TransferOutcome.MOVED, item, grabbed, Side.LEFT)

        def flag(unit: Item) -> None:
            unit.is_stolen = True
            unit.owner = None
        move_one(session.left_items, session.right_items, item, flag)
        progression.grant(self.player, SkillType.PICKPOCKET, self._xp_magnitude(item.value), notify=self.notify,
                          s=self.progression)
        if self.notify:
            self.notify(f"Pickpocketed {item.name} from {self.victim.name}!")
        return TransferResult(TransferOutcome.MOVED, item, side=Side.LEFT)

    def give(self, session, item):
        def plant(unit: Item) -> None:
            unit.owner = None
            if self.victim.is_fence:
                unit.is_stolen = False
        move_one(session.right_items, session.left_items, item, plant)
        if self.notify:
            self.notify(f"Planted {item.name} on {self.victim.name}.")
        return TransferResult(TransferOutcome.MOVED, item, side=Side.RIGHT)


class ContainerPolicy(TransferPolicy):
    """Taking from / putting into a container. Taking from somebody else's container is
    theft: the unit is flagged stolen and - unless a Stealing roll keeps it unnoticed -
    the crime is reported to whoever is watching. The player's *own* belongings (say, in
    the jail's confiscation lockbox) are simply taken back. Stealing XP scales with the
    value of the goods and shrinks with the skill."""
    right_label = "YOUR INVENTORY (PUT)"

    def __init__(self, container, player: Player, notify: Notify = None, report_crime: CrimeReport = None,
                 rewards: Optional[SkillRewards] = None, stealth: Optional[StealthSettings] = None,
                 rng: Optional[random.Random] = None, progression_settings: Optional[ProgressionSettings] = None):
        self.container, self.player, self.notify, self.report_crime = container, player, notify, report_crime
        self.rewards = rewards or SkillRewards()
        self.stealth = stealth or StealthSettings()
        self.rng = rng or random.Random()
        self.progression = progression_settings or ProgressionSettings()
        self.title = container.label.upper()
        self.left_label = f"{container.label.upper()} (TAKE)"

    @property
    def is_theft(self) -> bool:
        return self.container.owner is not None

    def row_text(self, item, side, session):
        return f"{item.display_name} ({item.value}g)"

    def take(self, session, item):
        if item.is_players or not self.is_theft:
            move_one(session.left_items, session.right_items, item)
            if self.notify:
                self.notify(f"Took back your {item.name}." if item.is_players else f"Took {item.name}.")
            return TransferResult(TransferOutcome.MOVED, item, side=Side.LEFT)
        unnoticed = roll(self.rng, stealing_chance(self.player, self.stealth, self.progression))
        witnesses = []
        if not unnoticed and self.report_crime:
            witnesses = self.report_crime(self.container.crime_name) or []

        def flag(unit: Item) -> None:
            unit.is_stolen = True
            unit.owner = None
        move_one(session.left_items, session.right_items, item, flag)
        magnitude = self.rewards.stealing + progression.value_xp(item.value, self.progression)
        if witnesses:
            magnitude *= self.stealth.stealing_fail_xp_multiplier
        progression.grant(self.player, SkillType.STEALING, magnitude, notify=self.notify, s=self.progression)
        if self.notify:
            self.notify(f"Stole {item.name} from the {self.container.label.lower()}.")
        return TransferResult(TransferOutcome.MOVED, item, side=Side.LEFT)

    def give(self, session, item):
        move_one(session.right_items, session.left_items, item)
        if self.notify:
            self.notify(f"Put {item.name} in the {self.container.label.lower()}.")
        return TransferResult(TransferOutcome.MOVED, item, side=Side.RIGHT)


# ----------------------------------------------------------------------------- session
class TransferSession:
    def __init__(self, left_items: List[Item], right_items: List[Item], policy: TransferPolicy, visible_rows: int = 14):
        self.left_items = left_items
        self.right_items = right_items
        self.policy = policy
        self.side = Side.LEFT
        self.selection: Dict[Side, int] = {Side.LEFT: 0, Side.RIGHT: 0}
        self.visible_rows = visible_rows
        self.scroll: Dict[Side, int] = {Side.LEFT: 0, Side.RIGHT: 0}      # first visible row per column

    def visible(self, side: Side):
        """(first index, rows shown) for a column, keeping the cursor in view."""
        rows = self.rows(side)
        max_scroll = max(0, len(rows) - self.visible_rows)
        first = min(self.scroll[side], max_scroll)
        cursor = self.selection[side]
        if cursor < first:
            first = cursor
        elif cursor >= first + self.visible_rows:
            first = cursor - self.visible_rows + 1
        self.scroll[side] = max(0, min(first, max_scroll))
        return self.scroll[side], rows[self.scroll[side]:self.scroll[side] + self.visible_rows]

    # rows -------------------------------------------------------------------
    def rows(self, side: Side) -> List[Item]:
        return self.policy.visible_left(self.left_items) if side is Side.LEFT else list(self.right_items)

    @property
    def active_rows(self) -> List[Item]:
        return self.rows(self.side)

    def selected_item(self, side: Optional[Side] = None) -> Optional[Item]:
        side = side or self.side
        rows = self.rows(side)
        idx = self.selection[side]
        return rows[idx] if 0 <= idx < len(rows) else None

    def row_text(self, item: Item, side: Side) -> str:
        return self.policy.row_text(item, side, self)

    # navigation -------------------------------------------------------------
    def switch_side(self) -> Side:
        self.side = Side.RIGHT if self.side is Side.LEFT else Side.LEFT
        self.clamp()
        return self.side

    def move_selection(self, delta: int) -> int:
        count = len(self.active_rows)
        self.selection[self.side] = (self.selection[self.side] + delta) % max(1, count)
        return self.selection[self.side]

    def clamp(self) -> None:
        for side in Side:
            self.selection[side] = min(self.selection[side], max(0, len(self.rows(side)) - 1))

    # action -----------------------------------------------------------------
    def confirm(self) -> TransferResult:
        item = self.selected_item()
        if item is None:
            return TransferResult(TransferOutcome.NOTHING)
        result = self.policy.take(self, item) if self.side is Side.LEFT else self.policy.give(self, item)
        self.clamp()
        return result
