import asyncio
import logging
import os
import re
import time
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import Config
from youtube_downloader import MediaDownloader

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class MediaTelegramBot:
    def __init__(self):
        self.downloader = MediaDownloader()
        self.download_semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_DOWNLOADS)
        self.active_downloads = 0
        self.total_processed = 0

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = (
            f"📋 *Инструкция по использованию:*\n\n"
            f"1️⃣ Скопируйте ссылку на видео или фото\n"
            f"2️⃣ Отправьте её мне в чат\n"
            f"3️⃣ Получите файл для скачивания\n\n"
            f" *Поддерживаемые платформы:*\n"
            f" YouTube \\(видео\\)\n"
            f" Instagram \\(видео, фото\\)\n"
            f" TikTok \\(видео\\)\n\n"
        )
        
        await update.message.reply_text(
            welcome_message, 
            parse_mode='MarkdownV2'
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_message = (
            f"{Config.STATUS_EMOJIS['warning']} *Помощь по использованию бота*\n\n"
            f"🎯 *Поддерживаемые форматы ссылок:*\n\n"
            f"📺 *YouTube:*\n"
            f"• `youtube\\.com/watch\\?v\\=` \\(только видео\\)\n"
            f"• `youtu\\.be/` \\(только видео\\)\n"
            f"• `youtube\\.com/shorts/` \\(только видео\\)\n\n"
            f"📱 *Instagram:*\n"
            f"• `instagram\\.com/p/` \\(видео и фото\\)\n"
            f"• `instagram\\.com/reel/` \\(видео\\)\n\n"
            f"🎭 *TikTok:*\n"
            f"• `tiktok\\.com/@username/video/` \\(видео\\)\n"
            f"• `tiktok\\.com/@username/photo/` \\(фото\\)\n"
            f"• `vm\\.tiktok\\.com/` \\(видео\\)\n\n"
            f"⚠️ *Ограничения:*\n"
            f"• Максимальный размер: {Config.MAX_FILE_SIZE_MB} МБ\n"
            f"• Приватные аккаунты не поддерживаются\n\n"
            f"🚀 *Команды:*\n"
            f"/start \\- главное меню\n"
            f"/help \\- эта справка"
        )
        
        await update.message.reply_text(help_message, parse_mode='MarkdownV2')

    def is_supported_url(self, url: str) -> bool:
        url_lower = url.lower()
            
        for platform_info in Config.SUPPORTED_PLATFORMS.values():
            for pattern in platform_info['patterns']:
                if pattern in url_lower:
                    return True
        return False

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message_text = update.message.text.strip()

        if self.is_supported_url(message_text):
            await self.download_media(update, context, message_text)
        else:
            await update.message.reply_text(
                f"{Config.STATUS_EMOJIS['error']} *Неподдерживаемая ссылка*\n\n"
                f"Отправьте ссылку на видео с одной из поддерживаемых платформ:\n\n"
                f"📺 YouTube\n📱 Instagram\n🎭 TikTok\n\n"
                f"Нажмите /help для подробной справки\\.",
                parse_mode='MarkdownV2'
            )

    async def download_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        platform_info = self.downloader.get_platform_info(url)
        
        # Определяем тип контента
        is_photo = '/photo/' in url.lower()
        content_type = "фото" if is_photo else "видео"
        content_emoji = "📸" if is_photo else "📹"
        
        async with self.download_semaphore:
            self.active_downloads += 1
            logger.info(f"Начинаю загрузку {content_type} для пользователя {user_id}. Активных загрузок: {self.active_downloads}")
            
            status_message = await update.message.reply_text(
                f"{Config.STATUS_EMOJIS['processing']} *Обработка запроса*\n\n"
                f"{platform_info['emoji']} Платформа: {platform_info['name']}\n"
                f"{content_emoji} Тип: {content_type}\n"
                f"👥 В очереди: {self.active_downloads}\n"
                f"🔄 Получение информации\\.\\.\\.",
                parse_mode='MarkdownV2'
            )
            
            file_path = None
            try:
                await status_message.edit_text(
                    f"{Config.STATUS_EMOJIS['processing']} *Получение информации*\n\n"
                    f"{platform_info['emoji']} {platform_info['name']}\n"
                    f"{content_emoji} Анализ {content_type}\\.\\.\\.",
                    parse_mode='MarkdownV2'
                )
                
                media_info = await self.downloader.get_media_info(url)

                if not media_info:
                    await status_message.edit_text(
                        f"{Config.STATUS_EMOJIS['error']} *Ошибка получения информации*\n\n"
                        f"Не удалось получить данные о {content_type}\\.\n"
                        f"Возможные причины:\n"
                        f"• Приватный аккаунт\n"
                        f"• Удаленный контент\n"
                        f"• Проблемы с сетью",
                        parse_mode='MarkdownV2'
                    )
                    return

                title = media_info.get('title', 'Unknown')
                duration = media_info.get('duration', 0) or 0
                uploader = media_info.get('uploader', 'Unknown')
                platform = media_info.get('platform', 'unknown')

                if duration > 3600:
                    await status_message.edit_text(
                        f"{Config.STATUS_EMOJIS['warning']} *{content_type.capitalize()} слишком длинное*\n\n"
                        f"🕐 Длительность: {int(duration)//60} мин\\.\n"
                        f"⚠️ Максимум: 60 мин\\.\n\n"
                        f"Попробуйте {content_type} покороче\\.",
                        parse_mode='MarkdownV2'
                    )
                    return

                duration_str = f"{int(duration)//60}:{int(duration)%60:02d}" if duration else "неизвестно"
                
                await status_message.edit_text(
                    f"{Config.STATUS_EMOJIS['downloading']} *Начинаю загрузку*\n\n"
                    f"{platform_info['emoji']} *{title[:40]}\\.\\.\\.*\n"
                    f"👤 Автор: {uploader[:30]}\n"
                    f"⏱️ Длительность: {duration_str}\n\n"
                    f"📥 Скачивание\\.\\.\\.",
                    parse_mode='MarkdownV2'
                )

                file_path = await self.downloader.download_media(url)

                # Специальная обработка TikTok фото
                if file_path == "TIKTOK_PHOTO_NOT_SUPPORTED":
                    await status_message.edit_text(
                        f"{Config.STATUS_EMOJIS['error']} *TikTok фото не поддерживается*\n\n"
                        f"К сожалению, TikTok фото пока не поддерживается\\.\n"
                        f"Работает только с TikTok видео\\.\n\n"
                        f"Попробуйте:\n"
                        f"• TikTok видео вместо фото\n"
                        f"• Другие платформы \\(YouTube, Instagram\\)",
                        parse_mode='MarkdownV2'
                    )
                    return

                if not file_path or not os.path.exists(file_path):
                    await status_message.edit_text(
                        f"{Config.STATUS_EMOJIS['error']} *Ошибка загрузки*\n\n"
                        f"Не удалось скачать {content_type}\\.\n"
                        f"Попробуйте:\n"
                        f"• Другую ссылку\n"
                        f"• Повторить позже\n"
                        f"• Проверить доступность контента",
                        parse_mode='MarkdownV2'
                    )
                    return

                file_size = os.path.getsize(file_path)
                if file_size > Config.TELEGRAM_MAX_FILE_SIZE:
                    await status_message.edit_text(
                        f"{Config.STATUS_EMOJIS['warning']} *Файл слишком большой*\n\n"
                        f"📦 Размер: {file_size//1024//1024} МБ\n"
                        f"⚠️ Лимит: {Config.MAX_FILE_SIZE_MB} МБ\n\n"
                        f"Попробуйте {content_type} поменьше\\.",
                        parse_mode='MarkdownV2'
                    )
                    return

                await status_message.edit_text(
                    f"{Config.STATUS_EMOJIS['uploading']} *Отправка {content_type}*\n\n"
                    f"📤 Загружаю в Telegram\\.\\.\\.",
                    parse_mode='MarkdownV2'
                )

                with open(file_path, 'rb') as media_file:
                    if is_photo:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=media_file,
                            caption=(
                                f"{platform_info['emoji']} {title[:50]}\n"
                                f"👤 {uploader}"
                            ),
                            parse_mode='MarkdownV2'
                        )
                    else:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=media_file,
                            caption=(
                                f"{platform_info['emoji']} {title[:50]}\n"
                                f"👤 {uploader}"
                            ),
                            parse_mode='MarkdownV2',
                            supports_streaming=True
                        )

                await status_message.delete()
                self.total_processed += 1
                logger.info(f"Медиа успешно отправлено пользователю {user_id}. Всего обработано: {self.total_processed}")

            except Exception as e:
                logger.error(f"Ошибка при загрузке медиа для пользователя {user_id}: {e}")

                await status_message.edit_text(
                    f"{Config.STATUS_EMOJIS['error']} *Произошла ошибка*\n\n"
                    f"⚠️ Не удалось обработать запрос\\.\n"
                    f"Попробуйте еще раз или обратитесь к администратору\\.",
                    parse_mode='MarkdownV2'
                )

                if "403" in str(e) or "Forbidden" in str(e):
                    error_message = (
                        "❌ Видео заблокировано для скачивания.\n"
                        "Это может быть связано с:\n"
                        "• Ограничениями правообладателя\n"
                        "• Географическими блокировками\n"
                        "• Временными ограничениями YouTube\n\n"
                        "Попробуйте другое видео или повторите позже."
                    )
                elif "404" in str(e) or "not found" in str(e).lower():
                    error_message = (
                        "❌ Видео не найдено.\n"
                        "Возможно, оно было удалено или ссылка неверна."
                    )
                elif "timeout" in str(e).lower():
                    error_message = (
                        "❌ Превышено время ожидания.\n"
                        "Попробуйте позже или выберите видео поменьше."
                    )
                elif "Video not available, status code 0" in str(e):
                    error_message = (
                        "❌ Видео недоступно для скачивания.\n"
                        "TikTok блокирует автоматические запросы.\n"
                        "Попробуйте:\n"
                        "• Другое видео\n"
                        "• Повторить через несколько минут\n"
                        "• Проверить, что видео публичное"
                    )
                else:
                    error_message = "❌ Произошла ошибка при обработке видео.\nПопробуйте позже или с другой ссылкой."

                await status_message.edit_text(error_message)
            
            finally:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"Файл {file_path} удален после обработки")
                    except Exception as cleanup_error:
                        logger.error(f"Ошибка при удалении файла {file_path}: {cleanup_error}")
                
                self.active_downloads -= 1
                logger.info(f"Загрузка завершена для пользователя {user_id}. Активных загрузок: {self.active_downloads}")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Произошла ошибка: {context.error}")

        if update and update.message:
            await update.message.reply_text(
                f"{Config.STATUS_EMOJIS['error']} *Системная ошибка*\n\n"
                f"Произошла неожиданная ошибка\\.\n"
                f"Попробуйте позже\\.",
                parse_mode='MarkdownV2'
            )

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        platforms_stats = "\n".join([
            f"{info['emoji']} {info['name']}" 
            for info in Config.SUPPORTED_PLATFORMS.values()
        ])
        
        stats_message = (
            f"{Config.STATUS_EMOJIS['processing']} *Статистика бота*\n\n"
            f"� *Текущее состояние:*\n"
            f"�🔄 Активных загрузок: {self.active_downloads}\n"
            f"✅ Всего обработано: {self.total_processed}\n"
            f"⚡ Лимит одновременных: {Config.MAX_CONCURRENT_DOWNLOADS}\n\n"
            f"🎯 *Поддерживаемые платформы:*\n"
            f"{platforms_stats}\n\n"
            f"🚀 *Бот работает стабильно\\!*"
        )
        
        await update.message.reply_text(stats_message, parse_mode='MarkdownV2')

    async def cleanup_task(self):
        while True:
            try:
                await asyncio.sleep(Config.CLEANUP_INTERVAL_HOURS * 3600)
                await self.downloader.cleanup_old_files_async()
                logger.info("Выполнена периодическая очистка файлов")
            except Exception as e:
                logger.error(f"Ошибка при периодической очистке: {e}")


def main():
    try:
        Config.validate()

        application = Application.builder().token(Config.BOT_TOKEN).build()

        bot = MediaTelegramBot()

        application.add_handler(CommandHandler("start", bot.start_command))
        application.add_handler(CommandHandler("help", bot.help_command))
        application.add_handler(CommandHandler("stats", bot.stats_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

        application.add_error_handler(bot.error_handler)

        logger.info(f"🚀 Бот запущен с поддержкой {Config.MAX_CONCURRENT_DOWNLOADS} одновременных загрузок!")

        loop = asyncio.get_event_loop()
        loop.create_task(bot.cleanup_task())

        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        print(f"❌ Ошибка запуска: {e}")


if __name__ == '__main__':
    main()