import os
import re
import sqlite3
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, request, render_template, jsonify, redirect, session, url_for, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash

from ai_core import AICore
from contest_routes import create_contest_blueprint


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


def collapse_spaces(value):
    return re.sub(r"\s+", " ", (value or "")).strip()


def strip_html_tags(raw_html):
    without_tags = re.sub(r"<[^>]+>", " ", raw_html or "")
    return collapse_spaces(without_tags)


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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_archived INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE,
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
        """
    )
    db.commit()


def get_user_by_username(username):
    return get_db().execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (username,)
    ).fetchone()


def get_user_by_id(user_id):
    return get_db().execute(
        "SELECT id, username FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()


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


def create_chat_thread_for_user(user_id, first_message=""):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO chat_threads (user_id, title) VALUES (?, ?)",
        (user_id, build_chat_thread_title(first_message))
    )
    db.commit()
    return int(cursor.lastrowid)


def get_chat_thread_for_user(user_id, thread_id):
    return get_db().execute(
        "SELECT id, user_id, title, created_at, updated_at FROM chat_threads WHERE id = ? AND user_id = ? AND is_archived = 0",
        (thread_id, user_id)
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
    return get_db().execute(
        """
        SELECT id, user_id, subject, theme, klass, generated_html, created_at
        FROM tests
        WHERE id = ? AND user_id = ? AND is_archived = 0
        """,
        (test_id, user_id)
    ).fetchone()


def save_test_attempt(test_id, user_id, score, total_questions, correct_count, duration_sec=None):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO test_attempts (test_id, user_id, score, total_questions, correct_count, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (test_id, user_id, score, total_questions, correct_count, duration_sec)
    )
    db.commit()
    return int(cursor.lastrowid)


def get_profile_summaries(user_id, limit=25):
    return get_db().execute(
        """
        SELECT id, title, subject, theme, klass, created_at
        FROM summaries
        WHERE user_id = ? AND is_archived = 0
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()


def get_profile_chat_threads(user_id, limit=25):
    return get_db().execute(
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


def get_profile_tests(user_id, limit=25):
    return get_db().execute(
        """
        SELECT
            t.id,
            t.subject,
            t.theme,
            t.klass,
            t.created_at,
            (SELECT COUNT(*) FROM test_attempts a WHERE a.test_id = t.id) AS attempts_count,
            (SELECT a.score FROM test_attempts a WHERE a.test_id = t.id ORDER BY a.created_at DESC, a.id DESC LIMIT 1) AS last_score,
            (SELECT a.correct_count FROM test_attempts a WHERE a.test_id = t.id ORDER BY a.created_at DESC, a.id DESC LIMIT 1) AS last_correct_count,
            (SELECT a.total_questions FROM test_attempts a WHERE a.test_id = t.id ORDER BY a.created_at DESC, a.id DESC LIMIT 1) AS last_total_questions,
            (SELECT a.created_at FROM test_attempts a WHERE a.test_id = t.id ORDER BY a.created_at DESC, a.id DESC LIMIT 1) AS last_attempt_at
        FROM tests t
        WHERE t.user_id = ? AND t.is_archived = 0
        ORDER BY t.created_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()


def get_summary_for_user(summary_id, user_id):
    return get_db().execute(
        """
        SELECT id, title, subject, theme, klass, content_html, created_at
        FROM summaries
        WHERE id = ? AND user_id = ? AND is_archived = 0
        """,
        (summary_id, user_id)
    ).fetchone()


def get_test_attempts_for_user(test_id, user_id, limit=30):
    return get_db().execute(
        """
        SELECT id, score, total_questions, correct_count, duration_sec, created_at
        FROM test_attempts
        WHERE test_id = ? AND user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (test_id, user_id, limit)
    ).fetchall()


app.register_blueprint(create_contest_blueprint(model))


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

    if thread_id:
        thread = get_chat_thread_for_user(current_user_id(), thread_id)
        if thread:
            initial_thread_id = int(thread['id'])
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
        initial_messages=initial_messages
    )


@app.route('/make_test', methods=['GET'])
@login_required
def make_test():
    mode = str(request.args.get('mode', 'test')).strip().lower()
    initial_mode = 'contest' if mode == 'contest' else 'test'
    return render_template('generate_test.html', initial_mode=initial_mode)


@app.route('/make_contest', methods=['GET'])
@login_required
def make_contest():
    return redirect(url_for('make_test', mode='contest'))


@app.route('/profile', methods=['GET'])
@login_required
def profile():
    tab = (request.args.get('tab') or 'summaries').strip().lower()
    if tab not in {'summaries', 'chats', 'tests'}:
        tab = 'summaries'

    user_id = current_user_id()

    return render_template(
        'profile.html',
        active_tab=tab,
        summaries=get_profile_summaries(user_id),
        chats=get_profile_chat_threads(user_id),
        tests=get_profile_tests(user_id)
    )


@app.route('/profile/summary/<int:summary_id>', methods=['GET'])
@login_required
def view_summary(summary_id):
    summary = get_summary_for_user(summary_id, current_user_id())
    if summary is None:
        return redirect(url_for('profile', tab='summaries'))

    return render_template('profile_summary.html', summary=summary)


@app.route('/profile/test/<int:test_id>', methods=['GET'])
@login_required
def view_test(test_id):
    user_id = current_user_id()
    test = get_test_for_user(test_id, user_id)
    if test is None:
        return redirect(url_for('profile', tab='tests'))

    attempts = get_test_attempts_for_user(test_id, user_id)
    return render_template('profile_test.html', test=test, attempts=attempts)


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
        rename_chat_thread_if_default(thread_id, question)

    append_chat_message(thread_id, 'user', question)

    try:
        answer = model.answer_question(subject, klass, theme, question, history)
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

    attempt_id = save_test_attempt(
        test_id=test_id,
        user_id=user_id,
        score=score,
        total_questions=total_questions,
        correct_count=correct_count,
        duration_sec=duration_sec
    )

    return jsonify({'ok': True, 'attempt_id': attempt_id})


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
