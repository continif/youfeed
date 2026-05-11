"""Configurazione logging strutturato (structlog).

In dev: output umano-leggibile colorato. In prod (LOG_JSON=true): JSON
line-per-line per ingest da journald/Loki.

Architettura: structlog routa via stdlib `logging` con un singolo handler
sullo stderr. Niente `PrintLoggerFactory` separato per evitare doppia
emissione (un handler stdlib + un PrintLogger producevano due righe
identiche per ogni log SQL di SQLAlchemy).
"""

from __future__ import annotations

import logging
import sys

import structlog

from .config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    # structlog -> stdlib (i log structlog escono attraverso logging.Logger,
    # non scrivono direttamente su stderr come faceva PrintLoggerFactory).
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Un solo handler stdlib sullo stderr. Il formatter di structlog renderizza
    # SIA i log structlog (già processati) SIA i log "foreign" stdlib
    # (uvicorn, sqlalchemy, ...) applicando shared_processors a entrambi.
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Pulisci handler preesistenti (es. quelli di uvicorn auto-config)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    # Riduce verbosità delle lib rumorose
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # SQLAlchemy: di default WARNING. Se serve debug query, settare LOG_LEVEL=DEBUG
    # in .env e l'engine `echo=True` (settings.yf_debug) farà uscire le query.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
