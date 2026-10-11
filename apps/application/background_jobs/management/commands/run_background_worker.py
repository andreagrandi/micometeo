import logging
import os

from django.core.management.base import CommandError
from django.utils.autoreload import DJANGO_AUTORELOAD_ENV, run_with_reloader
from django_tasks_db.management.commands.db_worker import Command as DatabaseWorkerCommand

from background_jobs.services import recover_interrupted_jobs
from background_jobs.worker import MicometeoWorker


logger = logging.getLogger("django_tasks_db")


class Command(DatabaseWorkerCommand):
    help = "Recover Micometeo background jobs, then run the database worker."

    def handle(
        self,
        *,
        verbosity: int,
        queue_name: str,
        interval: float,
        batch: bool,
        backend_name: str,
        startup_delay: bool,
        reload: bool,
        max_tasks: int | None,
        worker_id: str,
        exclude_queues: str,
        **options: dict,
    ) -> None:
        recover_interrupted_jobs()
        self.configure_logging(verbosity)

        if reload and batch:
            logger.warning(
                "Warning: --reload and --batch cannot be specified together. Disabling autoreload."
            )
            reload = False

        queue_names = queue_name.split(",")
        excluded_queue_names = exclude_queues.split(",") if exclude_queues else []
        if excluded_queue_names and "*" not in queue_names:
            raise CommandError("--exclude-queues can only be used with --queue-name=*")
        worker = MicometeoWorker(
            queue_names=queue_names,
            interval=interval,
            batch=batch,
            backend_name=backend_name,
            startup_delay=startup_delay,
            max_tasks=max_tasks,
            worker_id=worker_id,
            excluded_queue_names=excluded_queue_names,
        )

        if reload:
            if os.environ.get(DJANGO_AUTORELOAD_ENV) == "true":
                worker.configure_signals()
            run_with_reloader(worker.run)
        else:
            worker.configure_signals()
            worker.run()
