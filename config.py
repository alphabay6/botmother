"""
Configuration module — loads all settings from .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram Bot ---
BOT_TOKEN = os.getenv('BOT_TOKEN', '8707743560:AAGbTjapAVotUP32laLxKSOrIAn2FLyWtb4')
OWNER_ID = int(os.getenv('OWNER_ID', '5983253591'))
ADMIN_ID = int(os.getenv('ADMIN_ID', '5983253591'))
YOUR_USERNAME = os.getenv('YOUR_USERNAME', '@aaka8h')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', '5983253591')

# --- Force Join Channels/Groups ---
# Comma-separated list of channel/group usernames or IDs, e.g. "@mychannel,@mygroup,-100123456789"
_force_join_raw = os.getenv('FORCE_JOIN_CHANNELS', '')
FORCE_JOIN_CHANNELS = [c.strip() for c in _force_join_raw.split(',') if c.strip()] if _force_join_raw else []

# --- Directories ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
PENDING_DIR = os.path.join(BASE_DIR, 'pending_files')
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATABASE_PATH = os.path.join(DATA_DIR, 'bot_data.db')
VERSIONS_DIR = os.path.join(BASE_DIR, 'file_versions')

# --- User Limits ---
FREE_USER_LIMIT = int(os.getenv('FREE_USER_LIMIT', '0'))           # 0 = no free hosting
FREE_TRIAL_LIMIT = int(os.getenv('FREE_TRIAL_LIMIT', '1'))         # 1 file during free trial
SUBSCRIBED_USER_LIMIT = int(os.getenv('SUBSCRIBED_USER_LIMIT', '15'))
ADMIN_LIMIT = int(os.getenv('ADMIN_LIMIT', '999'))
OWNER_LIMIT = float('inf')

# --- Free Trial ---
FREE_TRIAL_DAYS = int(os.getenv('FREE_TRIAL_DAYS', '18'))

# --- Referral System ---
REFERRALS_PER_REWARD = int(os.getenv('REFERRALS_PER_REWARD', '5'))  # 5 referrals = 1 extra slot
REFERRAL_REWARD_SLOTS = int(os.getenv('REFERRAL_REWARD_SLOTS', '1'))  # extra file slots per reward

# --- Flask ---
# On Waifly: your subdomain bot.waifly.com maps to port 25584
# Waifly may also auto-set the PORT environment variable
FLASK_PORT = int(os.getenv('FLASK_PORT', '25584'))

# --- Web Admin Panel ---
WEB_ADMIN_PASSWORD = os.getenv('WEB_ADMIN_PASSWORD', 'admin123')
WEB_SESSION_SECRET = os.getenv('WEB_SESSION_SECRET', 'change_this_secret_key_in_production')

# --- Monitoring ---
WATCHDOG_INTERVAL = int(os.getenv('WATCHDOG_INTERVAL', '30'))
MAX_RESTART_ATTEMPTS = int(os.getenv('MAX_RESTART_ATTEMPTS', '5'))
MEMORY_ALERT_THRESHOLD = int(os.getenv('MEMORY_ALERT_THRESHOLD', '80'))

# --- File Constraints ---
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXTENSIONS = ['.py', '.js', '.zip']
MAX_VERSIONS_KEPT = 3

# --- Trial Resource Limits ---
TRIAL_MAX_MEMORY_MB = int(os.getenv('TRIAL_MAX_MEMORY_MB', '50'))   # 50 MB RAM cap for trial users
TRIAL_MAX_CPU_PERCENT = float(os.getenv('TRIAL_MAX_CPU_PERCENT', '5.0'))  # 5% CPU cap for trial users

# --- Create directories ---
for d in [UPLOAD_BOTS_DIR, PENDING_DIR, DATA_DIR, VERSIONS_DIR]:
    os.makedirs(d, exist_ok=True)
