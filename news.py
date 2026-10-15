```python
import os
import re
import json
import hashlib
import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape

BOT_TOKEN = os.environ.get("RUBIKA_TOKEN", "")
CHANNEL_ID = os.environ.get("RUBIKA_CHAT_ID", "@newskeybar")

STATE_FILE = "posted.json"
MAX_POSTS_PER_RUN = 3

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/persian/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.tasnimnews.com/fa/rss/feed/0/8/0",
    "https://www.mehrnews.com/rss",
]

KEYWORDS = [
    "تنگه هرمز", "خلیج فارس", "نفتکش", "ایران",
    "اسرائیل", "آمریکا", "حمله", "موشک", "جنگ",
    "درگیری", "آتش‌بس", "حمله هوایی", "انفجار",
    "تحریم", "خاورمیانه", "امنیت دریایی",
    "strait of hormuz", "iran", "israel",
    "middle east", "missile", "airstrike",
    "ceasefire", "tanker",
]

URGENT_KEYWORDS = [
    "تنگه هرمز", "حمله", "موشک", "انفجار",
    "آتش‌بس", "حمله هوایی", "درگیری",
    "strait of hormuz", "missile", "airstrike",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NEWSKEYBAR/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def clean_html(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(value).split())


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return {"posted": []}


def save_state(state):
    state["posted"] = state["posted"][-2000:]
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def parse_feed(feed_url):
    items = []

    try:
        root = ET.fromstring(fetch(feed_url))
        nodes = root.findall(".//item")

        for node in nodes:
            title = clean_html(node.findtext("title"))
            link = (node.findtext("link") or "").strip()
            description = clean_html(node.findtext("description"))

            if not title or not link:
                continue

            items.append({
                "title": title,
                "link": link,
                "description": description[:800],
                "source": urllib.parse.urlparse(feed_url).netloc,
            })

    except Exception as error:
        logging.warning("RSS error for %s: %s", feed_url, error)

    return items


def score(item):
    text = (item["title"] + " " + item["description"]).lower()

    matches = sum(
        1 for word in KEYWORDS if word.lower() in text
    )

    urgent_matches = sum(
        1 for word in URGENT_KEYWORDS if word.lower() in text
    )

    if matches < 2:
        return 0

    return matches + urgent_matches * 2


def send_message(text):
    if not BOT_TOKEN:
        raise RuntimeError("RUBIKA_TOKEN secret is missing")

    # Rubika Bot API sendMessage endpoint.
    url = f"https://botapi.rubika.ir/v3/{BOT_TOKEN}/sendMessage"

    payload = json.dumps({
        "chat_id": CHANNEL_ID,
        "text": text,
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    if result.get("status") not in ("OK", "ok", True, None):
        raise RuntimeError("Rubika API returned an unsuccessful response")

    if result.get("error"):
        raise RuntimeError("Rubika API returned an error")

    logging.info("Rubika API response received")
    return result


def build_message(item):
    text = (item["title"] + " " + item["description"]).lower()

    urgent = any(word.lower() in text for word in URGENT_KEYWORDS)
    heading = "🚨 خبر فوری" if urgent else "📰 خبر مهم"

    parts = [
        heading,
        "",
        "🔴 " + item["title"],
    ]

    if item["description"]:
        parts.extend(["", item["description"]])

    parts.extend([
        "",
        "🔗 لینک خبر:",
        item["link"],
        "",
        "📡 NEWSKEYBAR | اخبار مهم",
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    ])

    return "\n".join(parts)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Add RUBIKA_TOKEN in GitHub Actions Secrets")

    state = load_state()
    posted = set(state.get("posted", []))
    candidates = {}

    for feed in RSS_FEEDS:
        for item in parse_feed(feed):
            digest = hashlib.sha256(
                item["link"].encode("utf-8")
            ).hexdigest()

            if digest in posted:
                continue

            item["digest"] = digest
            item["score"] = score(item)

            if item["score"] >= 3:
                candidates[digest] = item

    ranked = sorted(
        candidates.values(),
        key=lambda item: item["score"],
        reverse=True,
    )

    if not ranked:
        logging.info("No important new stories. Nothing published.")
        return

    published = 0

    for item in ranked:
        if published >= MAX_POSTS_PER_RUN:
            break

        try:
            send_message(build_message(item))
            posted.add(item["digest"])
            published += 1
            logging.info("Published: %s", item["title"])

        except Exception:
            logging.exception("Could not publish: %s", item["title"])

    state["posted"] = list(posted)
    save_state(state)


if __name__ == "__main__":
    main()
```
