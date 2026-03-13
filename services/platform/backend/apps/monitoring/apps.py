import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Management commands where cache warm-up is pointless (no server running).
_SKIP_WARMUP_COMMANDS = {
    "collectstatic",
    "migrate",
    "makemigrations",
    "check",
    "shell",
}


class MonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.monitoring"
    verbose_name = "Monitoring"

    def ready(self) -> None:
        """Warm SHM spectral and peak caches in a background thread.

        Loading the 131 MB HDF5 file and running ~10k scipy find_peaks
        calls takes 5-15 seconds. Doing this at startup means the first
        user request hits a warm cache instead of timing out.

        Skipped when:
        - Running management commands that don't serve requests
        - In the run_realtime master process (before gunicorn fork) —
          signaled via _SEQUOIA_SKIP_WARMUP env var, which is set by
          run_realtime and cleared before launching gunicorn/uvicorn
        """
        if self._should_skip_warmup():
            return

        thread = threading.Thread(target=self._warm_shm_cache, daemon=True)
        thread.start()

    @staticmethod
    def _should_skip_warmup() -> bool:
        """Return True if warmup should be skipped in this process."""
        # Explicit skip flag set by run_realtime master process
        if os.environ.get("_SEQUOIA_SKIP_WARMUP") == "1":
            return True
        # Management commands that don't serve requests
        return len(sys.argv) > 1 and sys.argv[1] in _SKIP_WARMUP_COMMANDS

    @staticmethod
    def _warm_shm_cache() -> None:
        from apps.monitoring.hdf5_reader import load_peak_frequencies, sample_file_exists

        if not sample_file_exists():
            logger.info("SHM sample file not found, skipping cache warm-up")
            return

        try:
            logger.info("Warming SHM spectral + peak cache...")
            load_peak_frequencies()  # This also triggers load_spectral_data
            logger.info("SHM cache warm-up complete")
        except Exception:
            logger.warning("SHM cache warm-up failed", exc_info=True)
