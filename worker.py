"""
Воркер для обработки задач из очередей Redis.
Запускается как отдельный процесс и обрабатывает задачи асинхронно.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional, Dict, Any
from datetime import datetime

from redis_queue import RedisQueue, RedisQueueError
from redis_config import WORKER_POLL_INTERVAL, NUM_WORKERS, QUEUE_CONFIG
import models_config
import token_utils
from global_state import SYSTEM_PROMPTS, MODELS

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("worker.log", encoding="utf-8", mode="a"),
    ],
)
logger = logging.getLogger("worker")


class Worker:
    """
    Воркер для обработки задач из Redis очередей.

    Поддерживает:
    -Graceful shutdown
    -Периодический опрос очередей
    -Обработку ошибок и повторные попытки
    -Статистику выполнения
    """

    def __init__(self, worker_id: int = 0):
        """
        Инициализация воркера.

        Args:
            worker_id: Уникальный идентификатор воркера
        """
        self.worker_id = worker_id
        self.name = f"worker-{worker_id}"
        self.queue: Optional[RedisQueue] = None
        self.running = False
        self.tasks_processed = 0
        self.tasks_failed = 0
        self.start_time: Optional[datetime] = None

        # Флаг для graceful shutdown
        self._shutdown_requested = False

        # Регистрируем обработчики сигналов
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Обработчик сигналов завершения"""
        logger.info(
            f"{self.name}: Получен сигнал {signum}, завершаю работу..."
        )
        self._shutdown_requested = True

    async def start(self):
        """Запуск воркера"""
        logger.info(f"{self.name}: Инициализация...")

        try:
            self.queue = RedisQueue()
            self.running = True
            self.start_time = datetime.utcnow()

            logger.info(f"{self.name}: ✅ Воркер запущен")
            logger.info(
                f"{self.name}: Опрос очередей каждые {WORKER_POLL_INTERVAL}с"
            )

            await self._process_loop()

        except Exception as e:
            logger.exception(f"{self.name}: Критическая ошибка: {e}")
            raise
        finally:
            await self._shutdown()

    async def _process_loop(self):
        """Основной цикл обработки задач"""
        while self.running and not self._shutdown_requested:
            try:
                # Получаем задачу из очереди с таймаутом
                task = self.queue.dequeue(
                    queue_types=list(QUEUE_CONFIG.keys())[
                        :4
                    ],  # Основные очереди
                    timeout=int(WORKER_POLL_INTERVAL),
                    priority_aware=True,
                )

                if task:
                    await self._process_task(task)
                else:
                    # Очередь пуста, продолжаем цикл
                    await asyncio.sleep(0.1)

            except RedisQueueError as e:
                logger.error(f"{self.name}: Ошибка очереди: {e}")
                await asyncio.sleep(1)  # Пауза перед повторной попыткой

            except Exception as e:
                logger.exception(f"{self.name}: Неожиданная ошибка: {e}")
                await asyncio.sleep(1)

    async def _process_task(self, task: Dict[str, Any]):
        """
        Обработка отдельной задачи.

        Args:
            task: Данные задачи из очереди
        """
        task_id = task["id"]
        task_type = task.get("type", "unknown")
        task_data = task.get("data", {})

        logger.info(
            f"{self.name}: 📋 Обработка задачи {task_id} (тип: {task_type})"
        )

        start_time = datetime.utcnow()

        try:
            # Диспетчеризация по типу задачи
            if task_type == "chat":
                result = await self._process_chat(task_data)
            elif task_type == "file":
                result = await self._process_file(task_data)
            elif task_type == "image_gen":
                result = await self._process_image_gen(task_data)
            elif task_type == "image_edit":
                result = await self._process_image_edit(task_data)
            else:
                raise ValueError(f"Неизвестный тип задачи: {task_type}")

            # Вычисляем время выполнения
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            # Сохраняем результат
            self.queue.set_task_completed(
                task_id,
                {
                    "result": result,
                    "processing_time": processing_time,
                    "worker_id": self.worker_id,
                },
            )

            self.tasks_processed += 1
            logger.info(
                f"{self.name}: ✅ Задача {task_id} выполнена "
                f"за {processing_time:.2f}с"
            )

        except Exception as e:
            self.tasks_failed += 1
            logger.exception(
                f"{self.name}: ❌ Задача {task_id} не выполнена: {e}"
            )
            self.queue.set_task_failed(task_id, str(e), exc_info=True)

    async def _process_chat(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка задачи чата.

        Args:
            data: Данные задачи (user_id, message, context)

        Returns:
            Результат обработки
        """
        user_id = data.get("user_id")
        message = data.get("message")
        context_history = data.get("context", [])
        enable_web_search = data.get("enable_web_search", False)

        if not user_id or not message:
            raise ValueError("Отсутствует user_id или message")

        model_name = MODELS.get("chat", "gpt-5.2-chat-latest")

        # Проверяем токены
        total_tokens = token_utils.token_counter.count_openai_messages_tokens(
            context_history + [{"role": "user", "content": message}],
            model_name,
        )

        # Формируем полный контекст
        system_message = SYSTEM_PROMPTS.get("chat", "")
        full_context = (
            [{"role": "system", "content": system_message}]
            + context_history
            + [{"role": "user", "content": message}]
        )

        # Вызов API
        response = await models_config.ask_gpt51_with_web_search(
            context_history=full_context,
            enable_web_search=enable_web_search,
        )

        return {
            "response": response,
            "model": model_name,
            "tokens_used": total_tokens,
        }

    async def _process_file(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка задачи анализа файла.

        Args:
            data: Данные задачи (user_id, question, file_text, context)

        Returns:
            Результат обработки
        """
        user_id = data.get("user_id")
        question = data.get("question")
        file_text = data.get("file_text", "")
        context_history = data.get("context", [])

        if not user_id or not question:
            raise ValueError("Отсутствует user_id или question")

        model_name = MODELS.get("ai_file", "gpt-5.2-chat-latest")

        # Формируем запрос с содержимым файла
        augmented_question = (
            f"Файл содержит следующий текст: {file_text}\n\n"
            f"Вопрос: {question}"
        )

        # Проверяем длину
        max_chars = 50000  # Консервативный лимит
        if len(augmented_question) > max_chars:
            augmented_question = augmented_question[:max_chars]

        # Формируем контекст
        system_message = SYSTEM_PROMPTS.get("ai_file", "")
        full_context = (
            [{"role": "system", "content": system_message}]
            + context_history
            + [{"role": "user", "content": augmented_question}]
        )

        # Вызов API
        response = await models_config.ask_gpt51_with_web_search(
            context_history=full_context,
            enable_web_search=False,
        )

        return {
            "response": response,
            "model": model_name,
            "file_length": len(file_text),
        }

    async def _process_image_gen(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработка задачи генерации изображения.

        Args:
            data: Данные задачи (user_id, prompt)

        Returns:
            Результат обработки (URL изображения)
        """
        user_id = data.get("user_id")
        prompt = data.get("prompt", "")

        if not user_id or not prompt:
            raise ValueError("Отсутствует user_id или prompt")

        # Генерация изображения
        image_url = await models_config.generate_image(prompt)

        return {
            "image_url": image_url,
            "prompt": prompt,
            "model": MODELS.get("image", "gemini-3-pro-image-preview"),
        }

    async def _process_image_edit(
        self, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Обработка задачи редактирования изображения.

        Args:
            data: Данные задачи (user_id, prompt, image_paths)

        Returns:
            Результат обработки
        """
        user_id = data.get("user_id")
        prompt = data.get("prompt", "")
        image_paths = data.get("image_paths", [])

        if not user_id or not prompt:
            raise ValueError("Отсутствует user_id или prompt")

        # Здесь будет вызов функции редактирования изображений
        # Пока заглушка - нужно реализовать в image_edit_utils
        from image_edit_utils import edit_image_with_gemini

        edited_image_path = await edit_image_with_gemini(
            prompt=prompt,
            image_paths=image_paths,
        )

        return {
            "edited_image_path": edited_image_path,
            "prompt": prompt,
            "source_images": image_paths,
        }

    async def _shutdown(self):
        """Корректное завершение работы"""
        logger.info(f"{self.name}: Завершение работы...")
        self.running = False

        if self.queue:
            self.queue.close()

        # Логируем статистику
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
            logger.info(
                f"{self.name}: 📊 Статистика: "
                f"обработано={self.tasks_processed}, "
                f"ошибок={self.tasks_failed}, "
                f"время работы={uptime:.0f}с"
            )

        logger.info(f"{self.name}: 👋 Воркер остановлен")


async def run_worker(worker_id: int = 0):
    """Точка входа для запуска воркера"""
    worker = Worker(worker_id)
    await worker.start()


def main():
    """Основная функция для запуска из командной строки"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Воркер обработки задач Redis"
    )
    parser.add_argument(
        "--id", type=int, default=0, help="Идентификатор воркера"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=NUM_WORKERS,
        help=f"Количество воркеров (по умолчанию {NUM_WORKERS})",
    )

    args = parser.parse_args()

    if args.workers > 1:
        # Запуск нескольких воркеров
        logger.info(f"Запуск {args.workers} воркеров...")

        async def run_all_workers():
            tasks = [run_worker(args.id + i) for i in range(args.workers)]
            await asyncio.gather(*tasks)

        try:
            asyncio.run(run_all_workers())
        except KeyboardInterrupt:
            logger.info("Получен сигнал завершения")
    else:
        # Запуск одного воркера
        try:
            asyncio.run(run_worker(args.id))
        except KeyboardInterrupt:
            logger.info("Получен сигнал завершения")


if __name__ == "__main__":
    main()
