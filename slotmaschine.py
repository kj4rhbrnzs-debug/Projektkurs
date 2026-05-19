#!/usr/bin/env python3
# Slotmaschine – läuft auf Raspberry Pi (mit GPIO) und Windows/Linux (ohne GPIO)

import os
import json
import random
import time
import threading
import pygame

# Grafik-Fix für Raspberry Pi 
if os.name != 'nt':
    os.environ['SDL_VIDEO_X11_NETWM_BYPASS_COMPOSITOR'] = '0'

# GPIO einrichten
USE_GPIO = True
try:
    import RPi.GPIO as GPIO
except ImportError:
    USE_GPIO = False
    print(" RPi.GPIO nicht gefunden – GPIO deaktiviert (Windows-Testmodus aktiv)")

# Pins und Konstanten
COIN_PIN = 25
LEVER_PIN = 20  
RESET_PIN = 26

# Pfade relativ zum Skript-Verzeichnis
SCRIPT_DIR: str = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(SCRIPT_DIR, "slot_assets")
DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
START_CREDITS = 10
WIN_REWARD = 4

CREDIT_PER_COIN = 1
DEFAULT_SYMBOL_COUNT = 5
SCREEN_W, SCREEN_H = 800, 480
FPS = 60
is_fullscreen = False

# Daten speichern/laden
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            return json.load(open(DATA_FILE))
        except:
            pass
    return {"credits": START_CREDITS, "best": START_CREDITS}

def save_data(d):
    json.dump(d, open(DATA_FILE, "w"))

data_lock = threading.Lock()
data = load_data()
event_queue = []

# GPIO konfigurieren
if USE_GPIO:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(COIN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(LEVER_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(RESET_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def coin_cb(ch): event_queue.append("COIN")
    def lever_cb(ch): event_queue.append("LEVER")
    def reset_cb(ch): event_queue.append("RESET")

    GPIO.add_event_detect(COIN_PIN, GPIO.FALLING, callback=coin_cb, bouncetime=200)
    GPIO.add_event_detect(LEVER_PIN, GPIO.FALLING, callback=lever_cb, bouncetime=200)
    GPIO.add_event_detect(RESET_PIN, GPIO.FALLING, callback=reset_cb, bouncetime=200)

# Pygame Setup
pygame.init()
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption("Slotmaschine")
clock = pygame.time.Clock()
font_big = pygame.font.SysFont(None, 72)
font_small = pygame.font.SysFont(None, 36)
font_title = pygame.font.SysFont("Avenir Next", 46, bold=True)
font_label = pygame.font.SysFont("Avenir Next", 26)
font_value = pygame.font.SysFont("Avenir Next", 32, bold=True)
font_hint = pygame.font.SysFont("Avenir Next", 22)

# Symbole laden: bevorzugt alle Bilddateien aus slot_assets, sonst Platzhalter
symbols = []
symbol_colors = [(220, 50, 50), (255, 200, 0), (255, 140, 0), (150, 100, 200), (0, 200, 255)]
image_exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

if os.path.isdir(ASSET_DIR):
    asset_files = sorted(
        f for f in os.listdir(ASSET_DIR)
        if f.lower().endswith(image_exts)
    )
    for filename in asset_files:
        path = os.path.join(ASSET_DIR, filename)
        try:
            symbols.append(pygame.image.load(path).convert_alpha())
        except pygame.error:
            pass

if not symbols:
    for i in range(DEFAULT_SYMBOL_COUNT):
        surf = pygame.Surface((100, 100))
        surf.fill(symbol_colors[i % len(symbol_colors)])
        pygame.draw.rect(surf, (255, 255, 255), (2, 2, 96, 96), 3)
        symbols.append(surf)

# Reels und Status
reels = [0,1,2]
is_spinning = False
current_message = ""
show_blink = False

def toggle_fullscreen():
    global screen, SCREEN_W, SCREEN_H, is_fullscreen
    is_fullscreen = not is_fullscreen
    if is_fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode((800, 480))
    SCREEN_W, SCREEN_H = screen.get_size()

# Bildschirm zeichnen (OHNE display.flip() - das macht jetzt die Hauptschleife)
def draw_screen(message="", blink=False):
    # Sanfter vertikaler Verlauf statt flachem Hintergrund
    top = (9, 14, 28)
    bottom = (30, 19, 47)
    for y in range(SCREEN_H):
        t = y / max(1, SCREEN_H - 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
        pygame.draw.line(screen, color, (0, y), (SCREEN_W, y))

    # Dezente Hintergrundakzente (responsiv zur aktuellen Auflösung)
    c1_pos = (int(SCREEN_W * 0.13), int(SCREEN_H * 0.22))
    c2_pos = (int(SCREEN_W * 0.88), int(SCREEN_H * 0.84))
    c1_radius = max(90, int(min(SCREEN_W, SCREEN_H) * 0.18))
    c2_radius = max(130, int(min(SCREEN_W, SCREEN_H) * 0.26))
    pygame.draw.circle(screen, (26, 58, 96), c1_pos, c1_radius)
    pygame.draw.circle(screen, (58, 36, 92), c2_pos, c2_radius)
    
    with data_lock:
        c = data["credits"]
        b = data["best"]
    
    header_rect = pygame.Rect(24, 18, SCREEN_W - 48, 88)
    pygame.draw.rect(screen, (16, 24, 44), header_rect, border_radius=16)
    pygame.draw.rect(screen, (80, 122, 192), header_rect, 2, border_radius=16)

    title = font_title.render("SLOTMASCHINE", True, (203, 237, 255))
    cred_lbl = font_hint.render("CREDITS", True, (129, 186, 240))
    best_lbl = font_hint.render("BEST", True, (129, 186, 240))
    cred_txt = font_value.render(str(c), True, (131, 255, 201))
    best_txt = font_value.render(str(b), True, (255, 225, 132))

    screen.blit(title, (SCREEN_W // 2 - title.get_width() // 2, 34))
    screen.blit(cred_lbl, (44, 30))
    screen.blit(cred_txt, (44, 56))
    screen.blit(best_lbl, (SCREEN_W - 44 - best_lbl.get_width(), 30))
    screen.blit(best_txt, (SCREEN_W - 44 - best_txt.get_width(), 56))
    
    # Responsive Skalierung für verschiedene Auflösungen/Fullscreen
    w = min(int(SCREEN_W * 0.19), int(SCREEN_H * 0.34))
    w = max(140, w)
    h = w
    gap = max(22, int(w * 0.22))
    frame_margin = max(5, int(w * 0.035))
    total_reel_width = 3 * w + 2 * gap
    start_x = (SCREEN_W - total_reel_width) // 2
    reel_top = (SCREEN_H - h) // 2 - 10

    machine_pad_x = max(28, int(w * 0.24))
    machine_pad_top = max(20, int(w * 0.18))
    machine_pad_bottom = max(32, int(w * 0.26))
    machine_rect = pygame.Rect(
        start_x - machine_pad_x,
        reel_top - machine_pad_top,
        total_reel_width + machine_pad_x * 2,
        h + machine_pad_top + machine_pad_bottom
    )
    pygame.draw.rect(screen, (20, 29, 54), machine_rect, border_radius=18)
    pygame.draw.rect(screen, (89, 137, 220), machine_rect, 3, border_radius=18)
    pygame.draw.line(
        screen, (120, 172, 245),
        (machine_rect.left + 14, machine_rect.top + 12),
        (machine_rect.right - 14, machine_rect.top + 12), 2
    )
    
    for i, idx in enumerate(reels):
        x = start_x + i * (w + gap)
        y = reel_top
        shadow_rect = pygame.Rect(x - frame_margin + 2, y - frame_margin + 4, w + 2 * frame_margin, h + 2 * frame_margin)
        pygame.draw.rect(screen, (8, 11, 22), shadow_rect, border_radius=12)
        pygame.draw.rect(screen, (23, 33, 62), (x - frame_margin, y - frame_margin, w + 2*frame_margin, h + 2*frame_margin), 0, border_radius=12)
        pygame.draw.rect(screen, (93, 143, 231), (x - frame_margin, y - frame_margin, w + 2*frame_margin, h + 2*frame_margin), 3, border_radius=12)
        pygame.draw.rect(screen, (9, 12, 24), (x, y, w, h), 0, border_radius=8)
        
        img = pygame.transform.smoothscale(symbols[idx], (w - 10, h - 10))
        screen.blit(img, (x + 5, y + 5))
        
        if blink and (pygame.time.get_ticks() // 200) % 2 == 0:
            pygame.draw.rect(screen, (255, 243, 133), (x - frame_margin, y - frame_margin, w + 2*frame_margin, h + 2*frame_margin), 5, border_radius=12)
    
    status_rect = pygame.Rect(24, SCREEN_H - 62, SCREEN_W - 48, 38)
    pygame.draw.rect(screen, (16, 24, 44), status_rect, border_radius=10)
    pygame.draw.rect(screen, (60, 95, 151), status_rect, 2, border_radius=10)

    if message:
        if not blink or (pygame.time.get_ticks() // 300) % 2 == 0:
            msg = font_big.render(message, True, (117, 255, 159))
            shadow = font_big.render(message, True, (35, 87, 54))
            msg_y = status_rect.top - msg.get_height() - 18
            screen.blit(shadow, (SCREEN_W//2 - msg.get_width()//2 + 2, msg_y + 2))
            screen.blit(msg, (SCREEN_W//2 - msg.get_width()//2, msg_y))
    else:
        hint = font_hint.render("C Coin   L Lever   R Reset", True, (173, 191, 222))
        screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, SCREEN_H - 54))

# Spin Animation
def spin_animation(final_reels):
    global reels
    start_time = time.time()
    durations = [3.1, 3.9, 4.8]
    running = [True, True, True]
    last_step_time = [0.0, 0.0, 0.0]
    # Jede Rolle minimal anders: startet schnell und bremst progressiv ab.
    min_step = [0.048, 0.052, 0.056]
    max_step = [0.130, 0.140, 0.150]

    while any(running):
        now = time.time()
        for i in range(3):
            if running[i]:
                elapsed = now - start_time
                if elapsed < durations[i]:
                    progress = elapsed / durations[i]
                    step_interval = min_step[i] + (max_step[i] - min_step[i]) * (progress ** 1.7)
                    elapsed_since = now - last_step_time[i]
                    steps = int(elapsed_since / step_interval)
                    if steps > 0:
                        reels[i] = (reels[i] + steps) % len(symbols)
                        last_step_time[i] += steps * step_interval
                else:
                    reels[i] = final_reels[i]
                    running[i] = False
        time.sleep(0.004)

# Spin Logik
def spin():
    global reels, is_spinning, current_message, show_blink
    is_spinning = True
    current_message = ""
    show_blink = False

    choices = list(range(len(symbols)))
    final_reels = random.choices(choices, k=3)

    if random.random() < 0.20:
        sym = random.choice(choices)
        final_reels = [sym, sym, sym]

    spin_animation(final_reels)
    time.sleep(0.5)

    if final_reels[0] == final_reels[1] == final_reels[2]:
        with data_lock:
            data["credits"] += WIN_REWARD
            if data["credits"] > data["best"]:
                data["best"] = data["credits"]
            save_data(data)

        current_message = " GEWONNEN! "
        show_blink = True
        time.sleep(4.0)
        current_message = ""
        show_blink = False

    is_spinning = False

# Hauptschleife
running = True
try:
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN and not USE_GPIO:
                if e.key == pygame.K_c: event_queue.append("COIN")
                if e.key == pygame.K_l: event_queue.append("LEVER")
                if e.key == pygame.K_r: event_queue.append("RESET")
                if e.key == pygame.K_f: toggle_fullscreen()
        
        if event_queue:
            ev = event_queue.pop(0)
            if ev == "COIN":
                with data_lock:
                    data["credits"] += CREDIT_PER_COIN
                    save_data(data)
            elif ev == "RESET":
                with data_lock:
                    data["credits"] = START_CREDITS
                    save_data(data)
            elif ev == "LEVER":
                if not is_spinning:
                    with data_lock:
                        if data["credits"] > 0:
                            data["credits"] -= 1
                            save_data(data)
                            threading.Thread(target=spin, daemon=True).start()
                        else:
                            current_message = "KEINE CREDITS"
                            # Kurze Anzeige ohne den Thread zu blockieren
                            threading.Timer(1.5, lambda: globals().update(current_message="")).start()
        
        # Zeichnen und Aktualisieren NUR hier im Haupt-Thread
        draw_screen(current_message, show_blink)
        pygame.display.flip()
        clock.tick(FPS)

finally:
    if USE_GPIO:
        GPIO.cleanup()
    pygame.quit()
