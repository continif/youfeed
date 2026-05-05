"""Test smoke: i template email si renderizzano senza errori."""

from __future__ import annotations

import pytest


def test_verify_email_renders() -> None:
    from app.services.email_service import render_template

    html, text = render_template(
        "verify_email",
        username="luca",
        link="https://www.youfeed.it/verify-email?token=abc123",
        site_name="YouFeed",
    )
    assert "luca" in html
    assert "abc123" in html
    assert "luca" in text
    assert "abc123" in text
    assert "<a" in html
    # Il fallback text deve essere effettivamente plain (no tag)
    assert "<" not in text


def test_reset_password_renders() -> None:
    from app.services.email_service import render_template

    html, text = render_template(
        "reset_password",
        username="anna",
        link="https://www.youfeed.it/reset-password?token=xyz",
        site_name="YouFeed",
    )
    assert "anna" in html
    assert "xyz" in html
    assert "anna" in text


def test_unknown_template_raises() -> None:
    from app.services.email_service import render_template
    from jinja2 import TemplateNotFound

    with pytest.raises(TemplateNotFound):
        render_template("does_not_exist", foo="bar")
