import os, json, pygame, time, datetime, hashlib
from flask import Flask, request, send_file, jsonify, session, redirect
from werkzeug.utils import secure_filename

# ================= Flask =================
app = Flask(__name__, static_folder="static")
app.secret_key = os.urandom(24)  # Random secret key for sessions

CUSTOM_DIR = "custom_slides"
PRESET_DIR = "preset_slides"
PASSWORD_FILE = "editor_password.txt"
ADMIN_PASSWORD_FILE = "admin_password.txt"
UPLOAD_DIR = "uploads"
CALENDAR_DIR = "calendar_data"

os.makedirs(CUSTOM_DIR, exist_ok=True)
os.makedirs(PRESET_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CALENDAR_DIR, exist_ok=True)

# Create default password files if they don't exist
def create_default_passwords():
    # Editor password
    if not os.path.exists(PASSWORD_FILE):
        default_hash = hashlib.sha256("editor123".encode()).hexdigest()
        with open(PASSWORD_FILE, "w") as f:
            f.write(default_hash)
    
    # Admin password
    if not os.path.exists(ADMIN_PASSWORD_FILE):
        admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
        with open(ADMIN_PASSWORD_FILE, "w") as f:
            f.write(admin_hash)

create_default_passwords()

def check_password(password, is_admin=False):
    """Check if password matches the stored hash"""
    try:
        file_path = ADMIN_PASSWORD_FILE if is_admin else PASSWORD_FILE
        with open(file_path, "r") as f:
            stored_hash = f.read().strip()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return password_hash == stored_hash
    except:
        return False

def change_password(new_password, is_admin=False):
    """Change the password"""
    password_hash = hashlib.sha256(new_password.encode()).hexdigest()
    file_path = ADMIN_PASSWORD_FILE if is_admin else PASSWORD_FILE
    with open(file_path, "w") as f:
        f.write(password_hash)

# Create default preset slides
def create_default_presets():
    if not os.listdir(PRESET_DIR):
        presets = [
            {
                "title": "Bienvenue au collège !",
                "content": "Consultez cet écran régulièrement pour rester informé des actualités et événements du collège.",
                "order": 1,
                "type": "normal"
            },
            {
                "title": "Horaires du collège",
                "content": "Lundi - Vendredi: 8h00 - 17h00\nMercredi: 8h00 - 12h00\n\nAccueil ouvert dès 7h45",
                "order": 2,
                "type": "normal"
            }
        ]
        for i, preset in enumerate(presets):
            with open(f"{PRESET_DIR}/preset_{i+1}.json", "w", encoding="utf-8") as f:
                json.dump(preset, f, indent=2, ensure_ascii=False)

create_default_presets()

# Initialize calendar JSON files if they don't exist
def init_calendar_files():
    """Ensure calendar_data JSON files exist (even if empty)."""
    abs_path = os.path.join(CALENDAR_DIR, "absences.json")
    if not os.path.exists(abs_path):
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    
    events_path = os.path.join(CALENDAR_DIR, "events.json")
    if not os.path.exists(events_path):
        with open(events_path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    
    clubs_path = os.path.join(CALENDAR_DIR, "clubs.json")
    if not os.path.exists(clubs_path):
        with open(clubs_path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

init_calendar_files()

# ================= Pygame =================
pygame.init()
screen = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("Affichage Collège")
clock = pygame.time.Clock()

fullscreen = False

# ================= Colors =================
BLUE_HEADER = (30, 58, 138)
BLUE_BG = (224, 242, 254)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BORDER_COLOR = (30, 58, 138)
PROGRESS_COLOR = (16, 185, 129)

# ================= Limits =================
MAX_TITLE_CHARS = 100
MAX_CONTENT_CHARS = 500

# ================= Helpers =================

def calculate_duration(text):
    """Calculate duration based on word count"""
    words = len(text.split())
    duration = 5 + (words * 0.5)
    duration = max(5, min(30, duration))
    return duration

def draw_rounded_rect(surface, color, rect, radius):
    """Draw a rectangle with rounded corners"""
    shape_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shape_surf, color, shape_surf.get_rect(), border_radius=radius)
    surface.blit(shape_surf, rect.topleft)

def load_slides():
    """Load preset + custom slides + calendar slides"""
    slides = []
    
    # Load presets first (sorted by order)
    preset_files = []
    for f in os.listdir(PRESET_DIR):
        if f.endswith(".json"):
            try:
                with open(f"{PRESET_DIR}/{f}", encoding="utf-8") as file:
                    data = json.load(file)
                    data["is_preset"] = True
                    data["filename"] = f
                    preset_files.append(data)
            except:
                pass
    
    preset_files.sort(key=lambda x: x.get("order", 999))
    slides.extend(preset_files)
    
    # Add calendar slides
    calendar_slides = generate_calendar_slides()
    slides.extend(calendar_slides)
    
    # Then load custom slides
    for f in sorted(os.listdir(CUSTOM_DIR)):
        if f.endswith(".json"):
            try:
                with open(f"{CUSTOM_DIR}/{f}", encoding="utf-8") as file:
                    data = json.load(file)
                    data["is_preset"] = False
                    data["filename"] = f
                    
                    if "title" in data:
                        data["title"] = data["title"][:MAX_TITLE_CHARS]
                    if "content" in data:
                        data["content"] = data["content"][:MAX_CONTENT_CHARS]
                    
                    total_text = data.get("title", "") + " " + data.get("content", "")
                    data["duration"] = calculate_duration(total_text)
                    slides.append(data)
            except:
                pass
    
    if not slides:
        slides = [{
            "title": "Information collège",
            "content": "Aucune slide configurée.\n\nUtilisez l'éditeur web.",
            "duration": 8,
            "is_preset": False,
            "type": "normal"
        }]
    
    return slides

def generate_calendar_slides():
    """Generate slides from calendar data

    Produces a visual absences slide (`calendar_absences_visual`) that contains
    normalized `absences_data` keyed by French weekday names (Lundi..Vendredi).
    """
    slides = []

    # --- Absences visual slide (normalized keys) ---
    abs_path = os.path.join(CALENDAR_DIR, "absences.json")
    if os.path.exists(abs_path):
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}

            # normalize keys to French weekday names expected by draw_absences_calendar
            fr_days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
            en_map = {"monday": "Lundi", "tuesday": "Mardi", "wednesday": "Mercredi", "thursday": "Jeudi", "friday": "Vendredi"}

            absences_norm = {}
            for d in fr_days:
                absences_norm[d] = []

            for key, val in raw.items():
                if not val:
                    continue
                k = key.strip()
                mapped = None
                if k in fr_days:
                    mapped = k
                elif k.lower() in [d.lower() for d in fr_days]:
                    # match case-insensitive
                    for d in fr_days:
                        if d.lower() == k.lower():
                            mapped = d
                            break
                elif k.lower() in en_map:
                    mapped = en_map[k.lower()]

                if mapped:
                    # ensure list
                    if isinstance(val, list):
                        absences_norm[mapped].extend(val)
                    else:
                        absences_norm[mapped].append(val)

            # Only add slide if any absences present
            if any(absences_norm[d] for d in fr_days):
                slides.append({
                    "title": "Absences de la semaine",
                    "absences_data": absences_norm,
                    "duration": 12,
                    "type": "calendar_absences_visual"
                })
        except Exception as e:
            pass
    
    # --- Events visual slide (rolling 5-day window) ---
    events_path = os.path.join(CALENDAR_DIR, "events.json")
    if os.path.exists(events_path):
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                events = json.load(f) or []

            if events:
                # Organize events by date
                from datetime import datetime, timedelta
                events_by_date = {}
                for event in events:
                    try:
                        date_str = event.get("date") or event.get("jour")
                        if not date_str:
                            continue
                        # Try parsing with multiple formats
                        dt = None
                        for fmt in (None, "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                            try:
                                if fmt is None:
                                    dt = datetime.fromisoformat(date_str)
                                else:
                                    dt = datetime.strptime(date_str, fmt)
                                break
                            except:
                                dt = None
                        if not dt and date_str.endswith('Z'):
                            try:
                                dt = datetime.fromisoformat(date_str.rstrip('Z'))
                            except:
                                dt = None
                        if dt:
                            date_key = dt.date()
                            if date_key not in events_by_date:
                                events_by_date[date_key] = []
                            events_by_date[date_key].append(event)
                        else:
                            pass
                    except Exception as e:
                        pass

                if events_by_date:
                    slides.append({
                        "title": "Événements à venir",
                        "events_data": events_by_date,
                        "duration": 12,
                        "type": "calendar_events_visual"
                    })
        except Exception as e:
            pass
    
    # --- Clubs slide (unchanged) ---
    try:
        with open(f"{CALENDAR_DIR}/clubs.json", "r", encoding="utf-8") as f:
            clubs_data = json.load(f)

        if clubs_data:
            slides.append({
                "title": "Planning des clubs",
                "clubs_data": clubs_data,
                "duration": 15,
                "type": "calendar_clubs"
            })
    except Exception:
        pass
    
    return slides

def draw_text_wrapped(surface, text, rect, font, color):
    """Display text with word wrapping"""
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
    """Display a list of names that scrolls vertically - FASTER"""
    lines = []
    for line in names_text.split('\n'):
        if line.strip():
            lines.append(line.strip())
    
    if not lines:
        return 0
    
    line_height = font.get_height() + 8  # Reduced spacing for faster scroll
    total_height = len(lines) * line_height
    
    text_surface = pygame.Surface((rect.width, total_height + rect.height), pygame.SRCALPHA)
    
    y = 0
    for line in lines:
        surf = font.render("• " + line, True, color)
        text_surface.blit(surf, (20, y))
        y += line_height
    
    source_rect = pygame.Rect(0, scroll_offset, rect.width, rect.height - 40)
    surface.blit(text_surface, (rect.x, rect.y + 20), source_rect)
    
    return total_height

def draw_header():
    """Header bar"""
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
    """Progress bar at the top"""
    W = screen.get_width()
    bar_height = 8
    bar_y = 82
    
    pygame.draw.rect(screen, (200, 200, 200), (0, bar_y, W, bar_height))
    
    progress_width = int(W * progress)
    pygame.draw.rect(screen, PROGRESS_COLOR, (0, bar_y, progress_width, bar_height))

def draw_slide_surface(slide, scroll_offset=0):
    """Draw a slide on a surface"""
    W, H = screen.get_width(), screen.get_height()
    surface = pygame.Surface((W, H))
    surface.fill(BLUE_BG)
    
    title = slide.get("title", "").strip() or "Information collège"
    content = slide.get("content", "").strip()
    slide_type = slide.get("type", "normal")
    
    content_top = 100
    margin = 40
    
    # Title box
    title_rect = pygame.Rect(margin, content_top, W - margin*2, 100)
    draw_rounded_rect(surface, WHITE, title_rect, 15)
    pygame.draw.rect(surface, BORDER_COLOR, title_rect, 3, border_radius=15)
    
    font_title = pygame.font.SysFont("Arial", 36, bold=True)
    title_surf = font_title.render(title, True, BLACK)
    title_y = title_rect.y + (title_rect.height - title_surf.get_height()) // 2
    surface.blit(title_surf, (title_rect.x + 20, title_y))
    
    # Content box
    if slide_type == "calendar_clubs":
        draw_clubs_schedule(surface, slide.get("clubs_data", {}), margin, content_top + 120, W - margin*2, H - content_top - 160)
    elif slide_type == "calendar_absences_visual":
        draw_absences_calendar(surface, slide.get("absences_data", {}), margin, content_top + 120, W - margin*2, H - content_top - 160, scroll_offset)
    elif slide_type == "calendar_events_visual":
        draw_events_calendar(surface, slide.get("events_data", []), margin, content_top + 120, W - margin*2, H - content_top - 160)
    elif content:
        content_rect = pygame.Rect(margin, content_top + 120, W - margin*2, H - content_top - 160)
        draw_rounded_rect(surface, WHITE, content_rect, 15)
        pygame.draw.rect(surface, BORDER_COLOR, content_rect, 3, border_radius=15)
        
        if slide_type == "list":
            font_content = pygame.font.SysFont("Arial", 24)
            draw_scrolling_list(surface, content, content_rect, font_content, BLACK, scroll_offset)
        else:
            font_content = pygame.font.SysFont("Arial", 28)
            draw_text_wrapped(surface, content, content_rect, font_content, BLACK)
    
    return surface

def draw_clubs_schedule(surface, clubs_data, x, y, w, h):
    """Draw clubs schedule grid"""
    time_slots = [
        "8:15-9:10", "9:15-10:10", "10:25-11:20", "11:25-12:20",
        "13:00-13:55", "14:00-14:55", "15:00-15:45", "15:55-16:50"
    ]
    days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
    
    main_rect = pygame.Rect(x, y, w, h)
    draw_rounded_rect(surface, WHITE, main_rect, 15)
    pygame.draw.rect(surface, BORDER_COLOR, main_rect, 3, border_radius=15)
    
    time_col_width = 120
    day_col_width = (w - time_col_width - 40) // 5
    row_height = (h - 60) // (len(time_slots) + 1)
    
    start_x = x + 20
    start_y = y + 20
    
    font_header = pygame.font.SysFont("Arial", 16, bold=True)
    font_cell = pygame.font.SysFont("Arial", 13)
    
    # Draw day headers
    for i, day in enumerate(days):
        header_x = start_x + time_col_width + i * day_col_width
        header_rect = pygame.Rect(header_x, start_y, day_col_width, row_height)
        pygame.draw.rect(surface, BLUE_HEADER, header_rect)
        
        day_surf = font_header.render(day, True, WHITE)
        day_x = header_x + (day_col_width - day_surf.get_width()) // 2
        day_y = start_y + (row_height - day_surf.get_height()) // 2
        surface.blit(day_surf, (day_x, day_y))
    
    # Draw time slots and clubs
    for slot_idx, time_slot in enumerate(time_slots):
        row_y = start_y + (slot_idx + 1) * row_height
        
        time_rect = pygame.Rect(start_x, row_y, time_col_width, row_height)
        pygame.draw.rect(surface, (240, 249, 255), time_rect)
        pygame.draw.rect(surface, BORDER_COLOR, time_rect, 1)
        
        time_surf = font_header.render(time_slot, True, BLACK)
        time_x = start_x + (time_col_width - time_surf.get_width()) // 2
        time_y = row_y + (row_height - time_surf.get_height()) // 2
        surface.blit(time_surf, (time_x, time_y))
        
        # Day cells
        for day_idx, day in enumerate(days):
            cell_x = start_x + time_col_width + day_idx * day_col_width
            cell_rect = pygame.Rect(cell_x, row_y, day_col_width, row_height)
            
            key = f"{day}-{slot_idx}"
            club_names = clubs_data.get(key, "")
            
            # Support multiple clubs separated by comma
            if isinstance(club_names, list):
                club_names = ", ".join(club_names)
            
            if club_names:
                pygame.draw.rect(surface, (219, 234, 254), cell_rect)
            
            pygame.draw.rect(surface, BORDER_COLOR, cell_rect, 1)
            
            if club_names:
                # Wrap text if too long
                words = club_names.split()
                lines = []
                current_line = ""
                
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    if font_cell.size(test_line)[0] <= day_col_width - 10:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                
                text_y = row_y + 5
                for line in lines[:3]:  # Max 3 lines
                    club_surf = font_cell.render(line, True, BLACK)
                    club_x = cell_x + (day_col_width - club_surf.get_width()) // 2
                    surface.blit(club_surf, (club_x, text_y))
                    text_y += font_cell.get_height() + 2

def draw_absences_calendar(surface, absences_data, x, y, w, h, scroll_offset=0):
    """Draw absences in 5-column calendar format - like the screenshot"""
    from datetime import datetime, timedelta
    days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]

    # Build a consecutive list of the next 5 school days starting from today
    now = datetime.now()
    dates = []
    dt = now
    # find the first column date = today if weekday in 0..4, else next Monday
    if dt.weekday() > 4:
        # it's weekend -> next Monday
        days_until_monday = 7 - dt.weekday()
        dt = dt + timedelta(days=days_until_monday)

    # collect 5 consecutive weekdays (skip weekends)
    while len(dates) < 5:
        if dt.weekday() < 5:
            dates.append(dt)
        dt = dt + timedelta(days=1)
    
    # Calculate column dimensions
    gap = 15
    col_width = (w - gap * 6) // 5
    start_x = x + gap
    
    font_header = pygame.font.SysFont("Arial", 22, bold=True)
    font_date = pygame.font.SysFont("Arial", 16)
    font_absence = pygame.font.SysFont("Arial", 16)
    font_empty = pygame.font.SysFont("Arial", 16, italic=True)
    
    # Draw each column, applying horizontal scroll offset (in pixels)
    scroll_x = scroll_offset or 0

    for i, date in enumerate(dates):
        # Map actual date to French day name
        actual_day_name = days[date.weekday()]
        col_x = start_x + i * (col_width + gap) - scroll_x
        
        # Draw rounded column box
        col_rect = pygame.Rect(col_x, y, col_width, h)
        draw_rounded_rect(surface, WHITE, col_rect, 15)
        pygame.draw.rect(surface, BORDER_COLOR, col_rect, 3, border_radius=15)
        
        # Day header (centered, bold)
        day_surf = font_header.render(actual_day_name, True, BLUE_HEADER)
        day_x = col_x + (col_width - day_surf.get_width()) // 2
        surface.blit(day_surf, (day_x, y + 20))
        
        # Date (centered, gray)
        date_str = f"{date.day}/{date.month}"
        date_surf = font_date.render(date_str, True, (120, 120, 120))
        date_x = col_x + (col_width - date_surf.get_width()) // 2
        surface.blit(date_surf, (date_x, y + 52))
        
        # Separator line
        line_y = y + 85
        pygame.draw.line(surface, (200, 200, 200),
                        (col_x + 10, line_y),
                        (col_x + col_width - 10, line_y), 2)
        
        # Get absences for this day
        absences_list = absences_data.get(actual_day_name, [])
        content_y = line_y + 20
        
        if not absences_list:
            # "Aucun événement" message (centered, italic, gray)
            empty_msg = "Aucune absence"
            empty_surf = font_empty.render(empty_msg, True, (160, 160, 160))
            empty_x = col_x + (col_width - empty_surf.get_width()) // 2
            surface.blit(empty_surf, (empty_x, content_y + 40))
        else:
            # Draw absence boxes
            for absence in absences_list[:8]:  # Max 8 absences per column
                name = absence.get("name", "")
                reason = absence.get("reason", "")
                
                # Calculate box height based on content
                box_height = 45 if reason else 35
                
                # Draw absence box (light blue background, blue border)
                box_rect = pygame.Rect(col_x + 10, content_y, col_width - 20, box_height)
                pygame.draw.rect(surface, (219, 234, 254), box_rect, border_radius=5)
                pygame.draw.rect(surface, (59, 130, 246), box_rect, 2, border_radius=5)
                
                # Draw left accent bar
                accent_rect = pygame.Rect(col_x + 10, content_y, 4, box_height)
                pygame.draw.rect(surface, (59, 130, 246), accent_rect)
                
                # Name text
                name_surf = font_absence.render(name[:18], True, BLACK)
                surface.blit(name_surf, (col_x + 20, content_y + 8))
                
                # Reason text (smaller, gray)
                if reason:
                    reason_surf = font_date.render(reason[:20], True, (100, 100, 100))
                    surface.blit(reason_surf, (col_x + 20, content_y + 27))
                
                content_y += box_height + 8
                
                # Stop if we're out of space
                if content_y > y + h - 50:
                    break

def draw_events_calendar(surface, events_data, x, y, w, h):
    """Draw events in 5-column calendar format (rolling 5-day window).
    
    events_data: dict keyed by date (date.date() object) -> list of event dicts
    """
    from datetime import datetime, timedelta
    
    days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]
    
    # Build rolling 5-day window starting from today
    now = datetime.now()
    dates = []
    dt = now
    
    # If weekend, start from next Monday
    if dt.weekday() > 4:
        days_until_monday = 7 - dt.weekday()
        dt = dt + timedelta(days=days_until_monday)
    
    # Collect 5 consecutive weekdays
    while len(dates) < 5:
        if dt.weekday() < 5:
            dates.append(dt)
        dt = dt + timedelta(days=1)
    
    # Calculate column dimensions
    gap = 15
    col_width = (w - gap * 6) // 5
    start_x = x + gap
    
    font_header = pygame.font.SysFont("Arial", 22, bold=True)
    font_date = pygame.font.SysFont("Arial", 16)
    font_event = pygame.font.SysFont("Arial", 16)
    font_empty = pygame.font.SysFont("Arial", 16, italic=True)
    
    # Draw each column
    for i, date in enumerate(dates):
        # Map actual date to French day name
        actual_day_name = days[date.weekday()]
        col_x = start_x + i * (col_width + gap)
        
        # Draw rounded column box
        col_rect = pygame.Rect(col_x, y, col_width, h)
        draw_rounded_rect(surface, WHITE, col_rect, 15)
        pygame.draw.rect(surface, BORDER_COLOR, col_rect, 3, border_radius=15)
        
        # Day header
        day_surf = font_header.render(actual_day_name, True, BLUE_HEADER)
        day_x = col_x + (col_width - day_surf.get_width()) // 2
        surface.blit(day_surf, (day_x, y + 20))
        
        # Date
        date_str = f"{date.day}/{date.month}"
        date_surf = font_date.render(date_str, True, (120, 120, 120))
        date_x = col_x + (col_width - date_surf.get_width()) // 2
        surface.blit(date_surf, (date_x, y + 52))
        
        # Separator line
        line_y = y + 85
        pygame.draw.line(surface, (200, 200, 200),
                        (col_x + 10, line_y),
                        (col_x + col_width - 10, line_y), 2)
        
        # Get events for this day
        events_list = events_data.get(date.date(), []) if isinstance(events_data, dict) else []
        content_y = line_y + 20
        
        if not events_list:
            # "Aucun événement" message
            empty_msg = "Aucun événement"
            empty_surf = font_empty.render(empty_msg, True, (160, 160, 160))
            empty_x = col_x + (col_width - empty_surf.get_width()) // 2
            surface.blit(empty_surf, (empty_x, content_y + 40))
        else:
            # Draw event boxes
            for event in events_list[:8]:  # Max 8 events per column
                name = event.get("name", "Événement")
                
                # Wrap event name if too long
                name_lines = []
                words = name.split()
                line = ""
                for word in words:
                    test = line + " " + word if line else word
                    if font_event.size(test)[0] <= col_width - 35:
                        line = test
                    else:
                        if line:
                            name_lines.append(line)
                        line = word
                if line:
                    name_lines.append(line)
                
                # Calculate box height
                box_height = 30 + len(name_lines[:2]) * 20
                
                # Draw event box (light blue background)
                box_rect = pygame.Rect(col_x + 10, content_y, col_width - 20, box_height)
                pygame.draw.rect(surface, (219, 234, 254), box_rect, border_radius=5)
                pygame.draw.rect(surface, (59, 130, 246), box_rect, 2, border_radius=5)
                
                # Draw left accent bar
                accent_rect = pygame.Rect(col_x + 10, content_y, 4, box_height)
                pygame.draw.rect(surface, (59, 130, 246), accent_rect)
                
                # Event text
                text_y = content_y + 8
                for line in name_lines[:2]:
                    line_surf = font_event.render(line, True, BLACK)
                    surface.blit(line_surf, (col_x + 20, text_y))
                    text_y += 20
                
                content_y += box_height + 8
                
                # Stop if out of space
                if content_y > y + h - 50:
                    break

def calculate_scroll_height(text, rect_height, font):
    """Calculate total text height for scrolling"""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    line_height = font.get_height() + 12
    total_height = len(lines) * line_height
    return max(0, total_height - rect_height + 60)

def slide_transition(old_surface, new_surface):
    """Slide transition animation to the left"""
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
    """Main loop"""
    global fullscreen, screen

    slides = load_slides()
    current_index = 0
    reload_done = False
    
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
    if not session.get('logged_in'):
        return redirect('/login')
    return send_file("slide_editor.html")

@app.route("/login")
def login_page():
    return send_file("login.html")

@app.route("/admin")
def admin_page():
    if not session.get('logged_in'):
        return redirect('/login')
    if not session.get('is_admin'):
        return redirect('/')
    return send_file("admin_panel.html")

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    password = data.get("password", "")
    
    if check_password(password, is_admin=False):
        session['logged_in'] = True
        session['is_admin'] = False
        return {"status": "ok"}
    else:
        return {"status": "error", "message": "Mot de passe incorrect"}, 401

@app.route("/api/admin_login", methods=["POST"])
def admin_login():
    data = request.get_json()
    password = data.get("password", "")
    
    if check_password(password, is_admin=True):
        session['logged_in'] = True
        session['is_admin'] = True
        return {"status": "ok"}
    else:
        return {"status": "error", "message": "Mot de passe admin incorrect"}, 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop('logged_in', None)
    session.pop('is_admin', None)
    return {"status": "ok"}

@app.route("/api/change_password", methods=["POST"])
def change_password_route():
    if not session.get('is_admin'):
        return {"status": "error", "message": "Non autorisé"}, 401
    
    data = request.get_json()
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    password_type = data.get("type", "editor")  # "editor" or "admin"
    
    is_admin = password_type == "admin"
    
    if not check_password(old_password, is_admin=is_admin):
        return {"status": "error", "message": "Ancien mot de passe incorrect"}, 401
    
    if len(new_password) < 6:
        return {"status": "error", "message": "Le mot de passe doit faire au moins 6 caractères"}, 400
    
    change_password(new_password, is_admin=is_admin)
    return {"status": "ok"}

@app.route("/api/upload_code", methods=["POST"])
def upload_code():
    if not session.get('is_admin'):
        return {"status": "error", "message": "Non autorisé"}, 401
    
    if 'file' not in request.files:
        return {"status": "error", "message": "Aucun fichier"}, 400
    
    file = request.files['file']
    file_type = request.form.get('type')
    
    if file.filename == '':
        return {"status": "error", "message": "Nom de fichier vide"}, 400
    
    if file_type == 'python':
        filename = 'display.py'
    elif file_type == 'html':
        filename = 'slide_editor.html'
    else:
        return {"status": "error", "message": "Type de fichier invalide"}, 400
    
    upload_path = os.path.join(UPLOAD_DIR, filename)
    file.save(upload_path)
    
    if file_type == 'python':
        target_path = 'display.py'
    else:
        target_path = 'slide_editor.html'
    
    os.replace(upload_path, target_path)
    
    return {"status": "ok", "message": f"Fichier {filename} mis à jour avec succès"}

@app.route("/save", methods=["POST"])
def save():
    if not session.get('logged_in'):
        return {"status": "error", "message": "Non autorisé"}, 401
    
    try:
        data = request.get_json()
        name = data.get("name", "slide").replace(" ", "_")
        name = "".join(c for c in name if c.isalnum() or c in "._-")
        filename = f"{CUSTOM_DIR}/{name}.json"
        
        if "title" in data:
            data["title"] = data["title"][:MAX_TITLE_CHARS]
        if "content" in data:
            data["content"] = data["content"][:MAX_CONTENT_CHARS]
        
        total_text = data.get("title", "") + " " + data.get("content", "")
        data["duration"] = calculate_duration(total_text)
        
        if data.get("type") == "list":
            lines = len([l for l in data.get("content", "").split('\n') if l.strip()])
            data["duration"] = max(10, min(45, 8 + lines * 0.8))
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        word_count = len(total_text.split())
        return {"status": "ok", "duration": data["duration"], "words": word_count}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route("/list", methods=["GET"])
def list_slides():
    if not session.get('logged_in'):
        return {"status": "error", "message": "Non autorisé"}, 401
    
    result = {"presets": [], "custom": []}
    
    for f in os.listdir(PRESET_DIR):
        if f.endswith(".json"):
            try:
                with open(f"{PRESET_DIR}/{f}", encoding="utf-8") as file:
                    data = json.load(file)
                    result["presets"].append({
                        "filename": f,
                        "name": f[:-5],
                        "title": data.get("title", ""),
                        "order": data.get("order", 999)
                    })
            except:
                pass
    
    result["presets"].sort(key=lambda x: x["order"])
    
    for f in os.listdir(CUSTOM_DIR):
        if f.endswith(".json"):
            try:
                with open(f"{CUSTOM_DIR}/{f}", encoding="utf-8") as file:
                    data = json.load(file)
                    result["custom"].append({
                        "filename": f,
                        "name": f[:-5],
                        "title": data.get("title", "")
                    })
            except:
                pass
    
    return jsonify(result)

@app.route("/calendar")
def calendar_page():
    if not session.get('logged_in'):
        return redirect('/login')
    return send_file("calendar_manager.html")

@app.route("/api/calendar/absences", methods=["GET"])
def get_absences():
    if not session.get('logged_in'):
        return {"status": "error"}, 401
    try:
        with open(f"{CALENDAR_DIR}/absences.json", "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except:
        return jsonify({})

@app.route("/api/calendar/absence", methods=["POST"])
def add_absence():
    if not session.get('logged_in'):
        return {"status": "error"}, 401
    
    data = request.get_json()
    day = data.get("day")
    name = data.get("name")
    reason = data.get("reason", "")
    
    try:
        try:
            with open(f"{CALENDAR_DIR}/absences.json", "r", encoding="utf-8") as f:
                absences = json.load(f)
        except:
            absences = {}
        
        if day not in absences:
            absences[day] = []
        
        absences[day].append({"name": name, "reason": reason})
        
        with open(f"{CALENDAR_DIR}/absences.json", "w", encoding="utf-8") as f:
            json.dump(absences, f, ensure_ascii=False, indent=2)
        
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route("/api/calendar/absence/delete", methods=["POST"])
def delete_absence():
    if not session.get('logged_in'):
        return {"status": "error"}, 401
    
    data = request.get_json()
    day = data.get("day")
    index = data.get("index")
    
    try:
        with open(f"{CALENDAR_DIR}/absences.json", "r", encoding="utf-8") as f:
            absences = json.load(f) or {}
        
        if day in absences and 0 <= index < len(absences[day]):
            absences[day].pop(index)
            if not absences[day]:
                del absences[day]
        
        with open(f"{CALENDAR_DIR}/absences.json", "w", encoding="utf-8") as f:
            json.dump(absences, f, ensure_ascii=False, indent=2)
        
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route("/api/calendar/events", methods=["GET"])
def get_events():
    if not session.get('logged_in'):
        return {"status": "error"}, 401
    try:
        with open(f"{CALENDAR_DIR}/events.json", "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except:
        return jsonify([])

@app.route("/api/calendar/event", methods=["POST"])
def add_event():
    if not session.get('logged_in'):
        return {"status": "error"}, 401
    
    data = request.get_json()
    date = data.get("date")
    name = data.get("name")
    
    try:
        try:
            with open(f"{CALENDAR_DIR}/events.json", "r", encoding="utf-8") as f:
                events = json.load(f)
        except:
            events = []
        
        events.append({"date": date, "name": name})
        events.sort(key=lambda x: x["date"])
        
        with open(f"{CALENDAR_DIR}/events.json", "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route("/api/calendar/clubs", methods=["GET"])
def get_clubs():
    if not session.get('logged_in'):
        return {"status": "error"}, 401
    try:
        with open(f"{CALENDAR_DIR}/clubs.json", "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except:
        return jsonify({})

@app.route("/api/calendar/club", methods=["POST"])
def add_club():
    if not session.get('logged_in'):
        return {"status": "error"}, 401
    
    data = request.get_json()
    day = data.get("day")
    slot = data.get("slot")
    name = data.get("name")
    
    try:
        try:
            with open(f"{CALENDAR_DIR}/clubs.json", "r", encoding="utf-8") as f:
                clubs = json.load(f)
        except:
            clubs = {}
        
        key = f"{day}-{slot}"
        if name:
            clubs[key] = name
        elif key in clubs:
            del clubs[key]
        
        with open(f"{CALENDAR_DIR}/clubs.json", "w", encoding="utf-8") as f:
            json.dump(clubs, f, ensure_ascii=False, indent=2)
        
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route("/delete/<slide_type>/<filename>", methods=["DELETE"])
def delete_slide(slide_type, filename):
    if not session.get('logged_in'):
        return {"status": "error", "message": "Non autorisé"}, 401
    
    try:
        if slide_type == "preset":
            filepath = f"{PRESET_DIR}/{filename}"
        else:
            filepath = f"{CUSTOM_DIR}/{filename}"
        
        if os.path.exists(filepath):
            os.remove(filepath)
            return {"status": "ok"}
        else:
            return {"status": "error", "message": "File not found"}, 404
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

if __name__ == "__main__":
    import threading
    
    print("=" * 50)
    print("AFFICHAGE COLLÈGE")
    print("=" * 50)
    print(f"\nServeur web: http://localhost")
    print(f"Mot de passe éditeur: editor123")
    print(f"Mot de passe admin: admin123")
    print(f"Changez-les dans l'interface d'administration!\n")
    
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=80, debug=False),
        daemon=True
    ).start()
    
    time.sleep(1)
    
    try:
        run_slides()
    except KeyboardInterrupt:
        pygame.quit()