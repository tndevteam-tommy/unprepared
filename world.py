import json
import os
from models import Vector3D, BoundingBox3D, NPC, AIState, ScheduleTask, Item, Player, Door

class WorldManager:
    def __init__(self, notify_callback=None):
        self.simulated_hour = 7
        self.minute_accumulator = 0.0
        self.walls = []
        self.doors = []
        self.npcs = []
        self.anvil_position = Vector3D(-3.0, 0.0, -8.0)
        self.notify = notify_callback
        self.setup_town_geometry()
        self.setup_npcs()

    def setup_town_geometry(self):
        self.walls.append(BoundingBox3D(Vector3D(-25, 0, -25), Vector3D(25, 5, -24)))
        self.walls.append(BoundingBox3D(Vector3D(-25, 0, 24), Vector3D(25, 5, 25)))
        self.walls.append(BoundingBox3D(Vector3D(-25, 0, -25), Vector3D(-24, 5, 25)))
        self.walls.append(BoundingBox3D(Vector3D(24, 0, -25), Vector3D(25, 5, 25)))

        # Shop Building
        self.walls.append(BoundingBox3D(Vector3D(5, 0, -10), Vector3D(15, 4, -9.5)))
        self.walls.append(BoundingBox3D(Vector3D(5, 0, -10), Vector3D(5.5, 4, 0)))
        self.walls.append(BoundingBox3D(Vector3D(14.5, 0, -10), Vector3D(15, 4, 0)))
        self.walls.append(BoundingBox3D(Vector3D(5, 0, -0.5), Vector3D(8.5, 4, 0)))
        self.walls.append(BoundingBox3D(Vector3D(11.5, 0, -0.5), Vector3D(15, 4, 0)))

        # Player Hideout Building
        self.walls.append(BoundingBox3D(Vector3D(-18, 0, 15), Vector3D(-10, 4, 15.5)))
        self.walls.append(BoundingBox3D(Vector3D(-18.5, 0, 5), Vector3D(-18, 4, 15)))
        self.walls.append(BoundingBox3D(Vector3D(-10, 0, 5), Vector3D(-9.5, 4, 15)))
        self.walls.append(BoundingBox3D(Vector3D(-18, 0, 4.5), Vector3D(-14.5, 4, 5)))
        self.walls.append(BoundingBox3D(Vector3D(-11.5, 0, 4.5), Vector3D(-10, 4, 5)))
        
        # Reusable Door entities with hinge positions
        self.doors.append(Door("hideout_door", hinge_position=Vector3D(-14.5, 0.0, 5.0), is_locked=False, key_id="hideout_key"))
        self.doors.append(Door("shop_door", hinge_position=Vector3D(8.5, 0.0, 0.0), is_locked=True, key_id="shop_key"))

    def setup_npcs(self):
        # Shopkeeper Barnaby (Can trade, stocks general goods)
        shopkeeper = NPC("Shopkeeper Barnaby", is_guard=False, is_fence=False, can_trade=True, home_pos=Vector3D(10, 0, -5))
        shopkeeper.inventory = [
            Item("shop_key", "Store Backroom Key", is_key=True, key_door_id="shop_door"),
            Item("bread_1", "Fresh Bread", value=15.0),
            Item("apple_1", "Crisp Apple", value=8.0),
            Item("torch_item", "Portable Torch", value=25.0)
        ]
        shopkeeper.schedule = [
            ScheduleTask(0, 8, Vector3D(10, 0, -5), AIState.SLEEPING, "Barnaby is snoring loudly in bed."),
            ScheduleTask(8, 22, Vector3D(10, 0, -2), AIState.SHOPKEEPING, "Barnaby opened the shop doors for business."),
            ScheduleTask(22, 24, Vector3D(10, 0, -5), AIState.SLEEPING, "Barnaby went home to bed.")
        ]
        self.npcs.append(shopkeeper)

        # Raz the Fence (Can trade, stocks illicit items)
        fence = NPC("Raz the Fence", is_guard=False, is_fence=True, can_trade=True, home_pos=Vector3D(-12, 0, 15))
        fence.inventory = [
            Item("lockpick_pack", "Master Lockpick", value=20.0, is_lockpick=True),
            Item("stolen_ring", "Stolen Gold Ring", value=150.0, is_stolen=True)
        ]
        fence.schedule = [
            ScheduleTask(0, 24, Vector3D(-12, 0, 15), AIState.SHOPKEEPING, "Raz is waiting in the dark alley for illicit trade.")
        ]
        self.npcs.append(fence)

        # Guard Captain Vance (Cannot trade, patrol duty)
        guard = NPC("Guard Captain Vance", is_guard=True, is_fence=False, can_trade=False, home_pos=Vector3D(-5, 0, 10))
        guard.schedule = [
            ScheduleTask(0, 6, Vector3D(-5, 0, 10), AIState.SLEEPING, "Vance is resting in the barracks."),
            ScheduleTask(6, 24, Vector3D(0, 0, 0), AIState.PATROL, "Vance is patrolling the town square.")
        ]
        self.npcs.append(guard)

    def report_crime_to_witnesses(self, crime_name: str, player_pos: Vector3D):
        for npc in self.npcs:
            npc.witness_crime(crime_name, player_pos, self.walls, self.notify)

    def update_time(self, delta_time: float):
        self.minute_accumulator += delta_time * 2.5
        if self.minute_accumulator >= 60.0:
            self.minute_accumulator = 0.0
            self.simulated_hour = (self.simulated_hour + 1) % 24
            
            for door in self.doors:
                if door.door_id == "shop_door":
                    if self.simulated_hour == 8:
                        door.is_locked = False
                        door.is_open = True
                        if self.notify:
                            self.notify("Shopkeeper Barnaby has unlocked and opened the shop for business!")
                    elif self.simulated_hour == 22:
                        door.is_locked = True
                        door.is_open = False
                        if self.notify:
                            self.notify("Shopkeeper Barnaby has locked up the shop for the night.")

            if self.notify:
                self.notify(f"Time Update: {self.simulated_hour:02d}:00 hours")
            for npc in self.npcs:
                npc.update_schedule(self.simulated_hour, self.notify)

    def save_game_state(self, player: Player, filename: str = "savegame.json"):
        save_data = {
            "simulated_hour": self.simulated_hour,
            "player": player.to_dict(),
            "npcs": [npc.to_dict() for npc in self.npcs]
        }
        with open(filename, "w") as f:
            json.dump(save_data, f, indent=4)
        if self.notify:
            self.notify("Game state saved successfully!")

    def load_game_state(self, player: Player, filename: str = "savegame.json") -> bool:
        if not os.path.exists(filename):
            if self.notify:
                self.notify("No save file found!")
            return False
        with open(filename, "r") as f:
            save_data = json.load(f)
        
        self.simulated_hour = save_data.get("simulated_hour", 7)
        player.load_dict(save_data["player"])
        
        npc_data_map = {n["name"]: n for n in save_data.get("npcs", [])}
        for npc in self.npcs:
            if npc.name in npc_data_map:
                npc.load_dict(npc_data_map[npc.name])
        
        if self.notify:
            self.notify("Game state loaded successfully!")
        return True