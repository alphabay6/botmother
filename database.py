"""
Database module — thread-safe SQLite operations for all bot data.
Handles: users, files, subscriptions, admins, approvals, bans, versions, resource logs.
"""
import sqlite3
import threading
import logging
from datetime import datetime
from config import DATABASE_PATH

logger = logging.getLogger(__name__)
DB_LOCK = threading.Lock()


def get_connection():
    """Create a new SQLite connection."""
    return sqlite3.connect(DATABASE_PATH, check_same_thread=False)


def init_db(owner_id, admin_id):
    """Initialize all database tables."""
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = get_connection()
        c = conn.cursor()

        # --- Existing tables ---
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                      PRIMARY KEY (user_id, file_name))''')

        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY, joined_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')

        # --- New tables ---
        c.execute('''CREATE TABLE IF NOT EXISTS pending_approvals
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      file_name TEXT,
                      file_type TEXT,
                      submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                      status TEXT DEFAULT 'pending',
                      reviewed_by INTEGER,
                      reviewed_at TEXT,
                      reject_reason TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY,
                      banned_by INTEGER,
                      reason TEXT,
                      banned_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS file_versions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      file_name TEXT,
                      version INTEGER,
                      backup_path TEXT,
                      created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS auto_restart_config
                     (user_id INTEGER,
                      file_name TEXT,
                      enabled INTEGER DEFAULT 1,
                      max_retries INTEGER DEFAULT 5,
                      restart_count INTEGER DEFAULT 0,
                      last_restart TEXT,
                      PRIMARY KEY (user_id, file_name))''')

        c.execute('''CREATE TABLE IF NOT EXISTS resource_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      file_name TEXT,
                      cpu_percent REAL,
                      memory_mb REAL,
                      logged_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS maintenance_mode
                     (id INTEGER PRIMARY KEY DEFAULT 1,
                      enabled INTEGER DEFAULT 0,
                      message TEXT DEFAULT "Bot is under maintenance. Please try again later.",
                      ends_at TEXT)''')
                      
        c.execute('''CREATE TABLE IF NOT EXISTS script_env_vars
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      file_name TEXT,
                      env_key TEXT,
                      env_value TEXT,
                      UNIQUE(user_id, file_name, env_key))''')

        # --- Free Trial ---
        c.execute('''CREATE TABLE IF NOT EXISTS user_trials
                     (user_id INTEGER PRIMARY KEY,
                      started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                      expires_at TEXT,
                      is_active INTEGER DEFAULT 1)''')

        # --- Referrals ---
        c.execute('''CREATE TABLE IF NOT EXISTS referrals
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      referrer_id INTEGER,
                      referred_id INTEGER UNIQUE,
                      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                      is_valid INTEGER DEFAULT 1)''')

        c.execute('''CREATE TABLE IF NOT EXISTS referral_rewards
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      reward_type TEXT DEFAULT 'slot',
                      reward_value INTEGER DEFAULT 1,
                      granted_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

        # --- ZIP file selection state ---
        c.execute('''CREATE TABLE IF NOT EXISTS zip_pending_selection
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      zip_name TEXT,
                      extracted_path TEXT,
                      files_json TEXT,
                      created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

        # --- Settings ---
        c.execute('''CREATE TABLE IF NOT EXISTS bot_settings
                     (key TEXT PRIMARY KEY, value TEXT)''')

        # Insert defaults
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (owner_id,))
        if admin_id != owner_id:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
        c.execute('INSERT OR IGNORE INTO maintenance_mode (id, enabled) VALUES (1, 0)')

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully with all tables.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)


# ==================== ACTIVE USERS ====================

def add_active_user(user_id):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO active_users (user_id, joined_at) VALUES (?, ?)',
                      (user_id, datetime.now().isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding active user {user_id}: {e}")


def get_all_active_users():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT user_id FROM active_users')
        users = {row[0] for row in c.fetchall()}
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return set()


def get_total_user_count():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM active_users')
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error counting users: {e}")
        return 0


# ==================== USER FILES ====================

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, uploaded_at) VALUES (?, ?, ?, ?)',
                      (user_id, file_name, file_type, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            logger.info(f"Saved file '{file_name}' ({file_type}) for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving file for {user_id}: {e}")


def remove_user_file(user_id, file_name):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            conn.close()
            logger.info(f"Removed file '{file_name}' for user {user_id}")
        except Exception as e:
            logger.error(f"Error removing file for {user_id}: {e}")


def get_user_files(user_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT file_name, file_type FROM user_files WHERE user_id = ?', (user_id,))
        files = c.fetchall()
        conn.close()
        return files
    except Exception as e:
        logger.error(f"Error getting files for {user_id}: {e}")
        return []


def get_user_file_count(user_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM user_files WHERE user_id = ?', (user_id,))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error counting files for {user_id}: {e}")
        return 0


def get_all_user_files():
    """Returns dict of {user_id: [(file_name, file_type), ...]}."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        result = {}
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in result:
                result[user_id] = []
            result[user_id].append((file_name, file_type))
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error getting all user files: {e}")
        return {}


def get_total_file_count():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM user_files')
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error counting total files: {e}")
        return 0


# ==================== SUBSCRIPTIONS ====================

def save_subscription(user_id, expiry):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)',
                      (user_id, expiry.isoformat()))
            conn.commit()
            conn.close()
            logger.info(f"Saved subscription for {user_id}, expiry {expiry}")
        except Exception as e:
            logger.error(f"Error saving subscription for {user_id}: {e}")


def remove_subscription(user_id):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            logger.info(f"Removed subscription for {user_id}")
        except Exception as e:
            logger.error(f"Error removing subscription for {user_id}: {e}")


def get_subscription(user_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT expiry FROM subscriptions WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return datetime.fromisoformat(row[0])
        return None
    except Exception as e:
        logger.error(f"Error getting subscription for {user_id}: {e}")
        return None


def get_all_subscriptions():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        subs = {}
        for user_id, expiry in c.fetchall():
            try:
                subs[user_id] = datetime.fromisoformat(expiry)
            except ValueError:
                pass
        conn.close()
        return subs
    except Exception as e:
        logger.error(f"Error getting all subscriptions: {e}")
        return {}


# ==================== ADMINS ====================

def add_admin(admin_id):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            conn.close()
            logger.info(f"Added admin {admin_id}")
        except Exception as e:
            logger.error(f"Error adding admin {admin_id}: {e}")


def remove_admin(admin_id, owner_id):
    if admin_id == owner_id:
        return False
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            removed = c.rowcount > 0
            conn.commit()
            conn.close()
            if removed:
                logger.info(f"Removed admin {admin_id}")
            return removed
        except Exception as e:
            logger.error(f"Error removing admin {admin_id}: {e}")
            return False


def get_all_admins():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT user_id FROM admins')
        admins = {row[0] for row in c.fetchall()}
        conn.close()
        return admins
    except Exception as e:
        logger.error(f"Error getting admins: {e}")
        return set()


# ==================== PENDING APPROVALS ====================

def add_pending_approval(user_id, file_name, file_type):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO pending_approvals (user_id, file_name, file_type, submitted_at, status)
                         VALUES (?, ?, ?, ?, 'pending')''',
                      (user_id, file_name, file_type, datetime.now().isoformat()))
            approval_id = c.lastrowid
            conn.commit()
            conn.close()
            logger.info(f"Added pending approval #{approval_id} for {file_name} by user {user_id}")
            return approval_id
        except Exception as e:
            logger.error(f"Error adding pending approval: {e}")
            return None


def approve_file(approval_id, admin_id):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''UPDATE pending_approvals SET status='approved', reviewed_by=?, reviewed_at=?
                         WHERE id=? AND status='pending' ''',
                      (admin_id, datetime.now().isoformat(), approval_id))
            updated = c.rowcount > 0
            conn.commit()
            if updated:
                c.execute('SELECT user_id, file_name, file_type FROM pending_approvals WHERE id=?', (approval_id,))
                row = c.fetchone()
                conn.close()
                if row:
                    return {'user_id': row[0], 'file_name': row[1], 'file_type': row[2]}
            conn.close()
            return None
        except Exception as e:
            logger.error(f"Error approving file #{approval_id}: {e}")
            return None


def reject_file(approval_id, admin_id, reason="No reason provided"):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''UPDATE pending_approvals SET status='rejected', reviewed_by=?, reviewed_at=?, reject_reason=?
                         WHERE id=? AND status='pending' ''',
                      (admin_id, datetime.now().isoformat(), reason, approval_id))
            updated = c.rowcount > 0
            conn.commit()
            if updated:
                c.execute('SELECT user_id, file_name, file_type FROM pending_approvals WHERE id=?', (approval_id,))
                row = c.fetchone()
                conn.close()
                if row:
                    return {'user_id': row[0], 'file_name': row[1], 'file_type': row[2]}
            conn.close()
            return None
        except Exception as e:
            logger.error(f"Error rejecting file #{approval_id}: {e}")
            return None


def get_pending_approvals():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''SELECT id, user_id, file_name, file_type, submitted_at
                     FROM pending_approvals WHERE status='pending' ORDER BY submitted_at ASC''')
        rows = c.fetchall()
        conn.close()
        return [{'id': r[0], 'user_id': r[1], 'file_name': r[2], 'file_type': r[3], 'submitted_at': r[4]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting pending approvals: {e}")
        return []


def get_pending_count():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM pending_approvals WHERE status='pending'")
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error counting pending: {e}")
        return 0


# ==================== BANNED USERS ====================

def ban_user(user_id, banned_by, reason="No reason"):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO banned_users (user_id, banned_by, reason, banned_at) VALUES (?, ?, ?, ?)',
                      (user_id, banned_by, reason, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            logger.warning(f"User {user_id} banned by {banned_by}. Reason: {reason}")
            return True
        except Exception as e:
            logger.error(f"Error banning user {user_id}: {e}")
            return False


def unban_user(user_id):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
            removed = c.rowcount > 0
            conn.commit()
            conn.close()
            if removed:
                logger.info(f"User {user_id} unbanned")
            return removed
        except Exception as e:
            logger.error(f"Error unbanning user {user_id}: {e}")
            return False


def is_banned(user_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT 1 FROM banned_users WHERE user_id = ?', (user_id,))
        result = c.fetchone() is not None
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error checking ban for {user_id}: {e}")
        return False


def get_banned_users():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT user_id, reason, banned_at FROM banned_users ORDER BY banned_at DESC')
        rows = c.fetchall()
        conn.close()
        return [{'user_id': r[0], 'reason': r[1], 'banned_at': r[2]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting banned users: {e}")
        return []


# ==================== FILE VERSIONS ====================

def save_file_version(user_id, file_name, version, backup_path):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO file_versions (user_id, file_name, version, backup_path, created_at)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, file_name, version, backup_path, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            logger.info(f"Saved version {version} of '{file_name}' for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving file version: {e}")


def get_file_versions(user_id, file_name):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''SELECT id, version, backup_path, created_at FROM file_versions
                     WHERE user_id=? AND file_name=? ORDER BY version DESC''',
                  (user_id, file_name))
        rows = c.fetchall()
        conn.close()
        return [{'id': r[0], 'version': r[1], 'backup_path': r[2], 'created_at': r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting file versions: {e}")
        return []


def get_latest_version_number(user_id, file_name):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT MAX(version) FROM file_versions WHERE user_id=? AND file_name=?',
                  (user_id, file_name))
        row = c.fetchone()
        conn.close()
        return row[0] if row and row[0] else 0
    except Exception as e:
        logger.error(f"Error getting latest version: {e}")
        return 0


def delete_old_versions(user_id, file_name, keep=3):
    """Delete versions older than the latest `keep` versions."""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''SELECT id, backup_path FROM file_versions
                         WHERE user_id=? AND file_name=?
                         ORDER BY version DESC''',
                      (user_id, file_name))
            rows = c.fetchall()
            if len(rows) > keep:
                old_rows = rows[keep:]
                for row in old_rows:
                    c.execute('DELETE FROM file_versions WHERE id=?', (row[0],))
                    # Return paths so caller can delete files
                conn.commit()
                conn.close()
                return [r[1] for r in old_rows]
            conn.close()
            return []
        except Exception as e:
            logger.error(f"Error deleting old versions: {e}")
            return []


# ==================== AUTO-RESTART CONFIG ====================

def set_auto_restart(user_id, file_name, enabled=True, max_retries=5):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO auto_restart_config
                         (user_id, file_name, enabled, max_retries, restart_count, last_restart)
                         VALUES (?, ?, ?, ?, 0, NULL)''',
                      (user_id, file_name, 1 if enabled else 0, max_retries))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error setting auto-restart: {e}")


def get_auto_restart(user_id, file_name):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT enabled, max_retries, restart_count FROM auto_restart_config WHERE user_id=? AND file_name=?',
                  (user_id, file_name))
        row = c.fetchone()
        conn.close()
        if row:
            return {'enabled': bool(row[0]), 'max_retries': row[1], 'restart_count': row[2]}
        return {'enabled': True, 'max_retries': 5, 'restart_count': 0}
    except Exception as e:
        logger.error(f"Error getting auto-restart config: {e}")
        return {'enabled': True, 'max_retries': 5, 'restart_count': 0}


def increment_restart_count(user_id, file_name):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''UPDATE auto_restart_config SET restart_count = restart_count + 1, last_restart = ?
                         WHERE user_id=? AND file_name=?''',
                      (datetime.now().isoformat(), user_id, file_name))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error incrementing restart count: {e}")


def reset_restart_count(user_id, file_name):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('UPDATE auto_restart_config SET restart_count = 0 WHERE user_id=? AND file_name=?',
                      (user_id, file_name))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error resetting restart count: {e}")


# ==================== MAINTENANCE MODE ====================

def set_maintenance(enabled, message=None, ends_at=None):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            if message:
                c.execute('UPDATE maintenance_mode SET enabled=?, message=?, ends_at=? WHERE id=1',
                          (1 if enabled else 0, message, ends_at))
            else:
                c.execute('UPDATE maintenance_mode SET enabled=?, ends_at=? WHERE id=1',
                          (1 if enabled else 0, ends_at))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error setting maintenance mode: {e}")


def get_maintenance_status():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT enabled, message, ends_at FROM maintenance_mode WHERE id=1')
        row = c.fetchone()
        conn.close()
        if row:
            return {'enabled': bool(row[0]), 'message': row[1], 'ends_at': row[2]}
        return {'enabled': False, 'message': '', 'ends_at': None}
    except Exception as e:
        logger.error(f"Error getting maintenance status: {e}")
        return {'enabled': False, 'message': '', 'ends_at': None}


# ==================== RESOURCE LOGS ====================

def log_resource_usage(user_id, file_name, cpu_percent, memory_mb):
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO resource_logs (user_id, file_name, cpu_percent, memory_mb, logged_at)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, file_name, cpu_percent, memory_mb, datetime.now().isoformat()))
            # Keep only last 100 entries per script
            c.execute('''DELETE FROM resource_logs WHERE id NOT IN
                         (SELECT id FROM resource_logs WHERE user_id=? AND file_name=?
                          ORDER BY logged_at DESC LIMIT 100)
                         AND user_id=? AND file_name=?''',
                      (user_id, file_name, user_id, file_name))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging resource usage: {e}")


def get_latest_resource_usage(user_id, file_name):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''SELECT cpu_percent, memory_mb, logged_at FROM resource_logs
                     WHERE user_id=? AND file_name=? ORDER BY logged_at DESC LIMIT 1''',
                  (user_id, file_name))
        row = c.fetchone()
        conn.close()
        if row:
            return {'cpu': row[0], 'memory_mb': row[1], 'logged_at': row[2]}
        return None
    except Exception as e:
        logger.error(f"Error getting resource usage: {e}")
        return None


# ==================== ENVIRONMENT VARIABLES ====================

def get_script_env(user_id, file_name):
    """Get all environment variables for a specific script."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT env_key, env_value FROM script_env_vars WHERE user_id=? AND file_name=?', 
                  (user_id, file_name))
        rows = c.fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception as e:
        logger.error(f"Error getting script env vars: {e}")
        return {}

def set_script_env(user_id, file_name, env_key, env_value):
    """Set or update an environment variable for a script."""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO script_env_vars 
                         (user_id, file_name, env_key, env_value)
                         VALUES (?, ?, ?, ?)''',
                      (user_id, file_name, env_key, env_value))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error setting script env var: {e}")
            return False

def delete_script_env(user_id, file_name, env_key):
    """Delete an environment variable from a script."""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('DELETE FROM script_env_vars WHERE user_id=? AND file_name=? AND env_key=?',
                      (user_id, file_name, env_key))
            removed = c.rowcount > 0
            conn.commit()
            conn.close()
            return removed
        except Exception as e:
            logger.error(f"Error deleting script env var: {e}")
            return False


# ==================== FREE TRIAL ====================

def activate_trial(user_id, trial_days=18):
    """Activate a free trial for a user. Returns True if newly activated."""
    from datetime import timedelta
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('SELECT user_id FROM user_trials WHERE user_id=?', (user_id,))
            if c.fetchone():
                conn.close()
                return False  # Already had a trial
            started = datetime.now()
            expires = started + timedelta(days=trial_days)
            c.execute('''INSERT INTO user_trials (user_id, started_at, expires_at, is_active)
                         VALUES (?, ?, ?, 1)''',
                      (user_id, started.isoformat(), expires.isoformat()))
            conn.commit()
            conn.close()
            logger.info(f"Activated {trial_days}-day trial for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error activating trial for {user_id}: {e}")
            return False


def get_trial(user_id):
    """Get trial info for user. Returns dict or None."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT started_at, expires_at, is_active FROM user_trials WHERE user_id=?', (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {'started_at': row[0], 'expires_at': row[1], 'is_active': bool(row[2])}
        return None
    except Exception as e:
        logger.error(f"Error getting trial for {user_id}: {e}")
        return None


def is_trial_active(user_id):
    """Check if user has an active (non-expired) trial."""
    trial = get_trial(user_id)
    if not trial or not trial['is_active']:
        return False
    try:
        expires = datetime.fromisoformat(trial['expires_at'])
        if datetime.now() > expires:
            # Expire it
            expire_trial(user_id)
            return False
        return True
    except Exception:
        return False


def expire_trial(user_id):
    """Mark a trial as expired/inactive."""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('UPDATE user_trials SET is_active=0 WHERE user_id=?', (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error expiring trial for {user_id}: {e}")


def get_all_active_trials():
    """Get all users with active trials."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT user_id, expires_at FROM user_trials WHERE is_active=1')
        rows = c.fetchall()
        conn.close()
        return [{'user_id': r[0], 'expires_at': r[1]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting active trials: {e}")
        return []


# ==================== REFERRAL SYSTEM ====================

def add_referral(referrer_id, referred_id):
    """Record a referral. Returns True if new."""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            # Don't allow self-referral
            if referrer_id == referred_id:
                conn.close()
                return False
            # Check if referred_id was already referred by someone
            c.execute('SELECT id FROM referrals WHERE referred_id=?', (referred_id,))
            if c.fetchone():
                conn.close()
                return False
            c.execute('''INSERT INTO referrals (referrer_id, referred_id, created_at, is_valid)
                         VALUES (?, ?, ?, 1)''',
                      (referrer_id, referred_id, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            logger.info(f"Referral: {referrer_id} referred {referred_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding referral: {e}")
            return False


def get_referral_count(user_id):
    """Get total valid referrals made by user."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND is_valid=1', (user_id,))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error getting referral count for {user_id}: {e}")
        return 0


def get_referral_rewards_count(user_id):
    """Get total rewards claimed by user."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT COALESCE(SUM(reward_value), 0) FROM referral_rewards WHERE user_id=?', (user_id,))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error getting referral rewards for {user_id}: {e}")
        return 0


def grant_referral_reward(user_id, reward_type='slot', reward_value=1):
    """Grant a referral reward to a user."""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO referral_rewards (user_id, reward_type, reward_value, granted_at)
                         VALUES (?, ?, ?, ?)''',
                      (user_id, reward_type, reward_value, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            logger.info(f"Granted referral reward ({reward_type}={reward_value}) to user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error granting referral reward: {e}")
            return False


def get_referral_extra_slots(user_id):
    """Get extra file slots earned from referrals."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''SELECT COALESCE(SUM(reward_value), 0) FROM referral_rewards
                     WHERE user_id=? AND reward_type='slot' ''', (user_id,))
        slots = c.fetchone()[0]
        conn.close()
        return slots
    except Exception as e:
        logger.error(f"Error getting extra slots for {user_id}: {e}")
        return 0


def get_referral_leaderboard(limit=10):
    """Get top referrers."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''SELECT referrer_id, COUNT(*) as ref_count FROM referrals
                     WHERE is_valid=1 GROUP BY referrer_id ORDER BY ref_count DESC LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        return [{'user_id': r[0], 'referral_count': r[1]} for r in rows]
    except Exception as e:
        logger.error(f"Error getting referral leaderboard: {e}")
        return []


def get_referrer_of(user_id):
    """Get the referrer of a given user."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT referrer_id FROM referrals WHERE referred_id=?', (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error getting referrer of {user_id}: {e}")
        return None


# ==================== ZIP PENDING SELECTION ====================

def save_zip_selection(user_id, zip_name, extracted_path, files_list):
    """Store a pending ZIP selection state."""
    import json
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            # Remove old pending for this user
            c.execute('DELETE FROM zip_pending_selection WHERE user_id=?', (user_id,))
            c.execute('''INSERT INTO zip_pending_selection (user_id, zip_name, extracted_path, files_json, created_at)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, zip_name, extracted_path, json.dumps(files_list), datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving zip selection state: {e}")
            return False


def get_zip_selection(user_id):
    """Get pending ZIP selection state for user."""
    import json
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT zip_name, extracted_path, files_json FROM zip_pending_selection WHERE user_id=?', (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {'zip_name': row[0], 'extracted_path': row[1], 'files': json.loads(row[2])}
        return None
    except Exception as e:
        logger.error(f"Error getting zip selection state: {e}")
        return None


def clear_zip_selection(user_id):
    """Clear pending ZIP selection state for user."""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('DELETE FROM zip_pending_selection WHERE user_id=?', (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error clearing zip selection: {e}")


# ==================== BOT SETTINGS ====================

def get_setting(key, default=None):
    """Get a bot setting by key."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT value FROM bot_settings WHERE key=?', (key,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return default


def set_setting(key, value):
    """Set a bot setting."""
    with DB_LOCK:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)', (key, str(value)))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error setting {key}: {e}")
            return False
