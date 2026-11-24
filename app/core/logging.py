import logging


def configure_logging(level: str) -> None:
    """Configure the root logger once; uvicorn keeps its own access/error loggers."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    )
