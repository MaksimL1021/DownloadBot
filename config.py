import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', 500))
    DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', 10000))

    TELEGRAM_MAX_FILE_SIZE = 500 * 1024 * 1024
    
    MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', 10000))
    CLEANUP_INTERVAL_HOURS = float(os.getenv('CLEANUP_INTERVAL_HOURS', 1))
    MAX_FILE_AGE_HOURS = float(os.getenv('MAX_FILE_AGE_HOURS', 24))
    
    DOWNLOADS_DIR = 'downloads'
    
    TIKTOK_COOKIES_FILE = os.getenv('TIKTOK_COOKIES_FILE', 'tiktok_cookies.txt')

    SUPPORTED_PLATFORMS = {
        'youtube': {
            'name': '🔴 YouTube',
            'patterns': ['youtube.com', 'youtu.be', 'youtube.com/shorts'],
            'emoji': '📺',
            'supports_photos': False
        },
        'instagram': {
            'name': '📸 Instagram',
            'patterns': ['instagram.com', 'instagr.am'],
            'emoji': '📱',
            'supports_photos': True
        },
        'tiktok': {
            'name': '🎵 TikTok',
            'patterns': ['tiktok.com', 'www.tiktok.com', 'vm.tiktok.com'],
            'emoji': '🎭',
            'supports_photos': True
        }
    }
    
    STATUS_EMOJIS = {
        'processing': '⏳',
        'downloading': '📥',
        'uploading': '📤',
        'success': '✅',
        'error': '❌',
        'warning': '⚠️'
    }

    @staticmethod
    def validate():
        if not Config.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не установлен. Создайте .env файл по образцу .env.example")

        if not os.path.exists(Config.DOWNLOADS_DIR):
            os.makedirs(Config.DOWNLOADS_DIR)