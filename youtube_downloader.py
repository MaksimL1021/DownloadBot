import asyncio
import os
import yt_dlp
import tempfile
import logging
import time
import re
import requests
from bs4 import BeautifulSoup
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
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1'
                },
                'geo_bypass': True,
                'sleep_interval': 2,
                'max_sleep_interval': 5
            }
        }

    def detect_platform(self, url: str) -> str:
        url_lower = url.lower()
        
        for platform, info in Config.SUPPORTED_PLATFORMS.items():
            for pattern in info['patterns']:
                if pattern in url_lower:
                    return platform
        
        return 'unknown'

    def resolve_tiktok_url(self, url: str) -> str:
        try:
            if any(domain in url.lower() for domain in ['vt.tiktok.com', 'vm.tiktok.com']):
                print(f"DEBUG: Разворачиваем сокращенную ссылку: {url}")
                response = requests.head(url, allow_redirects=True, timeout=10)
                resolved_url = response.url
                print(f"DEBUG: Развернутая ссылка: {resolved_url}")
                return resolved_url
            return url
        except Exception as e:
            print(f"DEBUG: Ошибка разворачивания ссылки: {e}")
            return url

    def is_tiktok_photo(self, url: str) -> bool:
        resolved_url = self.resolve_tiktok_url(url)
        url_lower = resolved_url.lower()
        
        print(f"DEBUG: Проверяем URL: {url_lower}")
        
        has_tiktok = 'tiktok.com' in url_lower
        has_photo = '/photo/' in url_lower
        is_photo = has_tiktok and has_photo
        
        print(f"DEBUG: has_tiktok: {has_tiktok}")
        print(f"DEBUG: has_photo: {has_photo}")  
        print(f"DEBUG: result: {is_photo}")
        
        return is_photo
    
    def get_platform_info(self, url: str) -> Dict:
        platform = self.detect_platform(url)
        if platform in Config.SUPPORTED_PLATFORMS:
            return Config.SUPPORTED_PLATFORMS[platform]
        return {'name': '❓ Unknown', 'emoji': '🔗'}
    
    async def download_tiktok_photo(self, url: str) -> Optional[str]:
        logger.info(f"download_tiktok_photo начинает работу с URL: {url}")
        try:
            loop = asyncio.get_event_loop()
            
            def _download_photo(url_param, self_param):
                logger.info("Начинаем скачивание TikTok фото через веб-скрапинг")
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    }
                    
                    resolved_url = self_param.resolve_tiktok_url(url_param)
                    print(f"DEBUG: Загружаем страницу: {resolved_url}")
                    
                    response = requests.get(resolved_url, headers=headers, timeout=30)
                    response.raise_for_status()
                    
                    print(f"DEBUG: Статус ответа: {response.status_code}")
                    print(f"DEBUG: Размер контента: {len(response.text)} символов")
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    img_selectors = [
                        'img[data-e2e="photo-item"]',
                        'img[data-e2e="slideshow-item"]', 
                        'img[alt*="photo"]',
                        'img[src*="tiktokcdn"]',
                        'img[src*="muscdn"]',
                        'img[src*="p16-sign"]',
                        'div[data-e2e="photo-item"] img',
                        'div[data-e2e="slideshow-item"] img',
                        '[data-e2e*="photo"] img',
                        'img[src*="720x"]',
                        'img[src*="1080x"]',
                        'img'
                    ]
                    
                    img_url = None
                    print(f"DEBUG: Начинаем поиск изображений...")
                    
                    for i, selector in enumerate(img_selectors):
                        images = soup.select(selector)
                        print(f"DEBUG: Селектор {i+1} '{selector}': найдено {len(images)} изображений")
                        
                        for j, img in enumerate(images):
                            src = img.get('src') or img.get('data-src') or img.get('data-original')
                            if src:
                                print(f"DEBUG: Изображение {j+1}: {src[:100]}...")
                                if any(domain in src for domain in ['tiktokcdn', 'tiktok', 'muscdn', 'p16-sign']):
                                    if any(size in src for size in ['720x', '1080x', 'large', 'medium']) or len(src) > 100:
                                        img_url = src
                                        print(f"DEBUG: Выбрано изображение: {img_url}")
                                        break
                        if img_url:
                            break
                    
                    if not img_url:
                        print("DEBUG: Поиск в script тегах...")
                        scripts = soup.find_all('script')
                        for script in scripts:
                            if script.string and 'photo' in script.string.lower():
                                script_text = script.string
                                print(f"DEBUG: Найден script с 'photo', длина: {len(script_text)}")
                                
                                try:
                                    import json
                                    import re
                                    
                                    if script_text.strip().startswith('{') and script_text.strip().endswith('}'):
                                        print("DEBUG: Парсим как чистый JSON")
                                        data = json.loads(script_text)
                                    else:
                                        json_patterns = [
                                            r'window\["SIGI_STATE"\]\s*=\s*({.+?});',
                                            r'__UNIVERSAL_DATA_FOR_REHYDRATION__\s*=\s*({.+?});',
                                            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                                            r'({.*?"__DEFAULT_SCOPE__".*?})\s*(?:;|$)',
                                            r'({.*?"photo".*?})',
                                        ]
                                        
                                        data = None
                                        for pattern in json_patterns:
                                            json_match = re.search(pattern, script_text, re.DOTALL)
                                            if json_match:
                                                json_text = json_match.group(1)
                                                print(f"DEBUG: Найден JSON паттерн, длина: {len(json_text)}")
                                                try:
                                                    data = json.loads(json_text)
                                                    print("DEBUG: JSON успешно распарсен")
                                                    break
                                                except:
                                                    print("DEBUG: Ошибка парсинга этого JSON")
                                                    continue
                                    
                                    if data:
                                        def find_image_urls(obj, path="", depth=0):
                                            if depth > 10:
                                                return []
                                            
                                            urls = []
                                            if isinstance(obj, dict):
                                                for key, value in obj.items():
                                                    current_path = f"{path}.{key}" if path else key
                                                    
                                                    if isinstance(value, str) and len(value) > 20:
                                                        if any(domain in value for domain in ['tiktokcdn', 'muscdn', 'p16-sign', 'p16-amd', 'p16-va']):
                                                            has_image_ext = any(ext in value.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp'])
                                                            has_image_keywords = 'image' in value.lower() or 'photo' in value.lower()
                                                            has_image_path = any(path in value.lower() for path in ['img/', '/image/', '/photo/', 'obj/', '/media/'])
                                                            
                                                            if has_image_ext or has_image_keywords or has_image_path or 'obj/' in value:
                                                                print(f"DEBUG: Найден кандидат URL в {current_path}: {value[:120]}...")
                                                                
                                                                priority = 0
                                                                
                                                                if '7552419203936947478' in value:
                                                                    priority += 100
                                                                    print(f"DEBUG: +100 за ID поста")
                                                                
                                                                post_related_keys = ['video', 'aweme', 'item', 'detail', 'content', 'media']
                                                                if any(k in current_path.lower() for k in post_related_keys):
                                                                    priority += 50
                                                                    print(f"DEBUG: +50 за пост-ключи")
                                                                
                                                                photo_keys = ['photo', 'image', 'cover', 'thumb']
                                                                if any(k in current_path.lower() for k in photo_keys):
                                                                    priority += 30
                                                                    print(f"DEBUG: +30 за фото-ключи")
                                                                
                                                                if has_image_ext:
                                                                    priority += 20
                                                                    print(f"DEBUG: +20 за расширение изображения")
                                                                
                                                                if 'interest' in current_path.lower() or 'category' in current_path.lower():
                                                                    priority -= 20
                                                                    print(f"DEBUG: -20 за интересы/категории")
                                                                
                                                                print(f"DEBUG: Финальный приоритет: {priority}")
                                                                
                                                                if value.startswith('http://'):
                                                                    value = value.replace('http://', 'https://')
                                                                    print(f"DEBUG: Конвертировано в HTTPS")
                                                                
                                                                urls.append((value, priority, current_path))
                                                                print(f"DEBUG: URL добавлен в список")
                                                            else:
                                                                print(f"DEBUG: URL {value[:80]} не прошел проверку критериев изображения")
                                                                print(f"  - has_image_ext: {has_image_ext}")
                                                                print(f"  - has_image_keywords: {has_image_keywords}")
                                                                print(f"  - has_image_path: {has_image_path}")
                                                                print(f"  - has obj/: {'obj/' in value}")
                                                                print(f"  - URL: {value}")
                                                        else:
                                                            if any(ext in value.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']) and 'http' in value:
                                                                print(f"DEBUG: URL {value[:80]} не прошел доменную проверку")
                                                    
                                                    if key.lower() in ['photo', 'image', 'cover', 'video', 'aweme', 'item', 'detail', 'content', 'media'] or \
                                                       'photo' in key.lower() or 'image' in key.lower() or '7552419203936947478' in str(value):
                                                        urls.extend(find_image_urls(value, current_path, depth + 1))
                                                    elif depth < 4 and 'interest' not in current_path.lower():
                                                        urls.extend(find_image_urls(value, current_path, depth + 1))
                                            elif isinstance(obj, list):
                                                for i, item in enumerate(obj[:10]):
                                                    urls.extend(find_image_urls(item, f"{path}[{i}]", depth + 1))
                                            return urls
                                        
                                        image_urls = find_image_urls(data)
                                        print(f"DEBUG: Всего найдено URL изображений: {len(image_urls)}")
                                        
                                        image_urls.sort(key=lambda x: x[1], reverse=True)
                                        
                                        best_url = None
                                        for url_data in image_urls:
                                            url, priority, path = url_data
                                            print(f"DEBUG: Кандидат URL (приоритет {priority}): {url[:80]}...")
                                            
                                            if priority > 0 and any(size in url for size in ['1080x', '720x', 'large']) and not best_url:
                                                best_url = url
                                                print(f"DEBUG: Выбран высококачественный URL с высоким приоритетом: {url}")
                                                break
                                        
                                        if not best_url and image_urls:
                                            best_url = image_urls[0][0]
                                            print(f"DEBUG: Выбран URL с самым высоким приоритетом: {best_url}")
                                        
                                        if best_url:
                                            img_url = best_url
                                            print(f"DEBUG: Финальный URL изображения: {img_url}")
                                            
                                except Exception as e:
                                    print(f"DEBUG: Ошибка парсинга JSON: {e}")
                                    import traceback
                                    traceback.print_exc()
                                
                                if img_url:
                                    break
                    
                    if not img_url:
                        logger.error("Не удалось найти URL изображения через веб-скрапинг")
                        print("DEBUG: Пробуем использовать yt-dlp как fallback...")
                        
                        try:
                            ydl_opts = {
                                'quiet': True,
                                'no_warnings': True,
                                'extractaudio': False,
                                'outtmpl': f'{self_param.downloads_dir}/%(id)s.%(ext)s',
                                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                                'headers': {
                                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                    'Accept-Language': 'en-us,en;q=0.5',
                                },
                            }
                            
                            import yt_dlp
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(resolved_url, download=False)
                                print(f"DEBUG: yt-dlp info: {info.get('title', 'No title')}")
                                
                                if 'thumbnails' in info and info['thumbnails']:
                                    for thumb in info['thumbnails']:
                                        if thumb.get('url') and any(size in str(thumb.get('width', 0)) for size in ['720', '1080', '640']):
                                            img_url = thumb['url']
                                            print(f"DEBUG: Найден thumbnail высокого качества: {img_url}")
                                            break
                                    
                                    if not img_url and info['thumbnails']:
                                        img_url = info['thumbnails'][-1]['url']
                                        print(f"DEBUG: Используем последний thumbnail: {img_url}")
                                        
                        except Exception as e:
                            print(f"DEBUG: yt-dlp fallback ошибка: {e}")
                        
                        if not img_url:
                            print("DEBUG: Сохраняем HTML для анализа...")
                            try:
                                with open('/tmp/tiktok_debug.html', 'w', encoding='utf-8') as f:
                                    f.write(response.text)
                                print("DEBUG: HTML сохранен в /tmp/tiktok_debug.html")
                                
                                with open('/tmp/tiktok_scripts.txt', 'w', encoding='utf-8') as f:
                                    scripts = soup.find_all('script')
                                    for i, script in enumerate(scripts):
                                        if script.string:
                                            f.write(f"=== SCRIPT {i+1} ===\n")
                                            f.write(script.string[:5000])
                                            f.write(f"\n... (длина: {len(script.string)})\n\n")
                                print("DEBUG: Scripts сохранены в /tmp/tiktok_scripts.txt")
                            except Exception as e:
                                print(f"DEBUG: Ошибка сохранения файлов: {e}")
                            return None
                    
                    try:
                        img_response = requests.get(img_url, headers=headers, timeout=30)
                        img_response.raise_for_status()
                    except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as e:
                        print(f"DEBUG: Ошибка скачивания {img_url}: {e}")
                        print("DEBUG: Пробуем yt-dlp fallback...")
                        
                        img_url = None
                        try:
                            ydl_opts = {
                                'quiet': True,
                                'no_warnings': True,
                                'extractaudio': False,
                                'outtmpl': f'{self_param.downloads_dir}/%(id)s.%(ext)s',
                                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                                'headers': {
                                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                    'Accept-Language': 'en-us,en;q=0.5',
                                },
                            }
                            
                            import yt_dlp
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(resolved_url, download=False)
                                print(f"DEBUG: yt-dlp info: {info.get('title', 'No title')}")
                                
                                if 'thumbnails' in info and info['thumbnails']:
                                    for thumb in info['thumbnails']:
                                        if thumb.get('url') and any(size in str(thumb.get('width', 0)) for size in ['720', '1080', '640']):
                                            img_url = thumb['url']
                                            print(f"DEBUG: Найден thumbnail высокого качества: {img_url}")
                                            break
                                    
                                    if not img_url and info['thumbnails']:
                                        img_url = info['thumbnails'][-1]['url']
                                        print(f"DEBUG: Используем последний thumbnail: {img_url}")
                                
                                if img_url:
                                    img_response = requests.get(img_url, headers=headers, timeout=30)
                                    img_response.raise_for_status()
                                    print(f"DEBUG: Успешно скачали через yt-dlp fallback!")
                                        
                        except Exception as fallback_e:
                            print(f"DEBUG: yt-dlp fallback тоже не сработал: {fallback_e}")
                            
                        if not img_url:
                            print("DEBUG: TikTok фото не поддерживается yt-dlp")
                            return "TIKTOK_PHOTO_NOT_SUPPORTED"
                    
                    content_type = img_response.headers.get('content-type', '')
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    elif 'png' in content_type:
                        ext = '.png'
                    elif 'webp' in content_type:
                        ext = '.webp'
                    else:
                        ext = '.jpg'
                    
                    timestamp = str(int(time.time()))
                    filename = f'tiktok_photo_{timestamp}{ext}'
                    file_path = os.path.join(self.downloads_dir, filename)
                    
                    with open(file_path, 'wb') as f:
                        f.write(img_response.content)
                    
                    logger.info(f"TikTok фото успешно скачано: {file_path}")
                    return file_path
                    
                except Exception as e:
                    logger.error(f"Ошибка при скачивании TikTok фото: {e}")
                    return None
            
            return await loop.run_in_executor(None, _download_photo, url, self)
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке TikTok фото: {e}")
            return None

    async def get_media_info(self, url: str) -> Optional[Dict]:
        print(f"=== DEBUG START ===")
        print(f"get_media_info вызван для URL: {url}")
        print(f"URL type: {type(url)}")
        print(f"URL repr: {repr(url)}")
        
        url_lower = url.lower()
        has_tiktok = 'tiktok.com' in url_lower
        has_photo = '/photo/' in url_lower
        is_photo_direct = has_tiktok and has_photo
        
        print(f"Прямая проверка:")
        print(f"  URL lower: {url_lower}")
        print(f"  has_tiktok: {has_tiktok}")
        print(f"  has_photo: {has_photo}")
        print(f"  is_photo_direct: {is_photo_direct}")
        
        is_photo_method = self.is_tiktok_photo(url)
        print(f"  is_photo_method: {is_photo_method}")
        print(f"=== DEBUG END ===")
        
        logger.info(f"get_media_info вызван для URL: {url}")
        
        if is_photo_method:
            try:
                print("DEBUG: Используем специальную обработку для TikTok фото")
                logger.info("Используем специальную обработку для TikTok фото")
                return {
                    'title': 'TikTok Photo',
                    'duration': 0,
                    'uploader': 'TikTok User',
                    'view_count': 0,
                    'platform': 'tiktok',
                    'upload_date': '',
                    'thumbnail': '',
                    'filesize': 0,
                    'formats': 1,
                }
            except Exception as e:
                logger.error(f"Ошибка получения информации TikTok фото: {e}")
                return None
        
        print("DEBUG: Используем yt-dlp для получения информации")
        logger.info("Используем yt-dlp для получения информации")
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
            logger.error(f"Ошибка при получении информации о медиа: {e}")
            return None

    async def get_video_info(self, url: str) -> Optional[Dict]:
        return await self.get_media_info(url)

    async def download_media(self, url: str) -> Optional[str]:
        logger.info(f"download_media вызван для URL: {url}")
        
        if self.is_tiktok_photo(url):
            logger.info("Переход к download_tiktok_photo")
            return await self.download_tiktok_photo(url)
        
        try:
            loop = asyncio.get_event_loop()
            platform = self.detect_platform(url)
            is_photo = '/photo/' in url.lower()

            def _download():
                output_path = None
                timestamp = str(int(time.time()))

                download_opts = {
                    **self.base_ydl_opts,
                    'outtmpl': os.path.join(self.downloads_dir, f'media_{timestamp}_%(title).50s.%(ext)s'),
                }
                
                if is_photo:
                    download_opts['format'] = 'best'
                
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

                        extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.jpg', '.jpeg', '.png', '.webp']
                        for file in os.listdir(self.downloads_dir):
                            if file.startswith(f'media_{timestamp}_') and any(file.endswith(ext) for ext in extensions):
                                output_path = os.path.join(self.downloads_dir, file)
                                break

                        if output_path and os.path.exists(output_path):
                            actual_size = os.path.getsize(output_path)
                            if actual_size > Config.TELEGRAM_MAX_FILE_SIZE:
                                os.remove(output_path)
                                logger.warning(f"Скачанный файл слишком большой: {actual_size} байт")
                                return None

                            logger.info(f"Медиа успешно скачано: {output_path}")
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
            logger.error("Тайм-аут загрузки медиа")
            return None
        except Exception as e:
            logger.error(f"Ошибка при загрузке медиа: {e}")
            return None

    async def download_video(self, url: str) -> Optional[str]:
        return await self.download_media(url)

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