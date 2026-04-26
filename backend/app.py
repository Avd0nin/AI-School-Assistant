import os
import re
import sqlite3
import json
import html as html_utils
from datetime import datetime, timezone, timedelta
from functools import wraps
from io import BytesIO
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, request, render_template, jsonify, redirect, session, url_for, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash

from ai_core import AICore
from contest_routes import create_contest_blueprint

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

model = AICore()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv(
    "SESSION_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}

USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_]{3,32}$")
DEFAULT_CHAT_THREAD_TITLE = "Новый чат"
try:
    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    # Fallback for environments without tzdata installed.
    MOSCOW_TZ = timezone(timedelta(hours=3))


def collapse_spaces(value):
    return re.sub(r"\s+", " ", (value or "")).strip()


def to_moscow_time(value):
    raw = collapse_spaces(str(value or ""))
    if not raw:
        return raw

    parsed = None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue

    if parsed is None:
        return raw

    parsed_utc = parsed.replace(tzinfo=timezone.utc)
    return parsed_utc.astimezone(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")


def row_to_dict_with_moscow(row, fields=("created_at", "updated_at", "last_attempt_at", "best_attempt_at")):
    if row is None:
        return None
    data = dict(row)
    for field in fields:
        if field in data and data[field]:
            data[field] = to_moscow_time(data[field])
    return data


def rows_to_dicts_with_moscow(rows, fields=("created_at", "updated_at", "last_attempt_at", "best_attempt_at")):
    return [row_to_dict_with_moscow(row, fields=fields) for row in (rows or [])]


def plural_ru(value, one, few, many):
    number = abs(int(value or 0))
    mod10 = number % 10
    mod100 = number % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        return few
    return many


def normalize_contest_difficulty_label(value):
    raw = collapse_spaces(str(value or "")).lower()
    if not raw:
        return "средний"

    numeric_map = {
        "1": "очень легкий",
        "2": "легкий",
        "3": "ниже среднего",
        "4": "средний",
        "5": "средний+",
        "6": "выше среднего",
        "7": "сложный",
        "8": "очень сложный",
        "9": "предолимпиадный",
        "10": "олимпиадный",
    }
    if raw in numeric_map:
        return numeric_map[raw]

    alias_map = {
        "easy": "легкий",
        "medium": "средний",
        "hard": "сложный",
        "olymp": "олимпиадный",
        "очень лёгкий": "очень легкий",
        "очень лёгкий+": "очень легкий",
    }
    if raw in alias_map:
        return alias_map[raw]

    return collapse_spaces(str(value or "средний"))


def is_generic_contest_title(title):
    raw = collapse_spaces(title).lower()
    generic = {
        "",
        "контест",
        "новый контест",
        "contest",
        "new contest",
    }
    if raw in generic:
        return True
    return raw.startswith("контест на ")


def extract_contest_theme(description):
    text = collapse_spaces(description)
    if not text:
        return ""
    cleaned = re.sub(r"[^A-Za-zА-Яа-яЁё0-9_+\- ]+", " ", text)
    parts = [p for p in cleaned.split() if len(p) >= 3]
    if not parts:
        return ""
    return " ".join(parts[:4])


def build_contest_title(contest_payload, description, difficulty_label, tasks_count):
    payload_title = collapse_spaces(
        (contest_payload or {}).get("contest_title") or
        (contest_payload or {}).get("title") or
        ""
    )
    if payload_title and not is_generic_contest_title(payload_title):
        return payload_title[:160]

    theme = extract_contest_theme(description)
    count = int(tasks_count or 0)
    if count <= 0:
        tasks = (contest_payload or {}).get("tasks") if isinstance((contest_payload or {}).get("tasks"), list) else []
        count = len(tasks)
    count = max(1, count)
    tasks_part = f"{count} {plural_ru(count, 'задача', 'задачи', 'задач')}"
    if theme:
        return f"{theme}: {difficulty_label}, {tasks_part}"[:160]
    return f"{difficulty_label.capitalize()} контест: {tasks_part}"[:160]


def strip_html_tags(raw_html):
    without_tags = re.sub(r"<[^>]+>", " ", raw_html or "")
    return collapse_spaces(without_tags)


PDF_FONT_REGULAR = "Helvetica"
PDF_FONT_BOLD = "Helvetica-Bold"
PDF_FONT_READY = False


def ensure_pdf_fonts():
    global PDF_FONT_READY, PDF_FONT_REGULAR, PDF_FONT_BOLD
    if PDF_FONT_READY or not REPORTLAB_AVAILABLE:
        return

    regular_candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    bold_candidates = [
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]

    regular_path = next((path for path in regular_candidates if os.path.exists(path)), None)
    bold_path = next((path for path in bold_candidates if os.path.exists(path)), None)

    try:
        if regular_path:
            if "AppSans" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("AppSans", regular_path))
            PDF_FONT_REGULAR = "AppSans"
        if bold_path:
            if "AppSansBold" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("AppSansBold", bold_path))
            PDF_FONT_BOLD = "AppSansBold"
        elif regular_path:
            PDF_FONT_BOLD = PDF_FONT_REGULAR
    except Exception:
        PDF_FONT_REGULAR = "Helvetica"
        PDF_FONT_BOLD = "Helvetica-Bold"

    PDF_FONT_READY = True


def html_to_pdf_text(raw_html):
    text = str(raw_html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|h1|h2|h3|h4|h5|h6|section|article|ul|ol)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "• ", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_utils.unescape(text)
    lines = [collapse_spaces(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def wrap_pdf_line(text, font_name, font_size, max_width):
    if not REPORTLAB_AVAILABLE:
        return [text]
    words = collapse_spaces(text).split(" ")
    if not words:
        return [""]

    lines = []
    current = ""

    def width(value):
        return pdfmetrics.stringWidth(value, font_name, font_size)

    for word in words:
        if not word:
            continue
        candidate = word if not current else f"{current} {word}"
        if width(candidate) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        if width(word) <= max_width:
            current = word
            continue

        chunk = ""
        for ch in word:
            ch_candidate = f"{chunk}{ch}"
            if chunk and width(ch_candidate) > max_width:
                lines.append(chunk)
                chunk = ch
            else:
                chunk = ch_candidate
        current = chunk

    if current:
        lines.append(current)
    return lines or [""]


def build_summary_pdf(summary):
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("PDF generator is unavailable")

    ensure_pdf_fonts()

    title = collapse_spaces(summary.get("title") or "Конспект")
    meta = f'{summary.get("subject", "")} • {summary.get("klass", "")} класс • {summary.get("theme", "")}'
    body_text = html_to_pdf_text(summary.get("content_html") or "")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(title)

    page_width, page_height = A4
    left = 42
    right = page_width - 42
    top = page_height - 44
    bottom = 42
    line_height = 16
    y = top

    def new_page():
        nonlocal y
        pdf.showPage()
        y = top

    def draw_lines(lines, font_name, font_size):
        nonlocal y
        pdf.setFont(font_name, font_size)
        for line in lines:
            if y < bottom:
                new_page()
                pdf.setFont(font_name, font_size)
            pdf.drawString(left, y, line)
            y -= line_height

    title_lines = wrap_pdf_line(title, PDF_FONT_BOLD, 16, right - left)
    draw_lines(title_lines, PDF_FONT_BOLD, 16)
    y -= 6

    meta_lines = wrap_pdf_line(meta, PDF_FONT_REGULAR, 11, right - left)
    draw_lines(meta_lines, PDF_FONT_REGULAR, 11)
    y -= 10

    for paragraph in body_text.split("\n"):
        wrapped = wrap_pdf_line(paragraph, PDF_FONT_REGULAR, 12, right - left)
        draw_lines(wrapped, PDF_FONT_REGULAR, 12)
        y -= 6

    pdf.save()
    return buffer.getvalue()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db_path = app.config["DATABASE"]
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            theme TEXT NOT NULL,
            klass INTEGER NOT NULL,
            title TEXT NOT NULL,
            content_html TEXT NOT NULL,
            content_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_favorite INTEGER NOT NULL DEFAULT 0,
            is_archived INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS chat_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            summary_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_archived INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (summary_id) REFERENCES summaries(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            theme TEXT NOT NULL,
            klass INTEGER NOT NULL,
            generated_html TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_archived INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS test_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            correct_count INTEGER NOT NULL,
            duration_sec INTEGER,
            is_final INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            difficulty TEXT NOT NULL DEFAULT 'medium',
            tasks_count INTEGER NOT NULL DEFAULT 0,
            duration_minutes INTEGER NOT NULL DEFAULT 60,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_archived INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS contest_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contest_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            solved_count INTEGER NOT NULL,
            total_tasks INTEGER NOT NULL,
            partial_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            attempts_count INTEGER NOT NULL DEFAULT 0,
            time_used_sec INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contest_id) REFERENCES contests(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_summaries_user_created
            ON summaries(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_chat_threads_user_updated
            ON chat_threads(user_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_created
            ON chat_messages(thread_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_tests_user_created
            ON tests(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_test_attempts_test_created
            ON test_attempts(test_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_contests_user_created
            ON contests(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_contest_attempts_contest_created
            ON contest_attempts(contest_id, created_at DESC);
        """
    )
    columns = db.execute("PRAGMA table_info(test_attempts)").fetchall()
    column_names = {str(row["name"]).lower() for row in columns}
    if "is_final" not in column_names:
        db.execute("ALTER TABLE test_attempts ADD COLUMN is_final INTEGER NOT NULL DEFAULT 0")

    chat_columns = db.execute("PRAGMA table_info(chat_threads)").fetchall()
    chat_column_names = {str(row["name"]).lower() for row in chat_columns}
    if "summary_id" not in chat_column_names:
        db.execute("ALTER TABLE chat_threads ADD COLUMN summary_id INTEGER")

    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_threads_summary ON chat_threads(summary_id, user_id)"
    )
    db.commit()


def get_user_by_username(username):
    return get_db().execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (username,)
    ).fetchone()


def get_user_by_id(user_id):
    row = get_db().execute(
        "SELECT id, username, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    return row_to_dict_with_moscow(row, fields=("created_at",))


def current_user_id():
    user = g.get("current_user")
    return int(user["id"]) if user else None


def is_safe_next_url(next_url):
    if not next_url:
        return False
    parsed = urlparse(next_url)
    return parsed.scheme == "" and parsed.netloc == "" and next_url.startswith("/")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.get("current_user") is not None:
            return view(*args, **kwargs)

        if request.path.startswith("/api/"):
            return jsonify({"error": "Требуется авторизация"}), 401

        next_url = request.path
        if request.query_string:
            next_url = f"{request.path}?{request.query_string.decode('utf-8')}"
        return redirect(url_for("login", next=next_url))

    return wrapped_view


@app.before_request
def load_current_user():
    g.current_user = None
    user_id = session.get("user_id")
    if not user_id:
        return

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return
    g.current_user = user


@app.context_processor
def inject_current_user():
    return {"current_user": g.get("current_user")}


def validate_username(username):
    if not username:
        return "Логин обязателен."
    if not USERNAME_REGEX.fullmatch(username):
        return "Логин: 3-32 символа, только латинские буквы, цифры и _."
    return None


def validate_password(password):
    if not password:
        return "Пароль обязателен."
    if len(password) < 8:
        return "Пароль должен содержать минимум 8 символов."
    return None


def build_summary_title(subject, theme, klass, content_html):
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", content_html or "", flags=re.IGNORECASE | re.DOTALL)
    if h1_match:
        h1_text = strip_html_tags(h1_match.group(1))
        if h1_text:
            return h1_text[:120]

    safe_subject = collapse_spaces(subject) or "Предмет"
    safe_theme = collapse_spaces(theme) or "Тема"
    return f"{safe_subject}: {safe_theme} ({klass} класс)"[:120]


def build_summary_chat_title(summary):
    summary_title = collapse_spaces(summary["title"]) if summary else "Конспект"
    return f"Чат к конспекту: {summary_title}"[:160]


def build_summary_chat_welcome(summary):
    if not summary:
        return "Задавайте любые вопросы по этому конспекту."
    summary_title = collapse_spaces(summary["title"])
    return (
        f"Это чат по конспекту «{summary_title}». "
        f"Задавайте любые вопросы по теме — разберём шаг за шагом."
    )


def build_summary_system_context(summary):
    if not summary:
        return ""
    summary_text = strip_html_tags(summary.get("content_html") or "")
    summary_text = summary_text[:12000]
    summary_title = collapse_spaces(summary.get("title") or "Конспект")
    return (
        "Ты отвечаешь в режиме чата по конкретному конспекту. "
        "Опирайся в первую очередь на этот конспект, объясняй понятно и по теме. "
        "Если вопрос вне конспекта, мягко скажи об этом и предложи связанный разбор.\n\n"
        f"Название конспекта: {summary_title}\n"
        f"Текст конспекта:\n{summary_text}"
    )


def save_summary_for_user(user_id, subject, theme, klass, content_html):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO summaries (user_id, subject, theme, klass, title, content_html, content_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            collapse_spaces(subject),
            collapse_spaces(theme),
            int(klass),
            build_summary_title(subject, theme, klass, content_html),
            content_html,
            strip_html_tags(content_html)
        )
    )
    db.commit()
    return int(cursor.lastrowid)


def build_chat_thread_title(first_message):
    message = collapse_spaces(first_message)
    if not message:
        return DEFAULT_CHAT_THREAD_TITLE
    return f"{message[:87]}..." if len(message) > 90 else message


def create_chat_thread_for_user(user_id, first_message="", summary_id=None, title_override=None):
    title = collapse_spaces(title_override) if title_override else ""
    if not title:
        title = build_chat_thread_title(first_message)

    db = get_db()
    cursor = db.execute(
        "INSERT INTO chat_threads (user_id, title, summary_id) VALUES (?, ?, ?)",
        (user_id, title, summary_id)
    )
    db.commit()
    return int(cursor.lastrowid)


def get_chat_thread_for_user(user_id, thread_id):
    return get_db().execute(
        "SELECT id, user_id, title, summary_id, created_at, updated_at FROM chat_threads WHERE id = ? AND user_id = ? AND is_archived = 0",
        (thread_id, user_id)
    ).fetchone()


def get_summary_chat_thread_for_user(user_id, summary_id):
    return get_db().execute(
        """
        SELECT id, user_id, title, summary_id, created_at, updated_at
        FROM chat_threads
        WHERE user_id = ? AND summary_id = ? AND is_archived = 0
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (user_id, summary_id)
    ).fetchone()


def rename_chat_thread_if_default(thread_id, first_message):
    candidate_title = build_chat_thread_title(first_message)
    if candidate_title == DEFAULT_CHAT_THREAD_TITLE:
        return

    db = get_db()
    db.execute(
        """
        UPDATE chat_threads
        SET title = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND title = ?
        """,
        (candidate_title, thread_id, DEFAULT_CHAT_THREAD_TITLE)
    )
    db.commit()


def append_chat_message(thread_id, role, content):
    db = get_db()
    db.execute(
        "INSERT INTO chat_messages (thread_id, role, content) VALUES (?, ?, ?)",
        (thread_id, role, content)
    )
    db.execute(
        "UPDATE chat_threads SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (thread_id,)
    )
    db.commit()


def get_chat_messages(thread_id, limit=200):
    return get_db().execute(
        """
        SELECT role, content, created_at
        FROM chat_messages
        WHERE thread_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (thread_id, limit)
    ).fetchall()


def save_test_for_user(user_id, subject, theme, klass, generated_html):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO tests (user_id, subject, theme, klass, generated_html)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            collapse_spaces(subject),
            collapse_spaces(theme),
            int(klass),
            generated_html
        )
    )
    db.commit()
    return int(cursor.lastrowid)


def get_test_for_user(test_id, user_id):
    row = get_db().execute(
        """
        SELECT id, user_id, subject, theme, klass, generated_html, created_at
        FROM tests
        WHERE id = ? AND user_id = ? AND is_archived = 0
        """,
        (test_id, user_id)
    ).fetchone()
    return row_to_dict_with_moscow(row, fields=("created_at",))


def save_test_attempt(test_id, user_id, score, total_questions, correct_count, duration_sec=None, is_final=0):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO test_attempts (test_id, user_id, score, total_questions, correct_count, duration_sec, is_final)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (test_id, user_id, score, total_questions, correct_count, duration_sec, int(1 if is_final else 0))
    )
    db.commit()
    return int(cursor.lastrowid)


def get_profile_summaries(user_id, limit=25):
    rows = get_db().execute(
        """
        SELECT id, title, subject, theme, klass, created_at
        FROM summaries
        WHERE user_id = ? AND is_archived = 0
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()
    return rows_to_dicts_with_moscow(rows, fields=("created_at",))


def get_profile_chat_threads(user_id, limit=25):
    rows = get_db().execute(
        """
        SELECT
            ct.id,
            ct.title,
            ct.created_at,
            ct.updated_at,
            COUNT(cm.id) AS message_count
        FROM chat_threads ct
        LEFT JOIN chat_messages cm ON cm.thread_id = ct.id
        WHERE ct.user_id = ? AND ct.is_archived = 0
        GROUP BY ct.id
        ORDER BY ct.updated_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()
    return rows_to_dicts_with_moscow(rows, fields=("created_at", "updated_at"))


def get_profile_tests(user_id, limit=25):
    rows = get_db().execute(
        """
        SELECT
            t.id,
            t.subject,
            t.theme,
            t.klass,
            t.created_at,
            (SELECT COUNT(*) FROM test_attempts a WHERE a.test_id = t.id AND a.is_final = 1) AS attempts_count,
            (SELECT a.score FROM test_attempts a WHERE a.test_id = t.id AND a.is_final = 1 ORDER BY a.created_at DESC, a.id DESC LIMIT 1) AS last_score,
            (SELECT a.correct_count FROM test_attempts a WHERE a.test_id = t.id AND a.is_final = 1 ORDER BY a.created_at DESC, a.id DESC LIMIT 1) AS last_correct_count,
            (SELECT a.total_questions FROM test_attempts a WHERE a.test_id = t.id AND a.is_final = 1 ORDER BY a.created_at DESC, a.id DESC LIMIT 1) AS last_total_questions,
            (SELECT a.created_at FROM test_attempts a WHERE a.test_id = t.id AND a.is_final = 1 ORDER BY a.created_at DESC, a.id DESC LIMIT 1) AS last_attempt_at
        FROM tests t
        WHERE t.user_id = ? AND t.is_archived = 0
        ORDER BY t.created_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()
    return rows_to_dicts_with_moscow(rows, fields=("created_at", "last_attempt_at"))


def get_summary_for_user(summary_id, user_id):
    row = get_db().execute(
        """
        SELECT id, title, subject, theme, klass, content_html, created_at
        FROM summaries
        WHERE id = ? AND user_id = ? AND is_archived = 0
        """,
        (summary_id, user_id)
    ).fetchone()
    return row_to_dict_with_moscow(row, fields=("created_at",))


def get_test_attempts_for_user(test_id, user_id, limit=30):
    rows = get_db().execute(
        """
        SELECT id, score, total_questions, correct_count, duration_sec, created_at
        FROM test_attempts
        WHERE test_id = ? AND user_id = ? AND is_final = 1
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (test_id, user_id, limit)
    ).fetchall()
    return rows_to_dicts_with_moscow(rows, fields=("created_at",))


def save_contest_for_user(user_id, payload, description="", difficulty="medium", tasks_count=0, duration_minutes=60):
    contest_payload = payload if isinstance(payload, dict) else {}
    tasks = contest_payload.get("tasks") if isinstance(contest_payload.get("tasks"), list) else []
    difficulty_label = normalize_contest_difficulty_label(difficulty)
    title = build_contest_title(
        contest_payload=contest_payload,
        description=description,
        difficulty_label=difficulty_label,
        tasks_count=(int(tasks_count) if tasks_count else len(tasks)),
    )
    contest_payload["contest_title"] = title
    contest_payload["difficulty_label"] = difficulty_label

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO contests (user_id, title, description, difficulty, tasks_count, duration_minutes, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            title[:160],
            collapse_spaces(description or ""),
            difficulty_label,
            int(tasks_count) if tasks_count else len(tasks),
            max(15, int(duration_minutes or 60)),
            json.dumps(contest_payload, ensure_ascii=False),
        ),
    )
    db.commit()
    return int(cursor.lastrowid)


def save_contest_attempt(
        contest_id,
        user_id,
        score,
        solved_count,
        total_tasks,
        partial_count=0,
        failed_count=0,
        attempts_count=0,
        time_used_sec=0,
):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO contest_attempts (
            contest_id, user_id, score, solved_count, total_tasks,
            partial_count, failed_count, attempts_count, time_used_sec
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contest_id,
            user_id,
            int(score),
            int(solved_count),
            int(total_tasks),
            int(partial_count),
            int(failed_count),
            int(attempts_count),
            int(time_used_sec),
        ),
    )
    db.commit()
    return int(cursor.lastrowid)


def get_contest_for_user(contest_id, user_id):
    row = get_db().execute(
        """
        SELECT id, user_id, title, description, difficulty, tasks_count, duration_minutes, payload_json, created_at
        FROM contests
        WHERE id = ? AND user_id = ? AND is_archived = 0
        """,
        (contest_id, user_id),
    ).fetchone()
    return row_to_dict_with_moscow(row, fields=("created_at",))


def get_contest_attempts_for_user(contest_id, user_id, limit=30):
    rows = get_db().execute(
        """
        SELECT
            id, score, solved_count, total_tasks, partial_count, failed_count,
            attempts_count, time_used_sec, created_at
        FROM contest_attempts
        WHERE contest_id = ? AND user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (contest_id, user_id, limit),
    ).fetchall()
    return rows_to_dicts_with_moscow(rows, fields=("created_at",))


def get_profile_contests(user_id, limit=25):
    rows = get_db().execute(
        """
        SELECT
            c.id,
            c.title,
            c.description,
            c.difficulty,
            c.tasks_count,
            c.duration_minutes,
            c.created_at,
            (SELECT COUNT(*) FROM contest_attempts a WHERE a.contest_id = c.id) AS attempts_count,
            (
                SELECT a.score
                FROM contest_attempts a
                WHERE a.contest_id = c.id
                ORDER BY a.score DESC, a.solved_count DESC, a.time_used_sec ASC, a.created_at DESC, a.id DESC
                LIMIT 1
            ) AS best_score,
            (
                SELECT a.solved_count
                FROM contest_attempts a
                WHERE a.contest_id = c.id
                ORDER BY a.score DESC, a.solved_count DESC, a.time_used_sec ASC, a.created_at DESC, a.id DESC
                LIMIT 1
            ) AS best_solved_count,
            (
                SELECT a.total_tasks
                FROM contest_attempts a
                WHERE a.contest_id = c.id
                ORDER BY a.score DESC, a.solved_count DESC, a.time_used_sec ASC, a.created_at DESC, a.id DESC
                LIMIT 1
            ) AS best_total_tasks,
            (
                SELECT a.created_at
                FROM contest_attempts a
                WHERE a.contest_id = c.id
                ORDER BY a.score DESC, a.solved_count DESC, a.time_used_sec ASC, a.created_at DESC, a.id DESC
                LIMIT 1
            ) AS best_attempt_at
        FROM contests c
        WHERE c.user_id = ? AND c.is_archived = 0
        ORDER BY c.created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return rows_to_dicts_with_moscow(rows, fields=("created_at", "best_attempt_at"))


def serialize_contest_row(row):
    if row is None:
        return None
    data = dict(row)
    data["difficulty_label"] = normalize_contest_difficulty_label(data.get("difficulty"))
    return data


def get_profile_stats(user_id):
    db = get_db()

    def row_int(row, key):
        if row is None:
            return 0
        try:
            return int(row[key] or 0)
        except (KeyError, TypeError, ValueError):
            return 0

    summaries_count = db.execute(
        "SELECT COUNT(*) AS value FROM summaries WHERE user_id = ? AND is_archived = 0",
        (user_id,),
    ).fetchone()["value"]

    chats_row = db.execute(
        """
        SELECT
            COUNT(DISTINCT ct.id) AS threads_count,
            COUNT(cm.id) AS messages_count
        FROM chat_threads ct
        LEFT JOIN chat_messages cm ON cm.thread_id = ct.id
        WHERE ct.user_id = ? AND ct.is_archived = 0
        """,
        (user_id,),
    ).fetchone()

    tests_row = db.execute(
        """
        SELECT
            COUNT(DISTINCT t.id) AS tests_count,
            COUNT(CASE WHEN a.is_final = 1 THEN a.id END) AS attempts_count,
            COALESCE(MAX(CASE WHEN a.is_final = 1 THEN a.score END), 0) AS best_score,
            COALESCE(ROUND(AVG(CASE WHEN a.is_final = 1 THEN a.score END)), 0) AS avg_score
        FROM tests t
        LEFT JOIN test_attempts a ON a.test_id = t.id
        WHERE t.user_id = ? AND t.is_archived = 0
        """,
        (user_id,),
    ).fetchone()

    contests_row = db.execute(
        """
        SELECT
            COUNT(DISTINCT c.id) AS contests_count,
            COUNT(a.id) AS attempts_count,
            COALESCE(MAX(a.score), 0) AS best_score,
            COALESCE(SUM(a.solved_count), 0) AS solved_total
        FROM contests c
        LEFT JOIN contest_attempts a ON a.contest_id = c.id
        WHERE c.user_id = ? AND c.is_archived = 0
        """,
        (user_id,),
    ).fetchone()

    return {
        "summaries_count": int(summaries_count or 0),
        "chat_threads_count": row_int(chats_row, "threads_count"),
        "chat_messages_count": row_int(chats_row, "messages_count"),
        "tests_count": row_int(tests_row, "tests_count"),
        "test_attempts_count": row_int(tests_row, "attempts_count"),
        "test_best_score": row_int(tests_row, "best_score"),
        "test_avg_score": row_int(tests_row, "avg_score"),
        "contests_count": row_int(contests_row, "contests_count"),
        "contest_attempts_count": row_int(contests_row, "attempts_count"),
        "contest_best_score": row_int(contests_row, "best_score"),
        "contest_solved_total": row_int(contests_row, "solved_total"),
    }


app.register_blueprint(
    create_contest_blueprint(
        model,
        save_contest_callback=save_contest_for_user,
        current_user_id_callback=current_user_id,
    )
)


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.get("current_user") is not None:
        return redirect(url_for("home"))

    error = None
    username = ""
    next_url = (request.args.get("next") or "").strip()

    if request.method == 'POST':
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""
        next_url = (request.form.get("next") or "").strip()

        error = validate_username(username) or validate_password(password)

        if not error and password != password_confirm:
            error = "Пароли не совпадают."

        if not error:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password))
                )
                db.commit()
            except sqlite3.IntegrityError:
                error = "Пользователь с таким логином уже существует."

        if not error:
            user = get_user_by_username(username)
            session.clear()
            session["user_id"] = int(user["id"])
            if is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("home"))

    return render_template(
        "register.html",
        error=error,
        username=username,
        next_url=next_url
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.get("current_user") is not None:
        return redirect(url_for("home"))

    error = None
    username = ""
    next_url = (request.args.get("next") or "").strip()

    if request.method == 'POST':
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        next_url = (request.form.get("next") or "").strip()

        if not username or not password:
            error = "Введите логин и пароль."
        else:
            user = get_user_by_username(username)
            if user is None or not check_password_hash(user["password_hash"], password):
                error = "Неверный логин или пароль."
            else:
                session.clear()
                session["user_id"] = int(user["id"])
                if is_safe_next_url(next_url):
                    return redirect(next_url)
                return redirect(url_for("home"))

    return render_template(
        "login.html",
        error=error,
        username=username,
        next_url=next_url
    )


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route('/make_summary')
@login_required
def make_summary():
    return render_template('generate_summary.html')


@app.route('/help', methods=['GET'])
def info():
    return render_template('help.html')


@app.route('/chat', methods=['GET'])
@login_required
def chat():
    thread_id = request.args.get('thread_id', type=int)
    initial_thread_id = None
    initial_messages = []
    chat_welcome_message = "Привет! Я помогу с учебой: объясню тему, дам план подготовки, сделаю краткий разбор и примеры. С чего начнем?"

    if thread_id:
        thread = get_chat_thread_for_user(current_user_id(), thread_id)
        if thread:
            initial_thread_id = int(thread['id'])
            summary_id = thread["summary_id"]
            if summary_id:
                summary = get_summary_for_user(int(summary_id), current_user_id())
                if summary:
                    chat_welcome_message = build_summary_chat_welcome(summary)
            rows = get_chat_messages(initial_thread_id, limit=250)
            initial_messages = [
                {
                    "role": row["role"],
                    "content": row["content"]
                }
                for row in rows
            ]

    return render_template(
        'chat.html',
        initial_thread_id=initial_thread_id,
        initial_messages=initial_messages,
        chat_welcome_message=chat_welcome_message
    )


@app.route('/make_test', methods=['GET'])
@login_required
def make_test():
    mode = str(request.args.get('mode', 'test')).strip().lower()
    initial_mode = 'contest' if mode == 'contest' else 'test'
    initial_test_id = request.args.get('test_id', type=int)
    initial_contest_id = request.args.get('contest_id', type=int)
    return render_template(
        'generate_test.html',
        initial_mode=initial_mode,
        initial_test_id=initial_test_id,
        initial_contest_id=initial_contest_id,
    )


@app.route('/make_contest', methods=['GET'])
@login_required
def make_contest():
    return redirect(url_for('make_test', mode='contest'))


@app.route('/profile', methods=['GET'])
@login_required
def profile():
    tab = (request.args.get('tab') or 'summaries').strip().lower()
    if tab not in {'summaries', 'chats', 'tests', 'contests'}:
        tab = 'summaries'

    user_id = current_user_id()
    deleted = str(request.args.get("deleted", "")).strip() == "1"
    delete_error = str(request.args.get("delete_error", "")).strip() == "1"

    contests_rows = get_profile_contests(user_id)
    contests = [serialize_contest_row(row) for row in contests_rows]

    return render_template(
        'profile.html',
        active_tab=tab,
        deleted=deleted,
        delete_error=delete_error,
        profile_stats=get_profile_stats(user_id),
        summaries=get_profile_summaries(user_id),
        chats=get_profile_chat_threads(user_id),
        tests=get_profile_tests(user_id),
        contests=contests,
    )


@app.route('/profile/delete_data', methods=['POST'])
@login_required
def delete_profile_data():
    confirmation = collapse_spaces(request.form.get("confirm_text", "")).lower()
    if confirmation not in {"удалить", "delete"}:
        return redirect(url_for("profile", tab="summaries", delete_error=1))

    user_id = current_user_id()
    db = get_db()
    db.execute("DELETE FROM summaries WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM chat_threads WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM tests WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM contests WHERE user_id = ?", (user_id,))
    db.commit()
    return redirect(url_for("profile", tab="summaries", deleted=1))


@app.route('/profile/summary/<int:summary_id>', methods=['GET'])
@login_required
def view_summary(summary_id):
    summary = get_summary_for_user(summary_id, current_user_id())
    if summary is None:
        return redirect(url_for('profile', tab='summaries'))

    return render_template('profile_summary.html', summary=summary)


@app.route('/profile/summary/<int:summary_id>/download_pdf', methods=['GET'])
@login_required
def download_summary_pdf(summary_id):
    summary = get_summary_for_user(summary_id, current_user_id())
    if summary is None:
        return redirect(url_for('profile', tab='summaries'))

    try:
        pdf_bytes = build_summary_pdf(summary)
    except Exception as error:
        print(f"Ошибка генерации PDF: {error}")
        return redirect(url_for('view_summary', summary_id=summary_id))

    filename = f"summary_{int(summary_id)}.pdf"
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route('/profile/summary/<int:summary_id>/chat', methods=['GET'])
@login_required
def open_summary_chat(summary_id):
    user_id = current_user_id()
    summary = get_summary_for_user(summary_id, user_id)
    if summary is None:
        return redirect(url_for('profile', tab='summaries'))

    thread = get_summary_chat_thread_for_user(user_id, summary_id)
    if thread:
        thread_id = int(thread["id"])
    else:
        thread_id = create_chat_thread_for_user(
            user_id=user_id,
            summary_id=summary_id,
            title_override=build_summary_chat_title(summary),
        )
        append_chat_message(thread_id, 'assistant', build_summary_chat_welcome(summary))

    return redirect(url_for('chat', thread_id=thread_id))


@app.route('/profile/test/<int:test_id>', methods=['GET'])
@login_required
def view_test(test_id):
    user_id = current_user_id()
    test = get_test_for_user(test_id, user_id)
    if test is None:
        return redirect(url_for('profile', tab='tests'))

    attempts = get_test_attempts_for_user(test_id, user_id)
    return render_template('profile_test.html', test=test, attempts=attempts)


@app.route('/profile/contest/<int:contest_id>', methods=['GET'])
@login_required
def view_contest(contest_id):
    user_id = current_user_id()
    contest = get_contest_for_user(contest_id, user_id)
    if contest is None:
        return redirect(url_for('profile', tab='contests'))

    attempts = get_contest_attempts_for_user(contest_id, user_id)
    return render_template('profile_contest.html', contest=serialize_contest_row(contest), attempts=attempts)


@app.route('/api/question', methods=['POST'])
@login_required
def asking():
    data = request.get_json(silent=True) or {}
    subject = collapse_spaces(data.get('subject'))
    theme = collapse_spaces(data.get('theme'))
    question = collapse_spaces(data.get('question'))
    history = data.get('message_history', [])

    if not question:
        return jsonify({'error': 'Пустой вопрос'}), 400

    try:
        klass = int(data.get('klass', 6))
    except (TypeError, ValueError):
        klass = 6

    user_id = current_user_id()
    thread_id = data.get('thread_id')
    try:
        thread_id = int(thread_id) if thread_id is not None else None
    except (TypeError, ValueError):
        thread_id = None

    thread = get_chat_thread_for_user(user_id, thread_id) if thread_id else None
    if thread is None:
        thread_id = create_chat_thread_for_user(user_id, question)
    else:
        if not thread["summary_id"]:
            rename_chat_thread_if_default(thread_id, question)

    append_chat_message(thread_id, 'user', question)

    try:
        history_for_model = history if isinstance(history, list) else []
        if thread and thread["summary_id"]:
            summary = get_summary_for_user(int(thread["summary_id"]), user_id)
            if summary:
                subject = summary["subject"]
                theme = summary["theme"]
                try:
                    klass = int(summary["klass"])
                except (TypeError, ValueError):
                    klass = 6
                summary_system_context = build_summary_system_context(summary)
                history_for_model = [{"role": "system", "content": summary_system_context}] + history_for_model

        answer = model.answer_question(subject, klass, theme, question, history_for_model)
    except Exception as e:
        print(f"Ошибка чата: {str(e)}")
        return jsonify({
            'error': 'Ошибка при получении ответа от модели.',
            'thread_id': thread_id
        }), 500

    append_chat_message(thread_id, 'assistant', answer)

    return jsonify({
        'answer': answer,
        'thread_id': thread_id
    })


@app.route('/api/test')
@login_required
def generate_test():
    subject = request.args.get('subject')
    theme = request.args.get('theme')

    try:
        klass = int(request.args.get('class'))
    except (TypeError, ValueError):
        return "Некорректный класс", 400

    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400

    try:
        generated_html = model.create_test(subject, klass, theme).lstrip('```html\n').rstrip('\n```')
        test_id = save_test_for_user(current_user_id(), subject, theme, klass, generated_html)
        response = make_response(generated_html)
        response.headers['X-Test-Id'] = str(test_id)
        return response
    except Exception as e:
        print(f"Ошибка генерации теста: {str(e)}")
        return "<p>Ошибка при генерации теста.</p>", 500


@app.route('/api/test_saved/<int:test_id>', methods=['GET'])
@login_required
def get_saved_test(test_id):
    test = get_test_for_user(test_id, current_user_id())
    if test is None:
        return jsonify({"error": "Тест не найден"}), 404
    return jsonify(
        {
            "id": int(test["id"]),
            "subject": test["subject"],
            "theme": test["theme"],
            "klass": int(test["klass"]),
            "generated_html": test["generated_html"],
            "created_at": test["created_at"],
        }
    )


@app.route('/api/test_attempt', methods=['POST'])
@login_required
def save_attempt():
    data = request.get_json(silent=True) or {}

    try:
        test_id = int(data.get('test_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Некорректный test_id'}), 400

    user_id = current_user_id()
    test = get_test_for_user(test_id, user_id)
    if test is None:
        return jsonify({'error': 'Тест не найден'}), 404

    try:
        score = int(data.get('score', 0))
        total_questions = int(data.get('total_questions', 0))
        correct_count = int(data.get('correct_count', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Некорректные числовые значения'}), 400

    if total_questions <= 0:
        return jsonify({'error': 'total_questions должен быть больше 0'}), 400
    if correct_count < 0 or correct_count > total_questions:
        return jsonify({'error': 'correct_count вне диапазона'}), 400

    score = max(0, min(score, 100))

    duration_sec = data.get('duration_sec')
    if duration_sec is not None:
        try:
            duration_sec = int(duration_sec)
        except (TypeError, ValueError):
            duration_sec = None
        if duration_sec is not None and duration_sec < 0:
            duration_sec = None
    is_final_raw = data.get('is_final', False)
    if isinstance(is_final_raw, str):
        is_final = is_final_raw.strip().lower() in {"1", "true", "yes", "y", "final"}
    else:
        is_final = bool(is_final_raw)

    # Не считаем попытку, пока тест не завершён пользователем.
    if not is_final:
        return jsonify({'ok': True, 'attempt_id': None, 'skipped': 'non_final'})

    attempt_id = save_test_attempt(
        test_id=test_id,
        user_id=user_id,
        score=score,
        total_questions=total_questions,
        correct_count=correct_count,
        duration_sec=duration_sec,
        is_final=is_final
    )

    return jsonify({'ok': True, 'attempt_id': attempt_id})


@app.route('/api/contest_saved/<int:contest_id>', methods=['GET'])
@login_required
def get_saved_contest(contest_id):
    contest = get_contest_for_user(contest_id, current_user_id())
    if contest is None:
        return jsonify({"error": "Контест не найден"}), 404

    try:
        payload = json.loads(contest["payload_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}

    payload["contest_id"] = int(contest["id"])
    payload["contest_title"] = collapse_spaces(payload.get("contest_title") or contest["title"])
    payload["difficulty_label"] = normalize_contest_difficulty_label(contest["difficulty"])
    return jsonify(
        {
            "contest": payload,
            "duration_minutes": int(contest["duration_minutes"] or 60),
            "title": contest["title"],
            "difficulty_label": normalize_contest_difficulty_label(contest["difficulty"]),
            "created_at": contest["created_at"],
        }
    )


@app.route('/api/contest_attempt', methods=['POST'])
@login_required
def save_contest_attempt_api():
    data = request.get_json(silent=True) or {}

    try:
        contest_id = int(data.get('contest_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Некорректный contest_id'}), 400

    user_id = current_user_id()
    contest = get_contest_for_user(contest_id, user_id)
    if contest is None:
        return jsonify({'error': 'Контест не найден'}), 404

    required_int_fields = [
        "score",
        "solved_count",
        "total_tasks",
        "partial_count",
        "failed_count",
        "attempts_count",
        "time_used_sec",
    ]
    parsed = {}
    for field in required_int_fields:
        try:
            parsed[field] = int(data.get(field, 0))
        except (TypeError, ValueError):
            return jsonify({'error': f'Некорректное поле: {field}'}), 400

    if parsed["total_tasks"] <= 0:
        return jsonify({'error': 'total_tasks должен быть больше 0'}), 400
    if parsed["solved_count"] < 0 or parsed["solved_count"] > parsed["total_tasks"]:
        return jsonify({'error': 'solved_count вне диапазона'}), 400
    if parsed["partial_count"] < 0 or parsed["failed_count"] < 0:
        return jsonify({'error': 'partial_count/failed_count не могут быть отрицательными'}), 400
    if parsed["score"] < 0:
        parsed["score"] = 0
    if parsed["score"] > 100:
        parsed["score"] = 100
    if parsed["time_used_sec"] < 0:
        parsed["time_used_sec"] = 0

    attempt_id = save_contest_attempt(
        contest_id=contest_id,
        user_id=user_id,
        score=parsed["score"],
        solved_count=parsed["solved_count"],
        total_tasks=parsed["total_tasks"],
        partial_count=parsed["partial_count"],
        failed_count=parsed["failed_count"],
        attempts_count=parsed["attempts_count"],
        time_used_sec=parsed["time_used_sec"],
    )
    return jsonify({"ok": True, "attempt_id": attempt_id})


@app.route('/api/check_answer', methods=['POST'])
@login_required
def check_answer():
    try:
        data = request.get_json(silent=True) or {}
        question = collapse_spaces(data.get('question'))
        user_answer = collapse_spaces(data.get('answer'))
        subject = collapse_spaces(data.get('subject'))
        theme = collapse_spaces(data.get('theme'))

        try:
            klass = int(data.get('klass', 6))
        except (TypeError, ValueError):
            klass = 6

        if not question or not user_answer:
            return jsonify({
                "is_correct": False,
                "feedback": "Вопрос и ответ не могут быть пустыми.",
                "correct_answer": ""
            })

        checked_answer = model.check_answer_with_ai(
            subject, question, user_answer, klass, theme)

        if not all(key in checked_answer for key in ['is_correct', 'feedback', 'correct_answer']):
            raise ValueError("Некорректный формат ответа API")

        return jsonify(checked_answer)

    except Exception as e:
        print(f"Ошибка проверки ответа: {str(e)}")
        return jsonify({
            "is_correct": False,
            "feedback": "Ошибка проверки. Попробуйте ещё раз.",
            "correct_answer": ""
        })


@app.route('/api/summary')
@login_required
def action():
    subject = request.args.get('subject')
    theme = request.args.get('theme')

    try:
        klass = int(request.args.get('klass'))
    except (TypeError, ValueError):
        return "Некорректный класс", 400

    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400

    try:
        generated_html = model.generaty_summary(subject, klass, theme)
        summary_id = save_summary_for_user(current_user_id(), subject, theme, klass, generated_html)
        response = make_response(generated_html)
        response.headers['X-Summary-Id'] = str(summary_id)
        return response
    except Exception as e:
        print(f"Ошибка генерации конспекта: {str(e)}")
        return render_template('summary_example_snippet.html')


with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True)
