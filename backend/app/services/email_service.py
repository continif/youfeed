"""SMTP wrapper (OVH) + rendering template Jinja2.

Convenzione:
  - I nomi di template seguono `templates/emails/<name>.{html,txt}`.
  - Ogni `send_*` è un coroutine: lo chiama il worker RQ via asyncio.run, oppure
    il codice applicativo direttamente in test/integrazione.

Verifica deliverability lato OVH: SPF + DKIM + DMARC vanno configurati nel
DNS del dominio prima del primo invio in produzione (vedi docs).
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import get_settings

log = structlog.get_logger()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"

_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_template(name: str, **context: object) -> tuple[str, str]:
    """Renderizza `<name>.html` e `<name>.txt` in parallelo.

    Ritorna (html, text). Se il `.txt` è assente, ne genera uno minimale dal
    body HTML (basta per la maggior parte dei template).
    """
    html_tmpl = _jinja_env.get_template(f"{name}.html")
    html = html_tmpl.render(**context)

    try:
        text_tmpl = _jinja_env.get_template(f"{name}.txt")
        text = text_tmpl.render(**context)
    except Exception:
        # Fallback: crudo strip dell'HTML
        text = _strip_html(html)

    return html, text


def _strip_html(html: str) -> str:
    """Strip HTML grossolano per fallback text/plain."""
    import re

    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def send_email(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> None:
    """Invio singolo via SMTP OVH (STARTTLS o SSL secondo .env)."""
    settings = get_settings()
    if not settings.smtp_user or not settings.smtp_password:
        log.warning("yf.email.skipped_no_credentials", to=to, subject=subject)
        return

    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_address}>"
    msg["To"] = to
    msg["Subject"] = subject
    if text_body:
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
    else:
        msg.set_content(_strip_html(html_body))
        msg.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=settings.smtp_use_tls and not settings.smtp_use_ssl,
        use_tls=settings.smtp_use_ssl,
        timeout=20,
    )
    log.info("yf.email.sent", to=to, subject=subject)


# ---------------------------------------------------------------------------
# Template di alto livello
# ---------------------------------------------------------------------------


async def send_verification_email(*, to: str, username: str, token: str) -> None:
    settings = get_settings()
    link = f"{settings.yf_public_base_url.rstrip('/')}/verify-email?token={token}"
    html, text = render_template(
        "verify_email",
        username=username,
        link=link,
        site_name="YouFeed",
    )
    await send_email(
        to=to,
        subject="Verifica il tuo indirizzo email · YouFeed",
        html_body=html,
        text_body=text,
    )


async def send_password_reset_email(*, to: str, username: str, token: str) -> None:
    """Solo Phase 1.1: inclusa qui per simmetria, template arriverà allora."""
    settings = get_settings()
    link = f"{settings.yf_public_base_url.rstrip('/')}/reset-password?token={token}"
    html, text = render_template(
        "reset_password",
        username=username,
        link=link,
        site_name="YouFeed",
    )
    await send_email(
        to=to,
        subject="Reimposta la tua password · YouFeed",
        html_body=html,
        text_body=text,
    )
