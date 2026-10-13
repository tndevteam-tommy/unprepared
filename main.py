import sys
import os
import math
import pygame
from pygame.locals import DOUBLEBUF, OPENGL, QUIT, KEYDOWN, MOUSEMOTION, K_w, K_s, K_a, K_d, K_LSHIFT, K_LCTRL, K_e, K_r, K_p, K_1, K_l, K_F5, K_F9, K_LEFT, K_RIGHT, K_SPACE, K_UP, K_DOWN, K_RETURN
from OpenGL.GL import *
from OpenGL.GLU import *

from models import Player, Vector3D, Door, Item
from world import WorldManager

message_log = []

def add_message(msg: str):
    global message_log
    message_log.append(msg)
    if len(message_log) > 6:
        message_log.pop(0)
    print(f"[HUD / DIALOGUE] {msg}")

def generate_default_textures():
    os.makedirs(".", exist_ok=True)
    if not os.path.exists("ground.png"):
        surf = pygame.Surface((64, 64))
        surf.fill((34, 139, 34))
        for x in range(0, 64, 8):
            for y in range(0, 64, 8):
                surf.set_at((x, y), (46, 160, 46))
        pygame.image.save(surf, "ground.png")

    if not os.path.exists("building.png"):
        surf = pygame.Surface((64, 64))
        surf.fill((139, 69, 19))
        for y in range(0, 64, 16):
            pygame.draw.line(surf, (100, 40, 10), (0, y), (64, y), 2)
        pygame.image.save(surf, "building.png")

    if not os.path.exists("wall.png"):
        surf = pygame.Surface((64, 64))
        surf.fill((128, 128, 128))
        for y in range(0, 64, 16):
            pygame.draw.line(surf, (64, 64, 64), (0, y), (64, y), 2)
        pygame.image.save(surf, "wall.png")

    if not os.path.exists("guard.png"):
        surf = pygame.Surface((64, 64))
        surf.fill((200, 30, 30))
        pygame.draw.rect(surf, (220, 200, 50), (24, 10, 16, 44))
        pygame.image.save(surf, "guard.png")

    if not os.path.exists("npc.png"):
        surf = pygame.Surface((64, 64))
        surf.fill((30, 90, 200))
        pygame.draw.rect(surf, (200, 180, 140), (22, 16, 20, 32))
        pygame.image.save(surf, "npc.png")

def load_texture(filename: str) -> int:
    if not os.path.exists(filename):
        generate_default_textures()
    surface = pygame.image.load(filename)
    surface = pygame.transform.flip(surface, False, True)
    image_data = pygame.image.tostring(surface, "RGBA", True)
    width, height = surface.get_size()

    texture_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, image_data)
    return texture_id

def draw_textured_box(min_pt: Vector3D, max_pt: Vector3D, texture_id: int):
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    x1, y1, z1 = min_pt.x, min_pt.y, min_pt.z
    x2, y2, z2 = max_pt.x, max_pt.y, max_pt.z

    faces = [
        ((0.0, 0.0, 1.0), [(x1, y1, z2), (x2, y1, z2), (x2, y2, z2), (x1, y2, z2)], [(0,0), (1,0), (1,1), (0,1)]),
        ((0.0, 0.0, -1.0), [(x2, y1, z1), (x1, y1, z1), (x1, y2, z1), (x2, y2, z1)], [(0,0), (1,0), (1,1), (0,1)]),
        ((-1.0, 0.0, 0.0), [(x1, y1, z1), (x1, y1, z2), (x1, y2, z2), (x1, y2, z1)], [(0,0), (1,0), (1,1), (0,1)]),
        ((1.0, 0.0, 0.0), [(x2, y1, z2), (x2, y1, z1), (x2, y2, z1), (x2, y2, z2)], [(0,0), (1,0), (1,1), (0,1)]),
        ((0.0, 1.0, 0.0), [(x1, y2, z2), (x2, y2, z2), (x2, y2, z1), (x1, y2, z1)], [(0,0), (1,0), (1,1), (0,1)]),
        ((0.0, -1.0, 0.0), [(x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2)], [(0,0), (1,0), (1,1), (0,1)])
    ]

    glBegin(GL_QUADS)
    for normal, vertices, tex_coords in faces:
        glNormal3f(normal[0], normal[1], normal[2])
        for i, vert in enumerate(vertices):
            glTexCoord2f(tex_coords[i][0], tex_coords[i][1])
            glVertex3f(vert[0], vert[1], vert[2])
    glEnd()
    glDisable(GL_TEXTURE_2D)

def draw_ground(texture_id: int):
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    glBegin(GL_QUADS)
    glNormal3f(0.0, 1.0, 0.0)
    glTexCoord2f(0.0, 0.0); glVertex3f(-50.0, 0.0, -50.0)
    glTexCoord2f(10.0, 0.0); glVertex3f(50.0, 0.0, -50.0)
    glTexCoord2f(10.0, 10.0); glVertex3f(50.0, 0.0, 50.0)
    glTexCoord2f(0.0, 10.0); glVertex3f(-50.0, 0.0, 50.0)
    glEnd()
    glDisable(GL_TEXTURE_2D)

def draw_door(door: Door, texture_id: int):
    glPushMatrix()
    glTranslatef(door.hinge_position.x, door.hinge_position.y, door.hinge_position.z)
    if door.is_open:
        glRotatef(90.0, 0.0, 1.0, 0.0)
    
    min_pt = Vector3D(0.0, 0.0, -0.1)
    max_pt = Vector3D(door.width, door.height, 0.1)
    draw_textured_box(min_pt, max_pt, texture_id)
    glPopMatrix()

def get_targeted_interaction(player: Player, doors: list, npcs: list) -> tuple:
    yaw_rad = math.radians(player.rotation_y)
    pitch_rad = math.radians(player.rotation_x)
    
    dir_x = math.cos(pitch_rad) * math.sin(yaw_rad)
    dir_y = math.sin(pitch_rad)
    dir_z = -math.cos(pitch_rad) * math.cos(yaw_rad)

    cam_pos = Vector3D(player.position.x, player.position.y + 1.6, player.position.z)

    for door in doors:
        dist = cam_pos.distance_to(door.hinge_position)
        if dist <= 5.0:
            to_door_x = (door.hinge_position.x + 1.5) - cam_pos.x
            to_door_y = (door.hinge_position.y + 1.5) - cam_pos.y
            to_door_z = door.hinge_position.z - cam_pos.z
            mag = math.sqrt(to_door_x**2 + to_door_y**2 + to_door_z**2)
            if mag > 0:
                to_door_x /= mag; to_door_y /= mag; to_door_z /= mag
                dot = dir_x * to_door_x + dir_y * to_door_y + dir_z * to_door_z
                if dot > 0.6:
                    if not door.is_locked:
                        action = "Close Door" if door.is_open else "Open Door"
                        return "door", door, f"[E] {action}"
                    else:
                        has_key = any(item.is_key and item.key_door_id == door.door_id for item in player.inventory)
                        if has_key:
                            return "door", door, "[E] Unlock with Key"
                        else:
                            has_pick = any(item.is_lockpick for item in player.inventory)
                            if has_pick:
                                return "door", door, "[E] Pick Lock"
                            else:
                                return "door", door, "[Locked]"

    for npc in npcs:
        dist = cam_pos.distance_to(npc.position)
        if dist <= 3.0:
            to_npc_x = npc.position.x - cam_pos.x
            to_npc_y = (npc.position.y + 1.0) - cam_pos.y
            to_npc_z = npc.position.z - cam_pos.z
            mag = math.sqrt(to_npc_x**2 + to_npc_y**2 + to_npc_z**2)
            if mag > 0:
                to_npc_x /= mag; to_npc_y /= mag; to_npc_z /= mag
                dot = dir_x * to_npc_x + dir_y * to_npc_y + dir_z * to_npc_z
                if dot > 0.6:
                    label = f"[E] Talk / Trade with {npc.name}" if npc.can_trade else f"[E] Talk to {npc.name}"
                    return "npc", npc, label

    return None, None, None

def render_hud_overlay(player: Player, simulated_hour: int, in_lockpicking: bool, in_trade_menu: bool, active_merchant, trade_selection: int, pick_angle: float, sweet_spot: float, interaction_prompt: str, font, font_small):
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(0, 1024, 768, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    
    # RESET MATERIAL EMISSIONS & COLOR STATE BEFORE UI RENDERING
    glMaterialfv(GL_FRONT_AND_BACK, GL_EMISSION, [0.0, 0.0, 0.0, 1.0])
    glColor4f(1.0, 1.0, 1.0, 1.0)

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    # Top Bar Background Panel
    glBegin(GL_QUADS)
    glColor4f(0.08, 0.08, 0.12, 0.9)
    glVertex2f(0, 0); glVertex2f(1024, 0); glVertex2f(1024, 45); glVertex2f(0, 45)
    glEnd()

    def draw_text_surface(text, x, y, f=font, color=(255, 255, 255)):
        # Render text with Pygame surface using transparent background
        surf = f.render(text, True, color)
        w, h = surf.get_size()
        data = pygame.image.tostring(surf, "RGBA", True)
        
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex)
        
        # CRITICAL FIX: Force color to 100% white before drawing texture so texture color is not modulated by black
        glColor4f(1.0, 1.0, 1.0, 1.0)
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(x, y)
        glTexCoord2f(1, 1); glVertex2f(x + w, y)
        glTexCoord2f(1, 0); glVertex2f(x + w, y + h)
        glTexCoord2f(0, 0); glVertex2f(x, y + h)
        glEnd()
        
        glDisable(GL_TEXTURE_2D)
        glDeleteTextures([tex])

    # Solid White & High-Contrast Top Bar Text
    draw_text_surface(f"Time: {simulated_hour:02d}:00", 20, 10, font_small, (255, 255, 255))
    draw_text_surface(f"Gold: {player.gold:.1f}g", 160, 10, font_small, (255, 215, 0))
    draw_text_surface(f"Torch [1]: {'ON' if player.has_lit_torch else 'OFF'}", 280, 10, font_small, (255, 200, 100) if player.has_lit_torch else (255, 255, 255))
    draw_text_surface(f"Stance [Ctrl]: {'Crouching' if player.is_crouching else 'Standing'}", 460, 10, font_small, (150, 255, 150) if player.is_crouching else (255, 255, 255))

    if interaction_prompt and not in_trade_menu:
        prompt_color = (255, 120, 120) if "Locked" in interaction_prompt else (255, 240, 100)
        surf_p = font.render(interaction_prompt, True, prompt_color)
        pw, ph = surf_p.get_size()
        px_pos = 512 - (pw // 2)
        py_pos = 420
        
        glBegin(GL_QUADS)
        glColor4f(0.08, 0.08, 0.12, 0.95)
        glVertex2f(px_pos - 12, py_pos - 6)
        glVertex2f(px_pos + pw + 12, py_pos - 6)
        glVertex2f(px_pos + pw + 12, py_pos + ph + 6)
        glVertex2f(px_pos - 12, py_pos + ph + 6)
        glEnd()
        
        draw_text_surface(interaction_prompt, px_pos, py_pos, font, prompt_color)

    # Crosshair
    glLineWidth(2.0)
    glBegin(GL_LINES)
    glColor3f(1.0, 1.0, 1.0)
    glVertex2f(506, 384); glVertex2f(518, 384)
    glVertex2f(512, 378); glVertex2f(512, 390)
    glEnd()

    # Controls Panel Background
    glBegin(GL_QUADS)
    glColor4f(0.08, 0.08, 0.12, 0.85)
    glVertex2f(720, 55); glVertex2f(1014, 55); glVertex2f(1014, 275); glVertex2f(720, 275)
    glEnd()

    controls = [
        "CONTROLS:",
        "[W/A/S/D] Move | [Mouse] Look",
        "[Left Shift] Sprint | [Left Ctrl] Crouch",
        "[1] Toggle Torch | [E] Interact / Trade",
        "[R] Forge Lockpick at Anvil",
        "[F5] Quick Save | [F9] Quick Load"
    ]
    for idx, c_text in enumerate(controls):
        color = (255, 215, 0) if idx == 0 else (255, 255, 255)
        draw_text_surface(c_text, 730, 65 + (idx * 22), font_small, color)

    # Inventory Panel Background
    glBegin(GL_QUADS)
    glColor4f(0.08, 0.08, 0.12, 0.85)
    glVertex2f(10, 580); glVertex2f(350, 580); glVertex2f(350, 750); glVertex2f(10, 750)
    glEnd()
    draw_text_surface("PLAYER INVENTORY:", 20, 590, font_small, (255, 215, 0))
    for idx, item in enumerate(player.inventory[:6]):
        stolen_tag = " [STOLEN]" if item.is_stolen else ""
        item_text = f"- {item.name}{stolen_tag} ({item.value}g)"
        color = (255, 120, 120) if item.is_stolen else (255, 255, 255)
        draw_text_surface(item_text, 20, 620 + (idx * 20), font_small, color)

    # Dialogue Log Panel Background
    glBegin(GL_QUADS)
    glColor4f(0.08, 0.08, 0.12, 0.85)
    glVertex2f(370, 580); glVertex2f(704, 580); glVertex2f(704, 750); glVertex2f(370, 750)
    glEnd()
    draw_text_surface("WORLD DIALOGUE & EVENTS:", 380, 590, font_small, (150, 220, 255))
    for idx, msg in enumerate(message_log[-5:]):
        draw_text_surface(msg[:45], 380, 620 + (idx * 22), font_small, (255, 255, 255))

    # -------------------------------------------------------------
    # TRADE MENU INTERFACE
    # -------------------------------------------------------------
    if in_trade_menu and active_merchant:
        glBegin(GL_QUADS)
        glColor4f(0.05, 0.05, 0.08, 0.96)
        glVertex2f(212, 134); glVertex2f(812, 134); glVertex2f(812, 634); glVertex2f(212, 634)
        glEnd()

        draw_text_surface(f"TRADING WITH: {active_merchant.name}", 240, 150, font, (255, 215, 0))
        draw_text_surface("Use [UP/DOWN] to select item, [ENTER] to Buy/Sell, [ESC] to Exit", 240, 185, font_small, (255, 255, 255))

        draw_text_surface("MERCHANT STOCK (BUY):", 240, 230, font_small, (100, 220, 255))
        for idx, item in enumerate(active_merchant.inventory):
            prefix = "> " if trade_selection == idx else "  "
            color = (255, 230, 100) if trade_selection == idx else (255, 255, 255)
            draw_text_surface(f"{prefix}{item.name} - {item.value}g", 250, 260 + (idx * 25), font_small, color)

        draw_text_surface("YOUR INVENTORY (SELL):", 520, 230, font_small, (100, 220, 255))
        for idx, item in enumerate(player.inventory):
            sel_idx = len(active_merchant.inventory) + idx
            prefix = "> " if trade_selection == sel_idx else "  "
            color = (255, 120, 120) if item.is_stolen else ((255, 230, 100) if trade_selection == sel_idx else (255, 255, 255))
            stolen_tag = " [STOLEN]" if item.is_stolen else ""
            sell_val = item.value * 0.5 if item.is_stolen else item.value
            draw_text_surface(f"{prefix}{item.name}{stolen_tag} ({sell_val}g)", 530, 260 + (idx * 25), font_small, color)

    # -------------------------------------------------------------
    # LOCKPICKING MINI-GAME INTERFACE
    # -------------------------------------------------------------
    if in_lockpicking:
        glBegin(GL_QUADS)
        glColor4f(0.05, 0.05, 0.08, 0.95)
        glVertex2f(312, 184); glVertex2f(712, 184); glVertex2f(712, 584); glVertex2f(312, 584)
        glEnd()

        draw_text_surface("LOCKPICKING MINI-GAME", 365, 200, font, (255, 215, 0))
        draw_text_surface("Rotate pick with [LEFT / RIGHT] arrows", 335, 240, font_small, (255, 255, 255))
        draw_text_surface("Press [SPACE] to turn lock cylinder", 355, 270, font_small, (255, 255, 255))

        center_x, center_y = 512, 430
        radius = 90.0

        angle_diff = abs(pick_angle - sweet_spot)
        is_aligned = angle_diff <= 15.0
        glow_color = (1.0, 0.9, 0.1) if is_aligned else (0.4, 0.4, 0.5)

        glLineWidth(6.0 if is_aligned else 3.0)
        glBegin(GL_LINE_LOOP)
        for i in range(36):
            rad = math.radians(i * 10)
            glColor3f(glow_color[0], glow_color[1], glow_color[2])
            glVertex2f(center_x + math.cos(rad) * radius, center_y + math.sin(rad) * radius)
        glEnd()

        sweet_rad = math.radians(sweet_spot)
        sx = center_x + math.cos(sweet_rad) * radius
        sy = center_y + math.sin(sweet_rad) * radius
        glPointSize(10.0)
        glBegin(GL_POINTS)
        glColor3f(1.0, 0.8, 0.0)
        glVertex2f(sx, sy)
        glEnd()

        glLineWidth(5.0)
        glBegin(GL_LINES)
        rad = math.radians(pick_angle)
        px = center_x + math.cos(rad) * radius
        py = center_y + math.sin(rad) * radius
        glColor3f(0.9, 0.6, 0.1) if is_aligned else (0.8, 0.8, 0.8)
        glVertex2f(center_x, center_y)
        glVertex2f(px, py)
        glEnd()

        if is_aligned:
            draw_text_surface("✨ SWEET SPOT FOUND! Press [SPACE]! ✨", 355, 535, font_small, (255, 230, 0))

    glDisable(GL_BLEND)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()

def configure_torch_light(light_slot, x, y, z):
    glEnable(light_slot)
    glLightfv(light_slot, GL_POSITION, [x, y, z, 1.0])
    glLightfv(light_slot, GL_DIFFUSE, [8.0, 5.5, 2.0, 1.0])
    glLightfv(light_slot, GL_SPECULAR, [8.0, 5.5, 2.0, 1.0])
    glLightf(light_slot, GL_CONSTANT_ATTENUATION, 1.0)
    glLightf(light_slot, GL_LINEAR_ATTENUATION, 0.02)
    glLightf(light_slot, GL_QUADRATIC_ATTENUATION, 0.002)

def main():
    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont("Arial", 20, bold=True)
    font_small = pygame.font.SysFont("Arial", 16)

    width, height = 1024, 768
    screen = pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
    pygame.display.set_caption("KCD2 Theft Prototype - Fixed Text Coloring")

    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)

    glViewport(0, 0, width, height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60, (width / height), 0.1, 100.0)
    glMatrixMode(GL_MODELVIEW)
    
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT1)
    glEnable(GL_LIGHT2)
    glEnable(GL_LIGHT3)
    glEnable(GL_LIGHT4)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    
    glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)

    world = WorldManager(notify_callback=add_message)
    player = Player(Vector3D(-12.0, 1.0, -6.0))

    in_lockpicking = False
    in_trade_menu = False
    active_merchant = None
    trade_selection = 0
    lock_sweet_spot = 45.0
    lock_pick_angle = 0.0
    target_type = None
    target_obj = None

    clock = pygame.time.Clock()

    generate_default_textures()
    tex_ground = load_texture("ground.png")
    tex_building = load_texture("building.png")
    tex_wall = load_texture("wall.png")
    tex_guard = load_texture("guard.png")
    tex_npc = load_texture("npc.png")

    add_message("Tutorial started: Explore merchants, trade wares, and open doors!")

    running = True
    while running:
        delta_time = clock.tick(60) / 1000.0
        is_moving = False
        is_sprinting = False

        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == MOUSEMOTION and not in_lockpicking and not in_trade_menu:
                dx, dy = event.rel
                player.rotation_y += dx * 0.15
                player.rotation_x -= dy * 0.15
                player.rotation_x = max(-89.0, min(89.0, player.rotation_x))
            elif event.type == KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if in_lockpicking:
                        in_lockpicking = False
                    elif in_trade_menu:
                        in_trade_menu = False
                        active_merchant = None
                        pygame.mouse.set_visible(False)
                        pygame.event.set_grab(True)
                    else:
                        pygame.mouse.set_visible(True)
                        pygame.event.set_grab(False)
                        running = False
                elif event.key == K_F5:
                    world.save_game_state(player)
                elif event.key == K_F9:
                    world.load_game_state(player)
                elif event.key == K_e:
                    if in_trade_menu:
                        in_trade_menu = False
                        active_merchant = None
                        pygame.mouse.set_visible(False)
                        pygame.event.set_grab(True)
                    elif target_type == "door" and target_obj:
                        door = target_obj
                        if not door.is_locked:
                            door.is_open = not door.is_open
                            state_str = "opened" if door.is_open else "closed"
                            add_message(f"You {state_str} the door.")
                        else:
                            has_key = any(item.is_key and item.key_door_id == door.door_id for item in player.inventory)
                            if has_key:
                                door.is_locked = False
                                door.is_open = True
                                add_message(f"Unlocked and opened {door.door_id} with key! 🗝️")
                            else:
                                has_pick = any(item.is_lockpick for item in player.inventory)
                                if has_pick:
                                    in_lockpicking = True
                                    world.report_crime_to_witnesses("Lockpicking a door", player.position)
                                    add_message("Started lockpicking mini-game on door.")
                                else:
                                    add_message("Door is locked! You need a key or lockpick.")
                    elif target_type == "npc" and target_obj:
                        npc = target_obj
                        npc.interact(notify_callback=add_message)
                        if npc.can_trade:
                            in_trade_menu = True
                            active_merchant = npc
                            trade_selection = 0
                            pygame.mouse.set_visible(True)
                            pygame.event.set_grab(False)
                elif event.key == K_1:
                    player.has_lit_torch = not player.has_lit_torch
                    add_message(f"Torch is now {'LIT' if player.has_lit_torch else 'EXTINGUISHED'}.")
                elif event.key == K_LCTRL:
                    player.is_crouching = not player.is_crouching
                    add_message(f"Stance: {'Crouching' if player.is_crouching else 'Standing'}.")
                elif event.key == K_p:
                    world.report_crime_to_witnesses("Pickpocketing", player.position)
                    for npc in world.npcs:
                        if player.position.distance_to(npc.position) <= 2.5:
                            player.skills.add_xp(__import__('models').SkillType.PICKPOCKET, 50.0, notify_callback=add_message)
                            add_message(f"Successfully pickpocketed {npc.name}!")
                elif event.key == K_r:
                    if player.position.distance_to(world.anvil_position) <= 3.0:
                        player.inventory.append(Item("lockpick_new", "Iron Lockpick", value=5.0, is_lockpick=True))
                        player.skills.add_xp(__import__('models').SkillType.SMITHING, 40.0, notify_callback=add_message)
                        add_message("Successfully forged a new lockpick at the anvil! 🔨")
                    else:
                        add_message("You must be near the blacksmith's anvil to forge lockpicks.")
                
                if in_trade_menu and active_merchant:
                    total_items = len(active_merchant.inventory) + len(player.inventory)
                    if event.key == K_UP:
                        trade_selection = (trade_selection - 1) % max(1, total_items)
                    elif event.key == K_DOWN:
                        trade_selection = (trade_selection + 1) % max(1, total_items)
                    elif event.key == K_RETURN:
                        if trade_selection < len(active_merchant.inventory):
                            item_to_buy = active_merchant.inventory[trade_selection]
                            if player.gold >= item_to_buy.value:
                                player.gold -= item_to_buy.value
                                player.inventory.append(item_to_buy)
                                active_merchant.inventory.pop(trade_selection)
                                add_message(f"Bought {item_to_buy.name} for {item_to_buy.value}g.")
                            else:
                                add_message("Not enough gold to buy this item!")
                        else:
                            p_idx = trade_selection - len(active_merchant.inventory)
                            if p_idx < len(player.inventory):
                                item_to_sell = player.inventory[p_idx]
                                if item_to_sell.is_stolen and not active_merchant.is_fence:
                                    add_message(f"({active_merchant.name}): \"That {item_to_sell.name} is stolen! Guards!\"")
                                    active_merchant.state = AIState.REPORTING
                                    in_trade_menu = False
                                    pygame.mouse.set_visible(False)
                                    pygame.event.set_grab(True)
                                else:
                                    sell_price = item_to_sell.value * 0.5 if item_to_sell.is_stolen else item_to_sell.value
                                    player.gold += sell_price
                                    player.inventory.pop(p_idx)
                                    active_merchant.inventory.append(item_to_sell)
                                    add_message(f"Sold {item_to_sell.name} for {sell_price:.1f}g.")

                if in_lockpicking:
                    if event.key == K_LEFT:
                        lock_pick_angle = (lock_pick_angle - 10.0) % 360.0
                    elif event.key == K_RIGHT:
                        lock_pick_angle = (lock_pick_angle + 10.0) % 360.0
                    elif event.key == K_SPACE:
                        angle_diff = abs(lock_pick_angle - lock_sweet_spot)
                        if angle_diff <= 15.0:
                            if target_type == "door" and target_obj:
                                target_obj.is_locked = False
                                target_obj.is_open = True
                            add_message("SUCCESS! Lock successfully bypassed! 🗝️")
                            player.skills.add_xp(__import__('models').SkillType.LOCKPICKING, 75.0, notify_callback=add_message)
                            in_lockpicking = False
                        else:
                            add_message("SNAP! Your lockpick broke against the mechanism! 💥")

        if not in_lockpicking and not in_trade_menu:
            keys = pygame.key.get_pressed()
            move_speed = 4.0 * delta_time
            if keys[K_LSHIFT]:
                move_speed *= 1.8
                is_sprinting = True

            yaw_rad = math.radians(player.rotation_y)
            forward_x = math.sin(yaw_rad)
            forward_z = -math.cos(yaw_rad)
            right_x = math.cos(yaw_rad)
            right_z = math.sin(yaw_rad)

            if keys[K_w]:
                player.position.x += forward_x * move_speed
                player.position.z += forward_z * move_speed
                is_moving = True
            if keys[K_s]:
                player.position.x -= forward_x * move_speed
                player.position.z -= forward_z * move_speed
                is_moving = True
            if keys[K_a]:
                player.position.x -= right_x * move_speed
                player.position.z -= right_z * move_speed
                is_moving = True
            if keys[K_d]:
                player.position.x += right_x * move_speed
                player.position.z += right_z * move_speed
                is_moving = True

        world.update_time(delta_time)
        ambient_light = 0.1 if (world.simulated_hour < 6 or world.simulated_hour > 20) else 1.0
        
        for npc in world.npcs:
            npc.evaluate_perception(player, ambient_light, is_moving, is_sprinting, world.walls, world.simulated_hour, notify_callback=add_message)

        target_type, target_obj, interaction_prompt = get_targeted_interaction(player, world.doors, world.npcs)

        # Sun Lighting
        sun_angle = (world.simulated_hour / 24.0) * 2.0 * math.pi
        sun_x = math.cos(sun_angle) * 50.0
        sun_y = math.sin(sun_angle) * 50.0
        sun_z = 20.0
        glLightfv(GL_LIGHT0, GL_POSITION, [sun_x, sun_y, sun_z, 1.0])

        if 6 <= world.simulated_hour < 18:
            glClearColor(0.4, 0.6, 0.9, 1.0)
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [30.0, 28.0, 24.0, 1.0])
            glLightfv(GL_LIGHT0, GL_SPECULAR, [20.0, 20.0, 20.0, 1.0])
            glLightfv(GL_LIGHT0, GL_AMBIENT, [4.0, 4.0, 4.5, 1.0])
        elif 18 <= world.simulated_hour < 20 or 5 <= world.simulated_hour < 6:
            glClearColor(0.6, 0.3, 0.2, 1.0)
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [35.0, 18.0, 6.0, 1.0])
            glLightfv(GL_LIGHT0, GL_SPECULAR, [20.0, 10.0, 4.0, 1.0])
            glLightfv(GL_LIGHT0, GL_AMBIENT, [3.0, 2.0, 1.5, 1.0])
        else:
            glClearColor(0.02, 0.02, 0.06, 1.0)
            glLightfv(GL_LIGHT0, GL_DIFFUSE, [2.0, 2.0, 4.0, 1.0])
            glLightfv(GL_LIGHT0, GL_SPECULAR, [1.5, 1.5, 3.0, 1.0])
            glLightfv(GL_LIGHT0, GL_AMBIENT, [0.8, 0.8, 1.5, 1.0])

        # Player Torch
        if player.has_lit_torch:
            configure_torch_light(GL_LIGHT1, player.position.x, player.position.y + 1.0, player.position.z)
        else:
            glDisable(GL_LIGHT1)

        # NPC Torches
        for idx, npc in enumerate(world.npcs):
            light_slot = GL_LIGHT2 + idx
            if npc.has_torch:
                configure_torch_light(light_slot, npc.position.x, npc.position.y + 1.2, npc.position.z)
            else:
                glDisable(light_slot)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        pitch_rad = math.radians(player.rotation_x)
        yaw_rad = math.radians(player.rotation_y)

        dir_x = math.cos(pitch_rad) * math.sin(yaw_rad)
        dir_y = math.sin(pitch_rad)
        dir_z = -math.cos(pitch_rad) * math.cos(yaw_rad)

        gluLookAt(
            player.position.x, player.position.y + 1.6, player.position.z,
            player.position.x + dir_x, player.position.y + 1.6 + dir_y, player.position.z + dir_z,
            0.0, 1.0, 0.0
        )

        draw_ground(tex_ground)

        for i, wall in enumerate(world.walls):
            texture = tex_wall if i < 4 else tex_building
            draw_textured_box(wall.min_point, wall.max_point, texture)

        # Render Anvil
        anvil_min = Vector3D(world.anvil_position.x - 0.5, world.anvil_position.y, world.anvil_position.z - 0.4)
        anvil_max = Vector3D(world.anvil_position.x + 0.5, world.anvil_position.y + 0.8, world.anvil_position.z + 0.4)
        glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, [0.25, 0.25, 0.28, 1.0])
        draw_textured_box(anvil_min, anvil_max, tex_wall)

        # Draw Doors
        for door in world.doors:
            draw_door(door, tex_building)

        for npc in world.npcs:
            texture = tex_guard if npc.is_guard else tex_npc
            box_min = Vector3D(npc.position.x - 0.4, npc.position.y, npc.position.z - 0.4)
            box_max = Vector3D(npc.position.x + 0.4, npc.position.y + 1.8, npc.position.z + 0.4)
            draw_textured_box(box_min, box_max, texture)

            if npc.has_torch:
                torch_min = Vector3D(npc.position.x + 0.4, npc.position.y + 0.9, npc.position.z)
                torch_max = Vector3D(npc.position.x + 0.6, npc.position.y + 1.2, npc.position.z + 0.2)
                
                glMaterialfv(GL_FRONT, GL_EMISSION, [4.0, 2.5, 0.8, 1.0])
                draw_textured_box(torch_min, torch_max, tex_building)
                glMaterialfv(GL_FRONT, GL_EMISSION, [0.0, 0.0, 0.0, 1.0])

        render_hud_overlay(player, world.simulated_hour, in_lockpicking, in_trade_menu, active_merchant, trade_selection, lock_pick_angle, lock_sweet_spot, interaction_prompt, font, font_small)

        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()