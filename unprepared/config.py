"""Central configuration for Unprepared.

Every tunable that used to be a magic number inside ``main.py`` lives here so
that balancing, resolution changes or new content never require touching the
simulation or rendering code.  All values default to the exact numbers used by
the original prototype so behaviour is unchanged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Tuple

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)
DEFAULT_ASSET_DIR = os.path.join(PROJECT_DIR, "assets", "textures")
DEFAULT_SAVE_FILE = "savegame.json"

Color3 = Tuple[float, float, float]
Color4 = Tuple[float, float, float, float]
RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class WindowSettings:
    width: int = 1024
    height: int = 768
    title: str = "Unprepared"
    fov_degrees: float = 60.0
    near_plane: float = 0.1
    far_plane: float = 100.0
    target_fps: int = 60
    font_name: str = "Arial"
    font_size: int = 20
    font_small_size: int = 16
    tag_font_name: str = "Courier New"   # bold monospace used for the (S) stolen tag


@dataclass(frozen=True)
class PlayerSettings:
    walk_speed: float = 4.0            # world units / second
    sprint_multiplier: float = 1.8
    crouch_speed_multiplier: float = 0.5   # sneaking is slow
    attention_turn_speed: float = 150.0    # degrees/s the view swings round when an NPC demands attention
    mouse_sensitivity: float = 0.15    # degrees per pixel
    max_pitch: float = 89.0
    # ``player.position`` is at the feet (y = the floor), like an NPC's. The townsfolk stand 1.74 tall
    # with their eyes at 1.6, so the camera sits a touch below that: nobody towers over anybody.
    eye_height: float = 1.55           # camera offset above ``player.position`` when standing
    crouch_eye_height: float = 0.9     # ... and when crouching
    stance_transition_speed: float = 4.0   # eye height change per second between the two
    torch_light_height: float = 1.0
    starting_gold: float = 50.0
    # Collision: the player is a box ``collision_radius`` wide around ``position`` reaching from
    # ``position.y + collision_foot_clearance`` (low lips and steps do not catch the feet) up to
    # ``position.y + collision_head_height``.
    collision_radius: float = 0.3
    collision_foot_clearance: float = 0.25
    collision_head_height: float = 1.7
    # Stealth model
    noise_walk: float = 1.5
    noise_sprint: float = 3.0
    noise_crouch_multiplier: float = 0.3
    noise_floor: float = 0.1
    visibility_torch_bonus: float = 0.9
    visibility_crouch_multiplier: float = 0.4


@dataclass(frozen=True)
class TimeSettings:
    start_hour: int = 7
    time_scale: float = 2.5            # simulated minutes per real second
    minutes_per_hour: float = 60.0


@dataclass(frozen=True)
class InteractionSettings:
    door_range: float = 5.0
    npc_range: float = 6.0             # talk / trade distance (eye to NPC feet)
    container_range: float = 4.0
    aim_dot_threshold: float = 0.6     # cos(angle) needed between view dir and target
    door_aim_offset: Tuple[float, float] = (1.5, 1.5)   # (x, y) offset from hinge to aim point
    door_facing_min: float = 0.25      # view dir component towards the door plane needed (0 = edge-on allowed)
    crosshair_ray: bool = True         # whatever the crosshair ray hits first is the target (before the aim cone)
    npc_aim_height: float = 1.0
    pickpocket_range: float = 2.5      # must sneak this close (feet to feet) to pick pockets
    anvil_range: float = 3.0


@dataclass(frozen=True)
class LockpickSettings:
    rotate_step_degrees: float = 10.0
    success_tolerance_degrees: float = 15.0
    default_sweet_spot: float = 45.0   # used when ``random_sweet_spot`` is False
    random_sweet_spot: bool = True     # new random sweet spot for every lock attempt
    reset_pick_each_attempt: bool = True
    consume_pick_on_snap: bool = True  # a snapped pick is removed from the inventory
    xp_reward: float = 75.0


@dataclass(frozen=True)
class NPCSettings:
    move_speed: float = 3.6            # world units / second while travelling (a brisk walk; the player sprints at 7.2)
    patrol_pause: float = 2.0          # seconds spent at each patrol waypoint
    arrival_tolerance: float = 0.15    # distance at which a waypoint counts as reached
    door_operate_reach: float = 0.9    # how close (beyond the door box) an NPC opens a door it walks through
    door_lock_clearance: float = 1.5   # distance past a door before an NPC locks it behind itself
    locked_out_retry: float = 15.0     # seconds between attempts to get into a place that was shut


@dataclass(frozen=True)
class NavigationSettings:
    cell_size: float = 0.5
    agent_radius: float = 0.4          # obstacles are inflated by this much
    bounds: Tuple[float, float, float, float] = (-25.0, -25.0, 25.0, 25.0)   # min_x, min_z, max_x, max_z


@dataclass(frozen=True)
class EconomySettings:
    stolen_goods_multiplier: float = 0.5
    forged_lockpick_value: float = 5.0
    purse_grab: int = 20               # coins lifted per successful pickpocket of a purse at Pickpocket level 1 ...
    purse_grab_per_level: int = 2      # ... plus this many per level above it
    barter_bonus_per_level: float = 0.015   # better prices per Barter level (sell up, buy down) ...
    barter_bonus_cap: float = 0.75          # ... up to +75% on a sale / -75% on a purchase ...
    barter_value_knee: float = 60.0         # ... scaled by value/(value+knee): trinkets barely move, treasures do
    pantry_restock_days: int = 3            # households top their kitchen tables back up this often (midnight)


@dataclass(frozen=True)
class SkillRewards:
    """Base XP grants at skill level 1 (shrink with level, see ``ProgressionSettings``)."""
    pickpocket: float = 20.0           # plus value-based XP for the item lifted
    smithing: float = 40.0
    smithing_fail: float = 15.0
    lockpicking: float = 75.0          # per point of lock difficulty
    lockpicking_fail: float = 15.0
    stealing: float = 10.0             # plus value-based XP
    barter: float = 5.0                # plus value-based XP
    mining: float = 10.0
    sneak_success: float = 12.0        # a sneak roll passed in front of a watching NPC
    sneak_fail: float = 4.0


@dataclass(frozen=True)
class ProgressionSettings:
    """One rule for every skill: rewards pour in early and dwindle as the skill grows,
    while success odds climb smoothly towards (but never quite reach) certainty.

    * ``xp = base * magnitude / (1 + level_decay * (level - 1))``
    * ``chance = 1 - (1 - base_chance) * chance_decay ** (level - 1)``
    """
    level_decay: float = 0.08          # level 50 earns ~20% of the level-1 reward
    chance_decay: float = 0.955        # level 50: 90% of the way from the base chance to certainty
    chance_floor: float = 0.02
    chance_ceiling: float = 0.99
    value_xp_rate: float = 0.5         # XP per gold of item value (before the level factor)
    value_xp_cap: float = 250.0
    value_xp_floor: float = 0.5        # junk still teaches a sliver


@dataclass(frozen=True)
class PerceptionSettings:
    guard_view_distance: float = 14.0
    civilian_view_distance: float = 8.0
    torch_view_multiplier: float = 1.5
    min_light_view_multiplier: float = 0.4
    hearing_radius_per_noise: float = 10.0
    wake_noise_threshold: float = 0.8
    wall_noise_attenuation: float = 0.25   # noise that gets through walls (player and NPC in different buildings/outside)
    shout_radius: float = 60.0             # how far a cry of "Guards!" carries in the open ...
    shout_wall_attenuation: float = 0.5    # ... and the fraction of that through walls
    scold_cooldown: float = 15.0           # seconds before an NPC repeats the same warning
    scold_freeze_seconds: float = 1.2      # a guard's warning holds the player's attention (controls lock, view turns)
    warning_grace: float = 6.0             # seconds after a warning during which suspicion cannot reach the alarm
    # Suspicion rates are per second of simulated time (alarm at 100).
    heard_suspicion_gain: float = 40.0     # being heard next to an awake NPC: alarm in 2.5 s
    seen_suspicion_gain: float = 80.0      # scaled by visibility / distance
    min_visibility_to_notice: float = 0.15
    suspicion_decay: float = 25.0
    trespass_suspicion_gain: float = 45.0  # extra per second while the player is somewhere they should not be
    torch_light_reach: float = 4.5         # an NPC's torch lights the player up within this distance ...
    torch_lit_visibility: float = 0.5      # ... to at least this visibility
    schedule_override_threshold: float = 50.0
    alarm_threshold: float = 100.0
    view_half_angle_degrees: float = 90.0   # NPCs see a half-space in front of them, never behind


@dataclass(frozen=True)
class StealthSettings:
    """Base odds at skill level 1; ``ProgressionSettings.chance_decay`` lifts them with every level."""
    sneak_check_interval: float = 1.0      # seconds between sneak rolls per watching NPC
    sneak_base_chance: float = 0.45
    sneak_guard_penalty: float = 0.15
    sneak_daylight_penalty: float = 0.2    # scaled by how visible the player is (light, torch, stance)
    sneak_fail_suspicion: float = 35.0
    # Sneak XP per second while crouch-moving: a trickle even alone, more near people who do
    # not notice you (sleepers and backs turned count as "behind"), most right under their noses
    sneak_xp_alone: float = 0.75
    sneak_xp_behind: float = 3.0           # out of the NPC's field of view, or the NPC is asleep
    sneak_xp_in_front: float = 7.0         # inside it (and not spotted)
    sneak_xp_guard_multiplier: float = 1.5
    sneak_xp_range: float = 14.0           # how close counts as "near"
    pickpocket_base_chance: float = 0.45
    pickpocket_asleep_bonus: float = 0.3
    pickpocket_guard_penalty: float = 0.15
    pickpocket_asleep_xp_multiplier: float = 0.5
    pickpocket_guard_xp_multiplier: float = 1.5
    pickpocket_fail_xp_multiplier: float = 0.3
    stealing_base_chance: float = 0.3      # odds a witnessed shelf theft goes unnoticed
    stealing_fail_xp_multiplier: float = 0.4
    lockpick_base_tolerance: float = 15.0
    lockpick_per_level: float = 0.2        # tolerance grows 20% per skill level
    lockpick_min_tolerance: float = 4.0
    lockpick_max_tolerance: float = 45.0
    lockpick_wobble_base: float = 14.0      # degrees of hand wobble at skill level 1 on a simple lock
    lockpick_wobble_per_difficulty: float = 4.0
    lockpick_wobble_per_level: float = 3.0
    sneak_noise_per_level: float = 0.08     # each Sneak level makes the player 8% quieter


@dataclass(frozen=True)
class JusticeSettings:
    fines: Tuple[Tuple[str, float], ...] = (("Pickpocketing", 25.0), ("Lockpicking a door", 30.0), ("Shoplifting", 20.0),
                                             ("Theft", 20.0), ("Trespassing", 15.0), ("Jailbreak", 60.0),
                                             ("Fencing stolen goods", 30.0))
    default_fine: float = 20.0
    gold_per_jail_day: float = 20.0      # sentence length = ceil(unpaid fine / this)
    min_jail_days: int = 1
    max_jail_days: int = 14
    release_hour: int = 6                # prisoners are let out at this hour of their last day
    caught_freeze_seconds: float = 2.0   # controls lock while a guard has the player bang to rights
    jail_fade_delay: float = 2.0         # ... and the fade to the cell waits this long so it sinks in
    release_grace: float = 180.0         # seconds a released prisoner may linger to collect their things
    curfew_ask_interval: float = 8.0     # seconds between a resident's requests to leave at night
    curfew_asks_before_eviction: int = 3


@dataclass(frozen=True)
class CraftingSettings:
    ore_per_batch: int = 1                 # iron ore consumed per forging
    smithing_base_chance: float = 0.4      # odds a forging yields anything at level 1
    lockpicks_min: int = 1                 # yield at level 1 ...
    lockpicks_max: int = 15                # ... and at ``lockpicks_max_level`` and beyond
    lockpicks_max_level: int = 50


@dataclass(frozen=True)
class LightingSettings:
    """Atmosphere and light colours (all linear RGB, intensities ~0..1.5)."""
    sky_day: Color3 = (0.46, 0.66, 0.95)
    sky_dusk: Color3 = (0.85, 0.45, 0.25)
    sky_night: Color3 = (0.02, 0.035, 0.09)     # natural dark blue
    fog_tint: Color3 = (0.7, 0.72, 0.75)
    fog_density_day: float = 0.006       # exp2 fog: barely a haze by day ...
    fog_density_night: float = 0.055     # ... thick darkness at night (about 15 units of visibility)
    sun_color_noon: Color3 = (1.05, 1.0, 0.92)
    sun_color_horizon: Color3 = (1.0, 0.55, 0.3)
    moon_color: Color3 = (0.16, 0.18, 0.26)
    ambient_day: Color3 = (0.38, 0.40, 0.45)
    ambient_night: Color3 = (0.05, 0.055, 0.08)
    torch_color: Color3 = (1.3, 0.9, 0.45)
    lantern_color: Color3 = (1.5, 1.1, 0.62)     # indoor wall lanterns
    candle_color: Color3 = (1.1, 0.8, 0.42)      # table candles
    fire_color: Color3 = (1.6, 0.9, 0.4)         # the smith's forge
    torch_range: float = 11.0
    player_torch_range: float = 14.0
    torch_flicker: float = 0.12
    sun_disc_size: float = 9.0
    moon_disc_size: float = 6.0
    sky_distance: float = 85.0           # billboard distance for the sun/moon (inside the far plane)
    # fixed-function fallback (no GLSL)
    npc_torch_height: float = 1.2
    anvil_material: Color4 = (0.25, 0.25, 0.28, 1.0)
    ambient_day_level: float = 1.0       # perception ambient light (0..1)
    ambient_night_level: float = 0.1


@dataclass(frozen=True)
class HudColors:
    panel: Color4 = (0.08, 0.08, 0.12, 0.85)
    top_bar: Color4 = (0.08, 0.08, 0.12, 0.9)
    prompt_panel: Color4 = (0.08, 0.08, 0.12, 0.95)
    modal_panel: Color4 = (0.05, 0.05, 0.08, 0.96)
    lockpick_panel: Color4 = (0.05, 0.05, 0.08, 0.95)
    white: RGB = (255, 255, 255)
    gold: RGB = (255, 215, 0)
    torch_on: RGB = (255, 200, 100)
    crouch_on: RGB = (150, 255, 150)
    danger: RGB = (255, 120, 120)
    prompt: RGB = (255, 240, 100)
    log_title: RGB = (150, 220, 255)
    trade_heading: RGB = (100, 220, 255)
    selected: RGB = (255, 230, 100)
    sweet_spot_text: RGB = (255, 230, 0)
    stolen_tag: RGB = (255, 70, 70)
    scroll_hint: RGB = (170, 170, 190)
    bubble: Color4 = (0.85, 0.82, 0.7, 0.95)          # speech bubble border
    bubble_fill: Color4 = (0.12, 0.11, 0.14, 0.92)    # speech bubble panel
    bubble_name: RGB = (255, 215, 0)
    bubble_text: RGB = (245, 240, 225)


@dataclass(frozen=True)
class HudLayout:
    """Pixel layout of the HUD, derived from the window size.

    The defaults reproduce the original 1024x768 layout exactly; other window
    sizes keep panels anchored to the edges/centre they were designed around.
    """
    width: int = 1024
    height: int = 768
    top_bar_height: int = 45
    controls_panel: Tuple[int, int, int, int] = field(default=(720, 55, 1014, 275))
    inventory_panel: Tuple[int, int, int, int] = field(default=(10, 580, 350, 750))
    log_panel: Tuple[int, int, int, int] = field(default=(370, 560, 1014, 750))
    trade_panel: Tuple[int, int, int, int] = field(default=(212, 134, 812, 634))
    lockpick_panel: Tuple[int, int, int, int] = field(default=(312, 184, 712, 584))
    prompt_y: int = 420
    lockpick_center: Tuple[int, int] = (512, 430)
    lockpick_radius: float = 90.0
    max_inventory_rows: int = 6
    max_log_rows: int = 6              # wrapped lines shown in the dialogue panel
    log_line_height: int = 22

    @classmethod
    def for_window(cls, width: int, height: int) -> "HudLayout":
        dx = width - 1024
        dy = height - 768
        return cls(
            width=width,
            height=height,
            controls_panel=(720 + dx, 55, 1014 + dx, 275),
            inventory_panel=(10, 580 + dy, 350, 750 + dy),
            log_panel=(370, 560 + dy, 1014 + dx, 750 + dy),
            trade_panel=(212 + dx // 2, 134 + dy // 2, 812 + dx // 2, 634 + dy // 2),
            lockpick_panel=(312 + dx // 2, 184 + dy // 2, 712 + dx // 2, 584 + dy // 2),
            prompt_y=420 + dy // 2,
            lockpick_center=(512 + dx // 2, 430 + dy // 2),
        )

    @property
    def center(self) -> Tuple[int, int]:
        return self.width // 2, self.height // 2


@dataclass(frozen=True)
class GameSettings:
    window: WindowSettings = WindowSettings()
    player: PlayerSettings = PlayerSettings()
    time: TimeSettings = TimeSettings()
    interaction: InteractionSettings = InteractionSettings()
    lockpick: LockpickSettings = LockpickSettings()
    economy: EconomySettings = EconomySettings()
    skill_rewards: SkillRewards = SkillRewards()
    progression: ProgressionSettings = ProgressionSettings()
    perception: PerceptionSettings = PerceptionSettings()
    npc: NPCSettings = NPCSettings()
    navigation: NavigationSettings = NavigationSettings()
    stealth: StealthSettings = StealthSettings()
    crafting: CraftingSettings = CraftingSettings()
    justice: JusticeSettings = JusticeSettings()
    lighting: LightingSettings = LightingSettings()
    hud_colors: HudColors = HudColors()
    asset_dir: str = DEFAULT_ASSET_DIR
    save_file: str = DEFAULT_SAVE_FILE
    echo_messages_to_stdout: bool = True
    max_log_messages: int = 6
    random_seed: Optional[int] = None  # seed for gameplay randomness (lock sweet spots); None = unpredictable

    def hud_layout(self) -> HudLayout:
        return HudLayout.for_window(self.window.width, self.window.height)


DEFAULT_SETTINGS = GameSettings()
