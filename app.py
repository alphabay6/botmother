"""
Telegram Bot Hosting Platform — Main Entry Point
=================================================
A production-grade Telegram bot that hosts and runs Python/JS scripts.
Features: Admin file approval, auto-restart, resource monitoring, ban system,
maintenance mode, file versioning, broadcast, subscriptions, referral system,
free trials, force-join, and web admin dashboard.
"""
import os
import sys
import time
import logging
import atexit
import hashlib
import secrets
import json

import telebot
from flask import Flask, request, jsonify, send_from_directory
from threading import Thread
from datetime import datetime

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('HostingBot')

# --- Load Configuration ---
from config import (
    BOT_TOKEN, OWNER_ID, ADMIN_ID, FLASK_PORT,
    WEB_ADMIN_PASSWORD, WEB_SESSION_SECRET
)

# --- Initialize Bot ---
bot = telebot.TeleBot(BOT_TOKEN)

# --- Initialize Database ---
import database as db
db.init_db(OWNER_ID, ADMIN_ID)

# --- Load Runtime State ---
admin_ids = db.get_all_admins()
admin_ids.add(OWNER_ID)
if ADMIN_ID:
    admin_ids.add(ADMIN_ID)

# Load subscriptions into memory cache
subscriptions = db.get_all_subscriptions()

# Bot locked state — using list for mutability in closures
bot_locked = [False]

# Simple in-memory session store
_web_sessions = {}


# --- Flask App ---
flask_app = Flask('HostingBot')

WEB_DIR = os.path.join(os.path.dirname(__file__), 'web')


def _hash_password(password):
    return hashlib.sha256((password + WEB_SESSION_SECRET).encode()).hexdigest()


def _check_web_token(req):
    token = req.headers.get('X-Admin-Token') or req.args.get('token')
    return token and _web_sessions.get(token) is not None


# ==================== WEB STATIC FILES ====================

@flask_app.route('/')
def web_index():
    if os.path.exists(os.path.join(WEB_DIR, 'index.html')):
        return send_from_directory(WEB_DIR, 'index.html')
    return "Bot is running"


@flask_app.route('/dashboard')
def web_dashboard():
    if os.path.exists(os.path.join(WEB_DIR, 'dashboard.html')):
        return send_from_directory(WEB_DIR, 'dashboard.html')
    return "Dashboard not found", 404


@flask_app.route('/static/<path:filename>')
def web_static(filename):
    return send_from_directory(os.path.join(WEB_DIR, 'static'), filename)


# ==================== WEB AUTH API ====================

@flask_app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')
    if password == WEB_ADMIN_PASSWORD:
        token = secrets.token_hex(32)
        _web_sessions[token] = {'created': time.time()}
        return jsonify({'success': True, 'token': token})
    return jsonify({'success': False, 'error': 'Invalid password'}), 401


@flask_app.route('/api/logout', methods=['POST'])
def api_logout():
    token = request.headers.get('X-Admin-Token')
    if token and token in _web_sessions:
        del _web_sessions[token]
    return jsonify({'success': True})


# ==================== WEB STATS API ====================

@flask_app.route('/api/stats')
def api_stats():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    from services.script_runner import get_running_count, get_all_running
    from utils.helpers import get_system_stats, get_uptime
    stats = get_system_stats()
    running = get_all_running()
    trials = db.get_all_active_trials()
    return jsonify({
        'total_users': db.get_total_user_count(),
        'total_files': db.get_total_file_count(),
        'running_scripts': get_running_count(),
        'pending_approvals': db.get_pending_count(),
        'banned_users': len(db.get_banned_users()),
        'active_trials': len(trials),
        'bot_locked': bot_locked[0],
        'maintenance': db.get_maintenance_status(),
        'uptime': get_uptime(),
        'system': stats,
        'running_list': running[:20],
    })


@flask_app.route('/health')
def health():
    from services.script_runner import get_running_count
    return jsonify({
        'status': 'ok',
        'running_scripts': get_running_count(),
        'users': db.get_total_user_count(),
    })


# ==================== USERS API ====================

@flask_app.route('/api/users')
def api_users():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    all_users = list(db.get_all_active_users())
    subs = db.get_all_subscriptions()
    result = []
    for uid in all_users[:200]:
        trial = db.get_trial(uid)
        ref_count = db.get_referral_count(uid)
        extra_slots = db.get_referral_extra_slots(uid)
        is_sub = uid in subs and subs[uid] > datetime.now()
        is_banned = db.is_banned(uid)
        result.append({
            'user_id': uid,
            'is_admin': uid in admin_ids,
            'is_subscribed': is_sub,
            'subscription_expiry': subs[uid].isoformat() if is_sub else None,
            'trial_active': trial['is_active'] if trial else False,
            'trial_expires': trial['expires_at'] if trial else None,
            'referral_count': ref_count,
            'extra_slots': extra_slots,
            'is_banned': is_banned,
            'file_count': db.get_user_file_count(uid),
        })
    return jsonify({'users': result, 'total': len(all_users)})


@flask_app.route('/api/ban', methods=['POST'])
def api_ban():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    reason = data.get('reason', 'Banned via web panel')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    from services.script_runner import stop_all_user_scripts
    db.ban_user(int(user_id), OWNER_ID, reason)
    stopped = stop_all_user_scripts(int(user_id))
    try:
        bot.send_message(int(user_id), f"🚫 You have been **banned**.\n📝 Reason: {reason}", parse_mode='Markdown')
    except Exception:
        pass
    return jsonify({'success': True, 'stopped_scripts': stopped})


@flask_app.route('/api/unban', methods=['POST'])
def api_unban():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    removed = db.unban_user(int(user_id))
    if removed:
        try:
            bot.send_message(int(user_id), "✅ You have been **unbanned**. Welcome back!", parse_mode='Markdown')
        except Exception:
            pass
    return jsonify({'success': removed})


# ==================== SUBSCRIPTIONS API ====================

@flask_app.route('/api/subscription/add', methods=['POST'])
def api_add_subscription():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    from datetime import timedelta
    data = request.get_json(silent=True) or {}
    user_id = int(data.get('user_id', 0))
    days = int(data.get('days', 30))
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    expiry = datetime.now() + timedelta(days=days)
    db.save_subscription(user_id, expiry)
    subscriptions[user_id] = expiry
    try:
        bot.send_message(user_id, f"🎉 **Subscription Activated!**\n⭐ You now have Premium access for **{days} days**.\n📅 Expires: {expiry.strftime('%Y-%m-%d')}", parse_mode='Markdown')
    except Exception:
        pass
    return jsonify({'success': True, 'expiry': expiry.isoformat()})


# ==================== PENDING APPROVALS API ====================

@flask_app.route('/api/pending')
def api_pending():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    pending = db.get_pending_approvals()
    return jsonify({'pending': pending})


@flask_app.route('/api/approve', methods=['POST'])
def api_approve():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    approval_id = data.get('approval_id')
    if not approval_id:
        return jsonify({'error': 'approval_id required'}), 400
    from services.approval import handle_approve
    result = handle_approve(int(approval_id), OWNER_ID, bot)
    return jsonify({'success': bool(result)})


@flask_app.route('/api/reject', methods=['POST'])
def api_reject():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    approval_id = data.get('approval_id')
    reason = data.get('reason', 'Rejected via web panel')
    if not approval_id:
        return jsonify({'error': 'approval_id required'}), 400
    from services.approval import handle_reject
    result = handle_reject(int(approval_id), OWNER_ID, reason, bot)
    return jsonify({'success': bool(result)})


# ==================== BROADCAST API ====================

@flask_app.route('/api/broadcast', methods=['POST'])
def api_broadcast():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    message_text = data.get('message', '')
    if not message_text:
        return jsonify({'error': 'message required'}), 400

    users = list(db.get_all_active_users())
    sent = 0
    failed = 0
    for uid in users:
        try:
            bot.send_message(uid, message_text, parse_mode='Markdown')
            sent += 1
        except Exception:
            failed += 1
        time.sleep(0.05)  # Rate limit

    return jsonify({'success': True, 'sent': sent, 'failed': failed, 'total': len(users)})


# ==================== SETTINGS API ====================

@flask_app.route('/api/settings', methods=['POST'])
def api_settings():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    changes = {}

    if 'bot_locked' in data:
        bot_locked[0] = bool(data['bot_locked'])
        changes['bot_locked'] = bot_locked[0]

    if 'maintenance' in data:
        maint = data['maintenance']
        enabled = maint.get('enabled', False)
        msg = maint.get('message', None)
        db.set_maintenance(enabled, message=msg)
        changes['maintenance'] = enabled

    return jsonify({'success': True, 'changes': changes})


@flask_app.route('/api/referrals/leaderboard')
def api_referral_leaderboard():
    if not _check_web_token(request):
        return jsonify({'error': 'Unauthorized'}), 401
    leaders = db.get_referral_leaderboard(limit=20)
    return jsonify({'leaderboard': leaders})


def run_flask():
    # Waifly (and most PaaS) sets the PORT env variable automatically
    # The subdomain bot.waifly.com maps to whatever port is assigned
    port = int(os.environ.get("PORT", FLASK_PORT))
    logger.info(f"Starting Flask on 0.0.0.0:{port}")
    flask_app.run(
        host='0.0.0.0',
        port=port,
        use_reloader=False,
        threaded=True,       # Handle multiple requests at once
        debug=False
    )


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    port = int(os.environ.get("PORT", FLASK_PORT))
    logger.info(f"Flask web server started on port {port}.")


# --- Register All Handlers ---
from handlers import start, files, admin, subscription, callbacks, referral

start.register(bot, admin_ids, subscriptions, bot_locked)
files.register(bot, admin_ids, subscriptions, bot_locked)
admin.register(bot, admin_ids, subscriptions, bot_locked)
subscription.register(bot, admin_ids, subscriptions, bot_locked)
referral.register(bot, admin_ids, subscriptions, bot_locked)
callbacks.register(bot, admin_ids, subscriptions, bot_locked)


# --- Text Button Handler (reply keyboard) ---
BUTTON_TEXT_MAP = {
    "📢 Updates Channel": lambda m: bot.reply_to(m, f"📢 Visit our Updates Channel:", reply_markup=_updates_markup()),
    "📤 Upload File": lambda m: _dispatch_cmd(m, 'uploadfile'),
    "📂 My Files": lambda m: _dispatch_cmd(m, 'checkfiles'),
    "⚡ Bot Speed": lambda m: _dispatch_cmd(m, 'ping'),
    "📊 Statistics": lambda m: _dispatch_cmd(m, 'status'),
    "⏱ Uptime": lambda m: _dispatch_cmd(m, 'uptime'),
    "💳 Subscriptions": lambda m: _dispatch_cmd(m, 'subscriptions'),
    "📢 Broadcast": lambda m: _dispatch_cmd(m, 'broadcast'),
    "🔒 Lock Bot": lambda m: _dispatch_cmd(m, 'lockbot'),
    "🟢 Run All Scripts": lambda m: _dispatch_cmd(m, 'runall'),
    "👑 Admin Panel": lambda m: _dispatch_cmd(m, 'adminpanel'),
    "📋 Pending Files": lambda m: _dispatch_cmd(m, 'pending'),
    "📈 Dashboard": lambda m: _dispatch_cmd(m, 'dashboard'),
    "🚫 Ban Manager": lambda m: bot.reply_to(m, "🚫 **Ban Manager**\nUse `/ban`, `/unban`, `/banlist` commands.", parse_mode='Markdown'),
    "👥 My Referrals": lambda m: _dispatch_cmd(m, 'referrals'),
    "📞 Contact Owner": lambda m: bot.reply_to(m, "📞 Contact the owner:",
        reply_markup=telebot.types.InlineKeyboardMarkup().add(
            telebot.types.InlineKeyboardButton('📞 Contact', url=f'https://t.me/{_get_username()}'))),
}


def _updates_markup():
    from config import UPDATE_CHANNEL
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL))
    return markup


def _get_username():
    from config import YOUR_USERNAME
    return YOUR_USERNAME.replace('@', '')


def _dispatch_cmd(message, cmd):
    """Simulate a command dispatch."""
    message.text = f'/{cmd}'
    bot.process_new_messages([message])


@bot.message_handler(func=lambda m: m.text in BUTTON_TEXT_MAP)
def handle_reply_buttons(message):
    handler = BUTTON_TEXT_MAP.get(message.text)
    if handler:
        handler(message)


# --- Cleanup on Exit ---
def cleanup():
    from services.script_runner import cleanup_all
    cleanup_all()

atexit.register(cleanup)


# --- Start Monitor ---
from services.monitor import start_monitor
start_monitor(bot, admin_ids)


# --- Main ---
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("  HOSTING BOT — STARTING UP")
    logger.info(f"  Python: {sys.version.split()[0]}")
    logger.info(f"  Owner: {OWNER_ID}")
    logger.info(f"  Admins: {admin_ids}")
    logger.info(f"  Users: {db.get_total_user_count()}")
    logger.info(f"  Files: {db.get_total_file_count()}")
    logger.info("=" * 50)

    keep_alive()
    logger.info("Starting Telegram polling...")

    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except Exception as e:
            error_name = type(e).__name__
            if 'ReadTimeout' in error_name or 'ConnectionError' in error_name:
                logger.warning(f"Polling {error_name}. Retrying in 5s...")
                time.sleep(5)
            else:
                logger.critical(f"Polling error: {e}", exc_info=True)
                time.sleep(15)
        finally:
            logger.warning("Polling loop restarting...")
            time.sleep(1)