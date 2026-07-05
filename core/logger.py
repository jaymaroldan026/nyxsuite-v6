import logging
from core.process_utils import LOGS_DIR, ensure_logs_dir

LOG_FILE = LOGS_DIR / "nyx_bot.log"

ensure_logs_dir()

logger = logging.getLogger("nyx_bot")
logger.setLevel(logging.INFO)
logger.propagate = False

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
