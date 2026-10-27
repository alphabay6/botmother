"""
Helper utilities — uptime, formatting, user status, etc.
"""
from datetime import datetime
import psutil
import os

BOT_START_TIME = datetime.now()


def get_uptime():
    """Get formatted bot uptime string."""
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"


def get_user_status(user_id, owner_id, admin_ids, subscriptions):
    """Determine user status and subscription info."""
    import database as db
    if user_id == owner_id:
        return "👑 Owner", ""
    elif user_id in admin_ids:
        return "🛡️ Admin", ""
    elif user_id in subscriptions:
        expiry = subscriptions[user_id]
        if expiry > datetime.now():
            days_left = (expiry - datetime.now()).days
            return "⭐ Premium", f"\n📅 Subscription expires in: {days_left} days"
        else:
            return "Free User (Expired)", ""
    else:
        # Check trial
        trial = db.get_trial(user_id)
        if trial and trial['is_active']:
            try:
                expires = datetime.fromisoformat(trial['expires_at'])
                if expires > datetime.now():
                    days_left = (expires - datetime.now()).days
                    return "🆓 Free Trial", f"\n⏳ Trial expires in: {days_left} days"
            except Exception:
                pass
        return "👤 Free User", ""


def get_file_limit(user_id, owner_id, admin_ids, subscriptions, limits):
    """Get user's file upload limit, including referral bonus slots and trial."""
    import database as db
    from config import FREE_TRIAL_LIMIT
    if user_id == owner_id:
        return float('inf')
    if user_id in admin_ids:
        return limits['admin']
    if user_id in subscriptions and subscriptions[user_id] > datetime.now():
        base = limits['subscribed']
        extra = db.get_referral_extra_slots(user_id)
        return base + extra
    # Check trial
    if db.is_trial_active(user_id):
        extra = db.get_referral_extra_slots(user_id)
        return FREE_TRIAL_LIMIT + extra
    # Regular free user — get bonus from referrals only
    extra = db.get_referral_extra_slots(user_id)
    return limits.get('free', 0) + extra


def format_limit(limit):
    """Format file limit for display."""
    return str(limit) if limit != float('inf') else "Unlimited"


def get_system_stats():
    """Get system resource statistics."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    return {
        'cpu_percent': cpu_percent,
        'memory_total_gb': round(memory.total / (1024**3), 2),
        'memory_used_gb': round(memory.used / (1024**3), 2),
        'memory_percent': memory.percent,
        'disk_total_gb': round(disk.total / (1024**3), 2),
        'disk_used_gb': round(disk.used / (1024**3), 2),
        'disk_percent': round(disk.percent, 1),
    }


def format_bytes(bytes_val):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"


def sanitize_filename(filename):
    """Remove potentially dangerous characters from filename."""
    # Keep only alphanumeric, dots, underscores, hyphens
    import re
    name = re.sub(r'[^\w.\-]', '_', filename)
    # Remove leading dots (hidden files)
    name = name.lstrip('.')
    return name if name else 'unnamed_file'
