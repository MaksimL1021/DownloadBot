import asyncio
import os
import yt_dlp
import tempfile
import logging
import time
import re
from typing import Optional, Dict
from config import Config

logger = logging.getLogger(__name__)


class MediaDownloader:
    def __init__(self):
        self.downloads_dir = Config.DOWNLOADS_DIR

        self.base_ydl_opts = {
            'format': 'worst[ext=mp4][filesize<50M]/worst[filesize<50M]/worst[ext=mp4]/worst',
            'outtmpl': os.path.join(self.downloads_dir, 'video_%(timestamp)s_%(title).50s.%(ext)s'),
            'restrictfilenames': True,
            'noplaylist': True,
            'extract_flat': False,
            'writethumbnail': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': False,
            'no_warnings': True,
            'quiet': True,
            'socket_timeout': 30,
            'retries': 3,
        }
        
        self.platform_opts = {
            'instagram': {
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
                }
            },
            'tiktok': {
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
                }
            }
        }

    def detect_platform(self, url: str) -> str:
        url_lower = url.lower()
        
        for platform, info in Config.SUPPORTED_PLATFORMS.items():
            for pattern in info['patterns']:
                if pattern in url_lower:
                    return platform
        
        return 'unknown'

    def get_platform_info(self, url: str) -> Dict:
        platform = self.detect_platform(url)
        if platform in Config.SUPPORTED_PLATFORMS:
            return Config.SUPPORTED_PLATFORMS[platform]
        return {'name': '❓ Unknown', 'emoji': '🔗'}

    async def get_video_info(self, url: str) -> Optional[Dict]:
        try:
            loop = asyncio.get_event_loop()
            platform = self.detect_platform(url)

            info_opts = {
                **self.base_ydl_opts,
                'quiet': True,
                'no_warnings': True,
            }
            
            if platform in self.platform_opts:
                info_opts.update(self.platform_opts[platform])

            def _get_info():
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)
                        return {
                            'title': info.get('title', 'Unknown'),
                            'duration': info.get('duration', 0),
                            'uploader': info.get('uploader', 'Unknown'),
                            'view_count': info.get('view_count', 0),
                            'platform': platform,
                            'upload_date': info.get('upload_date', ''),
                            'thumbnail': info.get('thumbnail', ''),
                            'filesize': info.get('filesize', 0),
                            'formats': len(info.get('formats', [])),
                        }
                    except Exception as e:
                        logger.error(f"Ошибка получения информации: {e}")
                        return None

            return await loop.run_in_executor(None, _get_info)

        except Exception as e:
            logger.error(f"Ошибка при получении информации о видео: {e}")
            return None

    async def download_video(self, url: str) -> Optional[str]:
        try:
            loop = asyncio.get_event_loop()
            platform = self.detect_platform(url)

            def _download():
                output_path = None
                timestamp = str(int(time.time()))

                download_opts = {
                    **self.base_ydl_opts,
                    'outtmpl': os.path.join(self.downloads_dir, f'video_{timestamp}_%(title).50s.%(ext)s'),
                }
                
                if platform in self.platform_opts:
                    download_opts.update(self.platform_opts[platform])

                with yt_dlp.YoutubeDL(download_opts) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)

                        filesize = info.get('filesize') or info.get('filesize_approx', 0)
                        if filesize and filesize > Config.TELEGRAM_MAX_FILE_SIZE:
                            logger.warning(f"Файл слишком большой: {filesize} байт")
                            return None

                        ydl.download([url])

                        for file in os.listdir(self.downloads_dir):
                            if file.startswith(f'video_{timestamp}_') and any(file.endswith(ext) for ext in ['.mp4', '.webm', '.mkv', '.avi', '.mov']):
                                output_path = os.path.join(self.downloads_dir, file)
                                break

                        if output_path and os.path.exists(output_path):
                            actual_size = os.path.getsize(output_path)
                            if actual_size > Config.TELEGRAM_MAX_FILE_SIZE:
                                os.remove(output_path)
                                logger.warning(f"Скачанный файл слишком большой: {actual_size} байт")
                                return None

                            logger.info(f"Видео успешно скачано: {output_path}")
                            return output_path
                        else:
                            logger.error("Не удалось найти скачанный файл")
                            return None

                    except yt_dlp.DownloadError as e:
                        logger.error(f"Ошибка загрузки yt-dlp: {e}")
                        return None
                    except Exception as e:
                        logger.error(f"Неожиданная ошибка при загрузке: {e}")
                        return None

            return await asyncio.wait_for(
                loop.run_in_executor(None, _download),
                timeout=Config.DOWNLOAD_TIMEOUT
            )

        except asyncio.TimeoutError:
            logger.error("Тайм-аут загрузки видео")
            return None
        except Exception as e:
            logger.error(f"Ошибка при загрузке видео: {e}")
            return None

    def cleanup_old_files(self, max_age_hours: int = 1):
        try:
            import time

            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            for filename in os.listdir(self.downloads_dir):
                file_path = os.path.join(self.downloads_dir, filename)

                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getctime(file_path)

                    if file_age > max_age_seconds:
                        try:
                            os.remove(file_path)
                            logger.info(f"Удален старый файл: {filename}")
                        except Exception as e:
                            logger.error(f"Ошибка удаления файла {filename}: {e}")

        except Exception as e:
            logger.error(f"Ошибка очистки файлов: {e}")

    async def cleanup_old_files_async(self, max_age_hours: int = 1):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.cleanup_old_files, max_age_hours)

    @staticmethod
    def is_supported_url(url: str) -> bool:
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                ydl.extract_info(url, download=False)
                return True
        except:
            return False