"""Flux RSS des nouvelles missions : s'abonner dans n'importe quel lecteur RSS
(Feedly, Inoreader, Thunderbird, Slack /feed…) pour être alerté sans email."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from email.utils import format_datetime
from typing import Callable, Dict, List
from xml.sax.saxutils import escape

_DAYS = 7
_MAX_ITEMS = 150


def offer_headline(o: Dict) -> str:
    tags = []
    if o.get("short"):
        tags.append("⚡ Courte")
    if o.get("part_time"):
        tags.append(f"⏱ {o['part_time']}")
    if o.get("zone") in ("Europe", "Monde"):
        tags.append(f"🌍 {o.get('country')}")
    rate = format_rate(o)
    head = f"[{' · '.join(tags)}] " if tags else ""
    tail = " — ".join(x for x in (o.get("company"), rate) if x)
    return f"{head}{o['title']}" + (f" — {tail}" if tail else "")


def format_rate(o: Dict) -> str:
    lo, hi = o.get("tjm_min"), o.get("tjm_max")
    if lo and hi and lo != hi:
        return f"{lo}–{hi} €/j"
    if lo or hi:
        return f"{hi or lo} €/j"
    return o.get("budget") or ""


def write_feed(path: str, offers: List[Dict], site_url: str, title: str,
               keep: Callable[[Dict], bool]) -> None:
    cutoff = (date.today() - timedelta(days=_DAYS)).isoformat()
    items = [o for o in offers if o.get("active") and o["first_seen"] >= cutoff and keep(o)]
    items.sort(key=lambda o: (o["first_seen"], o["score"]), reverse=True)
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        f"<title>{escape(title)}</title>",
        f"<link>{escape(site_url)}</link>",
        "<description>Missions freelance Salesforce agrégées chaque jour.</description>",
        "<language>fr</language>",
    ]
    for o in items[:_MAX_ITEMS]:
        seen = datetime.combine(date.fromisoformat(o["first_seen"][:10]), time(6), tzinfo=timezone.utc)
        desc = f"Score {o['score']}/100 · {o.get('location') or o.get('zone')} · {o['source']}"
        if o.get("snippet"):
            desc += f"<br/><br/>{escape(o['snippet'])}"
        xml += [
            "<item>",
            f"<title>{escape(offer_headline(o))}</title>",
            f"<link>{escape(o['url'])}</link>",
            f'<guid isPermaLink="false">{escape(o["id"])}</guid>',
            f"<pubDate>{format_datetime(seen)}</pubDate>",
            f"<description>{escape(desc)}</description>",
            "</item>",
        ]
    xml.append("</channel></rss>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml))
