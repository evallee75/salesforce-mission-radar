"""Email récapitulatif des nouvelles missions (optionnel).

N'envoie rien si SMTP_PASSWORD est absent : le scan et le site fonctionnent sans.
Variables (secrets GitHub Actions) : SMTP_USER, SMTP_PASSWORD (mot de passe
d'application Gmail), ALERT_TO (défaut = SMTP_USER), SMTP_HOST, SMTP_PORT,
DIGEST_MIN_SCORE (défaut 40 : on n'envoie que ce qui vaut le coup).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape
from typing import Dict, List

from .feed import format_rate

log = logging.getLogger("radar.digest")


def send_digest(offers: List[Dict], new_ids, site_url: str) -> None:
    password = os.environ.get("SMTP_PASSWORD")
    if not password:
        log.info("Pas de SMTP_PASSWORD : email non envoyé.")
        return
    min_score = int(os.environ.get("DIGEST_MIN_SCORE", "40"))
    fresh = [o for o in offers if o["id"] in new_ids and o["score"] >= min_score]
    if not fresh:
        log.info("Aucune nouvelle mission au-dessus de %d : pas d'email.", min_score)
        return
    # Même ordre que le site : du plus récent au plus ancien.
    fresh.sort(key=lambda o: (o.get("posted_at") or o["first_seen"], o["score"]), reverse=True)
    user = os.environ["SMTP_USER"]
    msg = MIMEText(_html(fresh, site_url), "html", "utf-8")
    short = sum(1 for o in fresh if o.get("short") or o.get("part_time"))
    msg["Subject"] = f"🎯 {len(fresh)} mission(s) Salesforce dont {short} courte(s)/partielle(s)"
    msg["From"] = formataddr(("Salesforce Mission Radar", user))
    msg["To"] = os.environ.get("ALERT_TO") or user
    with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"),
                      int(os.environ.get("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    log.info("Email envoyé : %d mission(s).", len(fresh))


def _html(offers: List[Dict], site_url: str) -> str:
    rows = []
    for o in offers[:40]:
        tags = [t for t in (
            "⚡ courte" if o.get("short") else "", o.get("part_time") or "",
            f"🌍 {o.get('country')}" if o.get("zone") in ("Europe", "Monde") else "",
            format_rate(o), "client final" if o.get("client_final") else "") if t]
        meta = " · ".join(x for x in (o.get("company"), o.get("location"), o["source"]) if x)
        rows.append(
            f'<tr><td style="padding:12px 0;border-bottom:1px solid #eee">'
            f'<span style="background:#0369a1;color:#fff;border-radius:10px;padding:2px 8px;'
            f'font-size:12px;font-weight:700">{o["score"]}</span> '
            f'<a href="{escape(o["url"])}" style="font-size:15px;font-weight:700;color:#111827;'
            f'text-decoration:none">{escape(o["title"])}</a><br>'
            f'<span style="font-size:13px;color:#6b7280">{escape(meta)}</span><br>'
            f'<span style="font-size:13px;color:#0369a1">{escape(" · ".join(tags))}</span></td></tr>')
    link = f'<p><a href="{escape(site_url)}">Ouvrir le radar →</a></p>' if site_url else ""
    return (f'<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:auto">'
            f'<h2 style="color:#0369a1">{len(offers)} nouvelle(s) mission(s) Salesforce</h2>'
            f'{link}<table style="width:100%;border-collapse:collapse">{"".join(rows)}</table>{link}</div>')
