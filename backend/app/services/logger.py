import logging
from pathlib import Path

# Resolve logs directory at backend root
BACKEND_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = BACKEND_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# Initialize logger
clm_logger = logging.getLogger("clm_backend")
clm_logger.setLevel(logging.INFO)

# Setup handlers if not already configured to avoid duplicate logs on import reload
if not clm_logger.handlers:
    # File Handler: UTF-8 encoded file writer
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    # Standard Console Handler: logs critical application milestones
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter: Timestamp, Level, Source File/Line, Message
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    clm_logger.addHandler(file_handler)
    clm_logger.addHandler(console_handler)

    # Set propagate to False so uvicorn / other library root loggers do not duplicate logs
    clm_logger.propagate = False
