"""Tool interno per estrarre candidate topic (persone, papi, brand, model)
da articoli già indicizzati. Vedi README di modulo + comandi CLI in
`app.topic_extractor.cli`.
"""

from .extractor import (
    NER_TYPES,
    extract_brand_alphanum,
    extract_brand_single,
    extract_models,
    extract_persons,
    extract_popes,
    normalize,
)

__all__ = [
    "NER_TYPES",
    "extract_brand_alphanum",
    "extract_brand_single",
    "extract_models",
    "extract_persons",
    "extract_popes",
    "normalize",
]
