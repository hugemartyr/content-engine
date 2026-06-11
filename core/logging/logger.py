import sys
from loguru import logger
from core.settings.settings import settings

def setup_logger():
    # Remove default handler
    logger.remove()
    
    # Configure console handler
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        backtrace=True,
        diagnose=True
    )
    
    # Configure file logging for audit
    log_dir = settings.BASE_DIR / "outputs" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "app.log",
        rotation="10 MB",
        retention="1 week",
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        compression="zip"
    )

# Run logger setup immediately on import
setup_logger()

__all__ = ["logger"]
