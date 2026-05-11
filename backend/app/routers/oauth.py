"""Endpoint OAuth (Phase 1.1.A).

In v1.1 questo router espone i tre endpoint dell'Authorization Code flow:

    GET /yf_auth/google/authorize?next=<path>
    GET /yf_auth/google/callback?code=<...>&state=<...>
    GET /yf_auth/google/_mock?state=<...>            (solo dev/sim)

L'integrazione Google reale è dietro `oauth_service.is_simulate()`. Finché
`google_oauth_client_id` è vuoto in .env (default dev), il flow gira via
una pagina di consenso stub locale che NON parla con Google. Quando si
configurerà il client_id, `build_authorize_redirect` produrrà direttamente
l'URL Google e `exchange_code` chiamerà l'API token.
"""

from __future__ import annotations

import html
import urllib.parse

import structlog
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.deps import DB
from app.exceptions import AppError
from app.services import auth_service, oauth_service

log = structlog.get_logger()

router = APIRouter(prefix="/yf_auth/google", tags=["auth", "oauth"])


def _safe_next(next_path: str | None) -> str:
    """Whitelist next: solo path interni che iniziano con `/` (no `//host`)."""
    if not next_path:
        return "/me/feed"
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/me/feed"
    return next_path


def _set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=60 * 60 * 24 * settings.session_lifetime_days,
        domain=settings.session_cookie_domain or None,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Authorize: avvia il flow → 302 verso la pagina di consenso
# ---------------------------------------------------------------------------


@router.get("/authorize")
async def authorize(next: str = Query(default="/me/feed", max_length=512)) -> RedirectResponse:
    redirect_url = oauth_service.build_authorize_redirect(_safe_next(next))
    return RedirectResponse(url=redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# Callback: scambia code → profilo → user → sessione → 302 al next
# ---------------------------------------------------------------------------


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(min_length=1, max_length=512),
    state: str = Query(min_length=1, max_length=1024),
    db: DB = ...,
) -> RedirectResponse:
    state_data = oauth_service.verify_state(state)
    next_path = _safe_next(str(state_data.get("next") or "/me/feed"))

    profile = await oauth_service.exchange_code(code, state)
    user = await oauth_service.find_or_create_oauth_user(db, profile)

    auth_session = await auth_service.create_session(
        db,
        user=user,
        fingerprint=request.headers.get("X-YF-Fingerprint"),
        client=request.headers.get("X-YF-Client", "web"),
        ip=getattr(request.state, "client_ip", None),
        country=getattr(request.state, "country", None),
        asn=getattr(request.state, "asn", None),
        ua=request.headers.get("User-Agent"),
    )
    await db.commit()

    log.info(
        "yf.auth.google_callback",
        user_id=user.id,
        session_id=str(auth_session.id),
        simulated=oauth_service.is_simulate(),
    )

    # Redirect relativo: browser segue same-origin, così il cookie settato
    # sul callback è visibile alla pagina di destinazione (dev: Vite proxy,
    # prod: Apache /yf_* → backend, /me/* → SPA, stesso host).
    response = RedirectResponse(url=next_path, status_code=302)
    _set_session_cookie(response, str(auth_session.id))
    return response


# ---------------------------------------------------------------------------
# Mock consent page — solo quando is_simulate() == True
# ---------------------------------------------------------------------------


_MOCK_PAGE_TPL = """<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>YouFeed — Google OAuth (mock)</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ font-family: system-ui, sans-serif; background: #f1f5f9; margin: 0; padding: 0; }}
    .card {{ max-width: 380px; margin: 8vh auto; background: #fff; border-radius: 12px;
            box-shadow: 0 8px 28px rgba(0,0,0,.08); padding: 24px 28px; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px;
             background: #fef3c7; color: #92400e; font-size: 11px; font-weight: 600;
             text-transform: uppercase; letter-spacing: .05em; margin-bottom: 12px; }}
    h1 {{ font-size: 18px; margin: 0 0 4px; color: #0f172a; }}
    p.lead {{ color: #475569; font-size: 13px; margin: 0 0 16px; line-height: 1.5; }}
    label {{ display: block; font-size: 12px; color: #334155; margin-bottom: 6px; font-weight: 600; }}
    input {{ width: 100%; padding: 9px 12px; border: 1px solid #cbd5e1; border-radius: 8px;
            font-size: 14px; box-sizing: border-box; }}
    input:focus {{ outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,.15); }}
    .row {{ display: flex; gap: 8px; margin-top: 16px; }}
    button {{ flex: 1; padding: 9px 14px; border-radius: 8px; font-size: 14px; font-weight: 600;
             cursor: pointer; border: 1px solid transparent; }}
    .primary {{ background: #2563eb; color: white; }}
    .primary:hover {{ background: #1d4ed8; }}
    .secondary {{ background: #f1f5f9; color: #334155; border-color: #cbd5e1; }}
    .secondary:hover {{ background: #e2e8f0; }}
    .hint {{ font-size: 11px; color: #94a3b8; margin-top: 14px; line-height: 1.4; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">MOCK Google</span>
    <h1>Accedi a YouFeed</h1>
    <p class="lead">Stub di sviluppo. Inserisci l'email Google con cui vuoi entrare;
       l'utente verrà creato o riconosciuto automaticamente.</p>
    <form method="get" action="/yf_auth/google/callback">
      <input type="hidden" name="state" value="{state_attr}">
      <input type="hidden" name="code" id="code-field" value="">
      <label for="email">Email Google</label>
      <input type="email" id="email" name="_email" required
             placeholder="mario.rossi@gmail.com" autofocus>
      <div class="row">
        <a href="{cancel_href}" class="secondary"
           style="text-decoration:none;text-align:center;line-height:22px;">Annulla</a>
        <button type="submit" class="primary">Accedi</button>
      </div>
    </form>
    <p class="hint">In produzione questa pagina è sostituita dalla schermata
       di consenso Google reale. Lo state token è firmato HMAC-SHA256.</p>
  </div>
  <script>
    // Costruisce il `code` mock dall'email prima di inviare il form, così
    // l'endpoint /callback riceve la stessa forma `code=mock:<email>` che
    // userà il flow reale (code opaco di Google).
    document.querySelector('form').addEventListener('submit', function(ev) {{
      var email = document.getElementById('email').value.trim();
      document.getElementById('code-field').value = 'mock:' + email;
      document.getElementById('email').name = '';
    }});
  </script>
</body>
</html>
"""


@router.get("/_mock", response_class=HTMLResponse)
async def mock_consent(state: str = Query(min_length=1, max_length=1024)) -> HTMLResponse:
    if not oauth_service.is_simulate():
        raise AppError(
            "Mock OAuth disabilitato (client_id Google configurato).",
            code="oauth_mock_disabled",
            status_code=404,
        )
    # Valida lo state per evitare che la pagina venga aperta con state arbitrari
    oauth_service.verify_state(state)

    page = _MOCK_PAGE_TPL.format(
        state_attr=html.escape(urllib.parse.quote(state), quote=True),
        cancel_href="/login",
    )
    return HTMLResponse(content=page)
