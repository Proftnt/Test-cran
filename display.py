import datetime
import json
import logging
import os
import tempfile
import threading
import time

import pygame
from flask import Flask, request, send_file, jsonify

# ================= Flask =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")

CUSTOM_DIR = "custom_slides"
PRESET_DIR = "preset_slides"
os.makedirs(CUSTOM_DIR, exist_ok=True)
os.makedirs(PRESET_DIR, exist_ok=True)

FILE_LOCK = threading.RLock()
ALLOWED_SLIDE_TYPES = {"normal", "list"}


def _read_json_file(path):
    with FILE_LOCK:
        with open(path, encoding="utf-8") as file:
            return json.load(file)


def _atomic_write_json(path, data):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix="._tmp", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, indent=2, ensure_ascii=False)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        with FILE_LOCK:
            os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# Créer des slides de présentation par défaut
def create_default_presets():
    if not os.listdir(PRESET_DIR):
        presets = [
            {
                "title": "Bienvenue au collège !",
                "content": "Consultez cet écran régulièrement pour rester informé des actualités et événements du collège.",
                "order": 1,
                "type": "normal"
            },
        ]
        for i, preset in enumerate(presets):
            _atomic_write_json(f"{PRESET_DIR}/preset_{i+1}.json", preset)

create_default_presets()

# ================= Pygame =================
pygame.init()
screen = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("Affichage Collège")
clock = pygame.time.Clock()

fullscreen = False

# ================= Couleurs =================
BLUE_HEADER = (30, 58, 138)
BLUE_BG = (224, 242, 254)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BORDER_COLOR = (30, 58, 138)
PROGRESS_COLOR = (16, 185, 129)

# ================= Limites =================
MAX_TITLE_CHARS = 100
MAX_CONTENT_CHARS = 500

# ================= Helpers =================

def calculate_duration(text):
    """Calcule la durée selon le nombre de mots"""
    words = len(text.split())
    duration = 5 + (words * 0.5)
    duration = max(5, min(30, duration))
    return duration

def draw_rounded_rect(surface, color, rect, radius):
    """Dessine un rectangle avec coins arrondis"""
    shape_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shape_surf, color, shape_surf.get_rect(), border_radius=radius)
    surface.blit(shape_surf, rect.topleft)

def load_slides():
    """Charge les slides preset + custom"""
    slides = []
    
    # Charger presets d'abord (triés par order)
    preset_files = []
    for f in os.listdir(PRESET_DIR):
        if f.endswith(".json"):
            path = f"{PRESET_DIR}/{f}"
            try:
                data = _read_json_file(path)
            except Exception as exc:
                logger.warning("Failed to load preset slide %s: %s", path, exc)
                continue

            data["is_preset"] = True
            data["filename"] = f
            preset_files.append(data)
    
    preset_files.sort(key=lambda x: x.get("order", 999))
    slides.extend(preset_files)
    
    # Puis charger les custom
    for f in sorted(os.listdir(CUSTOM_DIR)):
        if f.endswith(".json"):
            path = f"{CUSTOM_DIR}/{f}"
            try:
                data = _read_json_file(path)
            except Exception as exc:
                logger.warning("Failed to load custom slide %s: %s", path, exc)
                continue

            data["is_preset"] = False
            data["filename"] = f

            if "title" in data:
                data["title"] = data["title"][:MAX_TITLE_CHARS]
            if "content" in data:
                data["content"] = data["content"][:MAX_CONTENT_CHARS]

            total_text = data.get("title", "") + " " + data.get("content", "")
            data["duration"] = calculate_duration(total_text)
            slides.append(data)
    
    if not slides:
        slides = [{
            "title": "Information collège",
            "content": "Aucune slide configurée.\n\nUtilisez l'éditeur web.",
            "duration": 8,
            "is_preset": False,
            "type": "normal"
        }]
    
    return slides

def draw_text_wrapped(surface, text, rect, font, color):
    """Affiche du texte avec retour à la ligne"""
    lines = []
    for paragraph in text.split('\n'):
        words = paragraph.split(' ')
        line = ""
        
        for word in words:
            test_line = line + " " + word if line else word
            if font.size(test_line)[0] <= rect.width - 40:
                line = test_line
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
    
    y = rect.y + 20
    for line in lines:
        if y + font.get_height() > rect.bottom - 20:
            surf = font.render("...", True, color)
            surface.blit(surf, (rect.x + 20, y))
            break
        
        surf = font.render(line, True, color)
        surface.blit(surf, (rect.x + 20, y))
        y += surf.get_height() + 8

def draw_scrolling_list(surface, names_text, rect, font, color, scroll_offset):
    """Affiche une liste de noms qui défile verticalement"""
    lines = []
    for line in names_text.split('\n'):
        if line.strip():
            lines.append(line.strip())
    
    if not lines:
        return 0
    
    # Calculer la hauteur totale du texte
    line_height = font.get_height() + 12
    total_height = len(lines) * line_height
    
    # Créer une surface temporaire pour le texte
    text_surface = pygame.Surface((rect.width, total_height + rect.height), pygame.SRCALPHA)
    
    y = 0
    for line in lines:
        surf = font.render("• " + line, True, color)
        text_surface.blit(surf, (20, y))
        y += line_height
    
    # Appliquer le scroll
    source_rect = pygame.Rect(0, scroll_offset, rect.width, rect.height - 40)
    surface.blit(text_surface, (rect.x, rect.y + 20), source_rect)
    
    return total_height

def draw_header():
    """Barre d'en-tête"""
    W = screen.get_width()
    
    pygame.draw.rect(screen, BLUE_HEADER, (0, 0, W, 80))
    
    font_title = pygame.font.SysFont("Arial", 36, bold=True)
    title = font_title.render("Affichage Collège", True, WHITE)
    screen.blit(title, (20, 22))
    
    now = datetime.datetime.now()
    days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    months = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"]
    
    day_name = days[now.weekday()]
    date_str = f"{day_name} {now.day} {months[now.month-1]}"
    time_str = now.strftime("%H:%M")
    
    font_time = pygame.font.SysFont("Arial", 32, bold=True)
    font_date = pygame.font.SysFont("Arial", 18)
    
    time_surf = font_time.render(time_str, True, WHITE)
    date_surf = font_date.render(date_str, True, WHITE)
    
    screen.blit(time_surf, (W - time_surf.get_width() - 20, 18))
    screen.blit(date_surf, (W - date_surf.get_width() - 20, 55))

def draw_progress_bar(progress, duration):
    """Barre de progression en haut"""
    W = screen.get_width()
    bar_height = 8
    bar_y = 82
    
    pygame.draw.rect(screen, (200, 200, 200), (0, bar_y, W, bar_height))
    
    progress_width = int(W * progress)
    pygame.draw.rect(screen, PROGRESS_COLOR, (0, bar_y, progress_width, bar_height))

def draw_slide_surface(slide, scroll_offset=0):
    """Dessine une slide sur une surface"""
    W, H = screen.get_width(), screen.get_height()
    surface = pygame.Surface((W, H))
    surface.fill(BLUE_BG)
    
    title = slide.get("title", "").strip() or "Information collège"
    content = slide.get("content", "").strip()
    slide_type = slide.get("type", "normal")
    
    content_top = 100
    margin = 40
    
    # Carré titre
    title_rect = pygame.Rect(margin, content_top, W - margin*2, 100)
    draw_rounded_rect(surface, WHITE, title_rect, 15)
    pygame.draw.rect(surface, BORDER_COLOR, title_rect, 3, border_radius=15)
    
    font_title = pygame.font.SysFont("Arial", 36, bold=True)
    title_surf = font_title.render(title, True, BLACK)
    title_y = title_rect.y + (title_rect.height - title_surf.get_height()) // 2
    surface.blit(title_surf, (title_rect.x + 20, title_y))
    
    # Carré contenu
    if content:
        content_rect = pygame.Rect(margin, content_top + 120, W - margin*2, H - content_top - 160)
        draw_rounded_rect(surface, WHITE, content_rect, 15)
        pygame.draw.rect(surface, BORDER_COLOR, content_rect, 3, border_radius=15)
        
        if slide_type == "list":
            # Mode liste avec défilement
            font_content = pygame.font.SysFont("Arial", 24)
            draw_scrolling_list(surface, content, content_rect, font_content, BLACK, scroll_offset)
        else:
            # Mode normal
            font_content = pygame.font.SysFont("Arial", 28)
            draw_text_wrapped(surface, content, content_rect, font_content, BLACK)
    
    return surface

def calculate_scroll_height(text, rect_height, font):
    """Calcule la hauteur totale du texte pour le scroll"""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    line_height = font.get_height() + 12
    total_height = len(lines) * line_height
    return max(0, total_height - rect_height + 60)

def slide_transition(old_surface, new_surface):
    """Animation de transition vers la gauche"""
    W = screen.get_width()
    
    for frame in range(60):
        progress = frame / 60
        eased = 1 - (1 - progress) ** 3
        offset = int(W * eased)
        
        screen.fill(BLUE_BG)
        screen.blit(old_surface, (-offset, 0))
        screen.blit(new_surface, (W - offset, 0))
        draw_header()
        
        pygame.display.flip()
        clock.tick(60)

def run_slides():
    """Boucle principale"""
    global fullscreen, screen

    slides = load_slides()
    current_index = 0
    reload_done = False
    
    # Variables pour le scroll
    scroll_offset = 0
    max_scroll = 0

    current_surface = draw_slide_surface(slides[current_index], scroll_offset)
    
    while True:
        if current_index == 0 and not reload_done:
            slides = load_slides()
            reload_done = True

        slide = slides[current_index]
        duration = slide.get("duration", 8)
        slide_type = slide.get("type", "normal")
        
        # Calculer le scroll si c'est une liste
        if slide_type == "list":
            W, H = screen.get_width(), screen.get_height()
            content_rect = pygame.Rect(40, 220, W - 80, H - 260)
            font_content = pygame.font.SysFont("Arial", 24)
            max_scroll = calculate_scroll_height(
                slide.get("content", ""),
                content_rect.height,
                font_content
            )
        else:
            max_scroll = 0
            scroll_offset = 0
        
        start_time = time.time()
        
        while time.time() - start_time < duration:
            elapsed = time.time() - start_time
            progress = elapsed / duration
            
            # Défilement automatique pour les listes
            if slide_type == "list" and max_scroll > 0:
                scroll_offset = int((elapsed / duration) * max_scroll)
                current_surface = draw_slide_surface(slide, scroll_offset)
            
            screen.blit(current_surface, (0, 0))
            draw_header()
            draw_progress_bar(progress, duration)
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        return
                    
                    elif event.key == pygame.K_F11:
                        fullscreen = not fullscreen
                        if fullscreen:
                            screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                        else:
                            screen = pygame.display.set_mode((1280, 720))
                        current_surface = draw_slide_surface(slide, scroll_offset)
                    
                    elif event.key == pygame.K_n:
                        start_time = 0
            
            pygame.display.flip()
            clock.tick(60)
        
        next_index = (current_index + 1) % len(slides)

        if next_index == 0:
            reload_done = False
        
        scroll_offset = 0
        next_surface = draw_slide_surface(slides[next_index], 0)
        slide_transition(current_surface, next_surface)
        
        current_surface = next_surface
        current_index = next_index

# ================= Flask routes =================

@app.route("/")
def index():
    return send_file("slide_editor.html")

@app.route("/save", methods=["POST"])
def save():
    try:
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return {"status": "error", "message": "Payload JSON invalide"}, 400

        name = data.get("name", "slide").replace(" ", "_")
        name = "".join(c for c in name if c.isalnum() or c in "._-")
        if not name:
            name = f"slide_{int(time.time())}"
        filename = f"{CUSTOM_DIR}/{name}.json"

        if "title" in data:
            data["title"] = data["title"][:MAX_TITLE_CHARS]
        if "content" in data:
            data["content"] = data["content"][:MAX_CONTENT_CHARS]

        slide_type = data.get("type", "normal")
        if slide_type not in ALLOWED_SLIDE_TYPES:
            logger.warning("Received unsupported slide type '%s', falling back to 'normal'", slide_type)
            slide_type = "normal"
        data["type"] = slide_type

        total_text = data.get("title", "") + " " + data.get("content", "")
        data["duration"] = calculate_duration(total_text)

        # Durée plus longue pour les listes
        if data.get("type") == "list":
            lines = len([l for l in data.get("content", "").split('\n') if l.strip()])
            data["duration"] = max(10, min(45, 8 + lines * 0.8))

        _atomic_write_json(filename, data)
        logger.info("Saved slide %s", filename)

        word_count = len(total_text.split())
        return {"status": "ok", "duration": data["duration"], "words": word_count}

    except Exception as e:
        logger.exception("Failed to save slide")
        return {"status": "error", "message": str(e)}, 500

@app.route("/list", methods=["GET"])
def list_slides():
    result = {"presets": [], "custom": []}
    
    for f in os.listdir(PRESET_DIR):
        if f.endswith(".json"):
            path = f"{PRESET_DIR}/{f}"
            try:
                data = _read_json_file(path)
            except Exception as exc:
                logger.warning("Failed to list preset slide %s: %s", path, exc)
                continue

            result["presets"].append({
                "filename": f,
                "name": f[:-5],
                "title": data.get("title", ""),
                "order": data.get("order", 999)
            })
    
    result["presets"].sort(key=lambda x: x["order"])
    
    for f in os.listdir(CUSTOM_DIR):
        if f.endswith(".json"):
            path = f"{CUSTOM_DIR}/{f}"
            try:
                data = _read_json_file(path)
            except Exception as exc:
                logger.warning("Failed to list custom slide %s: %s", path, exc)
                continue

            result["custom"].append({
                "filename": f,
                "name": f[:-5],
                "title": data.get("title", "")
            })
    
    return jsonify(result)

@app.route("/delete/<slide_type>/<filename>", methods=["DELETE"])
def delete_slide(slide_type, filename):
    try:
        if slide_type == "preset":
            filepath = f"{PRESET_DIR}/{filename}"
        else:
            filepath = f"{CUSTOM_DIR}/{filename}"
        
        with FILE_LOCK:
            if os.path.exists(filepath):
                os.remove(filepath)
            else:
                return {"status": "error", "message": "Fichier non trouvé"}, 404

        logger.info("Deleted %s slide %s", slide_type, filename)
        return {"status": "ok"}
    except Exception as e:
        logger.exception("Failed to delete %s slide %s", slide_type, filename)
        return {"status": "error", "message": str(e)}, 500

if __name__ == "__main__":
    import threading
    
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=80, debug=False),
        daemon=True
    ).start()
    
    time.sleep(1)
    
    try:
        run_slides()
    except KeyboardInterrupt:
        pygame.quit()
