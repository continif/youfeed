"""Pattern di path tipici degli scanner di vulnerabilità.

Se una richiesta non-autenticata hit uno di questi path, l'IP viene
auto-bannato per 24h dal TrafficBlockMiddleware. Sono i path che gli
scanner tirano a campione sperando di trovare CMS/dashboard esposti.

Lista hardcoded perché:
  - cambia di rado (sono target stabili da 15+ anni)
  - non vogliamo che venga svuotata per sbaglio dall'admin
  - 30 voci sono leggibili a colpo d'occhio

Per personalizzare in futuro: spostare in un YAML caricato a boot, oppure
aggiungere una tabella admin-editabile (`blocked_paths`) accanto a quelle
country/asn/ip/ua. Per ora copre il 90% del rumore.
"""

from __future__ import annotations

import re


# Pattern aderenti a substring nell'URL path. Niente regex complicate per
# evitare ReDoS e per leggibilità. Il match è case-insensitive.
SCANNER_PATH_SUBSTRINGS: tuple[str, ...] = (
    # File di configurazione lasciati esposti
    "/.env",
    "/.git/",
    "/.git/config",
    "/.svn/",
    "/.hg/",
    "/.DS_Store",
    "/.well-known/security.txt",   # i bot legittimi vanno bene, ma è frequente probing
    "/composer.json",
    "/composer.lock",
    # WordPress (siamo una webapp Vue, non WP)
    "/wp-login.php",
    "/wp-admin",
    "/wp-content",
    "/wp-includes",
    "/xmlrpc.php",
    "/wordpress/",
    "/wp-json",
    # phpMyAdmin / database UI
    "/phpmyadmin",
    "/pma/",
    "/myadmin/",
    "/adminer",
    "/dbadmin",
    # Pannelli generici di admin/CMS
    "/administrator/",   # Joomla
    "/admin.php",
    "/manager/html",     # Tomcat
    "/console",
    "/phpinfo.php",
    # Java/Spring sniff
    "/actuator/",
    "/jolokia/",
    # CGI / shell exposed
    "/cgi-bin/",
    "/shell.php",
    "/cmd.php",
    # Backup / dump files
    "/backup.sql",
    "/dump.sql",
    "/database.sql",
    "/.bak",
    # AWS/cloud metadata SSRF probing
    "/latest/meta-data/",
    "/_profiler/",
    # PHP che non gira sul nostro stack
    "/index.php",
    "/info.php",
    "/test.php",
)


def _build_pattern() -> re.Pattern[str]:
    # OR di tutte le substringhe ben quotate. Case-insensitive.
    parts = [re.escape(s) for s in SCANNER_PATH_SUBSTRINGS]
    return re.compile("|".join(parts), re.IGNORECASE)


_PATTERN = _build_pattern()


def is_scanner_path(path: str) -> bool:
    """True se il path richiesto matcha uno dei pattern noti."""
    if not path:
        return False
    return _PATTERN.search(path) is not None
