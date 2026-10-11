import logging
import os
import random
import time
import uuid
from contextlib import nullcontext

from django.db import close_old_connections
from django.db.utils import OperationalError
from django_tasks_db.management.commands.db_worker import Worker as DatabaseWorker
from django_tasks_db.models import DBTaskResult
from django_tasks_db.utils import exclusive_transaction, is_locked_database_exception

from .models import BackgroundJobAttempt
from .services import logical_job_lock


logger = logging.getLogger("django_tasks_db")


REPRESENTATIVE_TASK_PATH = "background_jobs.tasks.representative_job_task"


class MicometeoWorker(DatabaseWorker):
    """Claim representative tasks while holding their logical job lock."""

    def _logical_key_for_task(self, task_result: DBTaskResult) -> str | None:
        if task_result.task_path != REPRESENTATIVE_TASK_PATH:
            return None
        attempt_id = task_result.args_kwargs.get("kwargs", {}).get("attempt_id")
        if attempt_id is None:
            return None
        try:
            parsed_attempt_id = uuid.UUID(str(attempt_id))
        except ValueError:
            return None
        attempt = (
            BackgroundJobAttempt.objects.select_related("job")
            .filter(id=parsed_attempt_id)
            .first()
        )
        return attempt.job.logical_key if attempt is not None else None

    def _claim_task(
        self,
        *,
        tasks,
        pause_after_claim: float,
    ) -> tuple[DBTaskResult | None, bool]:
        candidates = list(tasks[:50])
        if not candidates:
            return None, True

        for candidate in candidates:
            logical_key = self._logical_key_for_task(candidate)
            lock_context = (
                logical_job_lock(logical_key=logical_key, wait=False)
                if logical_key is not None
                else nullcontext(True)
            )
            with lock_context as acquired:
                if not acquired:
                    continue
                try:
                    with exclusive_transaction(tasks.db):
                        task_result = tasks.filter(id=candidate.id).get_locked()
                        if task_result is not None:
                            task_result.claim(self.worker_id)
                except OperationalError as exc:
                    if is_locked_database_exception(exc):
                        continue
                    raise
                if task_result is not None:
                    if pause_after_claim:
                        time.sleep(pause_after_claim)
                    self.run_task(task_result)
                    return task_result, True

        return None, False

    def run(self) -> None:
        logger.info(
            "Starting worker worker_id=%s queues=%s",
            self.worker_id,
            ",".join(self.queue_names),
        )
        if self.startup_delay and self.interval:
            time.sleep(random.random())

        pause_after_claim = float(
            os.environ.get("MICOMETEO_TEST_PAUSE_AFTER_TASK_CLAIM", "0")
        )
        while self.running:
            close_old_connections()
            tasks = DBTaskResult.objects.ready().filter(backend_name=self.backend_name)
            if not self.process_all_queues:
                tasks = tasks.filter(queue_name__in=self.queue_names)
            if self.excluded_queue_names:
                tasks = tasks.exclude(queue_name__in=self.excluded_queue_names)

            task_result, retrieved_task_result = self._claim_task(
                tasks=tasks,
                pause_after_claim=pause_after_claim,
            )

            if self.batch and retrieved_task_result and task_result is None:
                logger.info(
                    "No more tasks to run for worker_id=%s - exiting gracefully.",
                    self.worker_id,
                )
                return None

            if self.max_tasks is not None and self._run_tasks >= self.max_tasks:
                logger.info(
                    "Run maximum tasks (%d) on worker=%s - exiting gracefully.",
                    self._run_tasks,
                    self.worker_id,
                )
                return None

            close_old_connections()
            if self.running and task_result is None:
                time.sleep(self.interval)
