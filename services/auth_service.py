import logging
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from models.database import get_connection

logger = logging.getLogger(__name__)


def register(email: str, name: str, password: str) -> dict:
    email = email.strip().lower()
    name = name.strip()

    if not email or '@' not in email or '.' not in email.split('@')[-1]:
        raise ValueError('Некоректний email')
    if not name or len(name) < 2:
        raise ValueError("Ім'я занадто коротке (мінімум 2 символи)")
    if not password or len(password) < 6:
        raise ValueError('Пароль має бути не менше 6 символів')

    conn = get_connection()
    try:
        existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            raise ValueError('Цей email вже зареєстровано')

        password_hash = generate_password_hash(password)
        now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        cur = conn.execute(
            'INSERT INTO users (email, password_hash, name, created_at) VALUES (?, ?, ?, ?)',
            (email, password_hash, name, now),
        )
        conn.commit()
        return {'id': cur.lastrowid, 'email': email, 'name': name}
    finally:
        conn.close()


def login(email: str, password: str) -> dict | None:
    email = email.strip().lower()
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT id, email, name, password_hash FROM users WHERE email = ?', (email,)
        ).fetchone()
        if row is None:
            return None
        user = dict(row)
        if not check_password_hash(user.pop('password_hash'), password):
            return None
        return user
    finally:
        conn.close()


def get_user(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT id, email, name, created_at FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
