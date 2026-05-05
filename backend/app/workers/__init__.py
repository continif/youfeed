"""Worker RQ.

Lanciare un worker:
    rq worker --url $RQ_REDIS_URL <coda1> <coda2> ...

Esempi:
    rq worker --url redis://localhost:6379/1 email
    rq worker --url redis://localhost:6379/1 process_article image_processor
"""
