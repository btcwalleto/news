```python
import os
import json
import time
import hashlib
import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# NEWSKEYBAR - Breaking News Bot
# Token is stored in GitHub Actions Secrets.
BOT_TOKEN = os.environ.get("RUBIKA_TOKEN", "")
CHANNEL_ID = os.environ.get("RUBIKA_CHAT_ID", "@newskeybar")

CHECK_INTERVAL = 30 * 60
MAX_POSTS_PER_RUN = 3
STATE_FILE = "posted.json"

RSS_FEEDS = [
    "https://www.tasnimnews.com/fa/rss/feed/0/8/0/%D8%A2%D8%AE%D8%B1%DB%8C%D9%86-%D8%A7%D8%AE%D8%A8%D8%A7%D8%B1",
    "https://www.mehrnews.com/rss",
    "https://feeds.bbci.co.uk/persian/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
]

KEYWORDS = [
    "تنگه هرمز", "هرمز", "خلیج فارس", "ایران", "اسرائیل",
    "آمریکا", "حمله", "موشک", "جنگ", "درگیری", "تنش",
    "آتش‌بس", "حمله هوایی", "نفتکش", "کشتی", "تحریم",
    "انفجار", "هشدار امنیتی", "خاورمیانه", "فوری",
    "strait of hormuz", "iran", "israel", "middle east",
    "missile", "attack", "war", "ceasefire", "tanker",
]

URGENT_KEYWORDS = [
    "تنگه هرمز", "حمله", "موشک", "جنگ", "انفجار",
    "آتش‌بس", "حمله هوایی", "درگیری", "فوری",
    "strait of hormuz", "missile", "airstrike",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def fetch_url(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NEWSKEYBAR-NewsBot/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


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


def parse_feed(url):
    try:
        root = ET.fromstring(fetch_url(url))
        results = []

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (
                item.findtext("description") or ""
            ).strip()

            if not title or not link:
                continue

            results.append({
                "title": title,
                "link": link,
                "description": description[:700],
                "source": urllib.parse.urlparse(url).netloc,
            })

        # Support Atom feeds too.
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        if not results:
            for entry in root.findall(".//atom:entry", namespace):
                title = (
                    entry.findtext("atom:title", default="", namespaces=namespace)
                ).strip()
                link_element = entry.find("atom:link", namespace)
                link = (
                    link_element.get("href", "")
                    if link_element is not None else ""
                )
                summary = entry.findtext(
                    "atom:summary", default="", namespaces=namespace
                )

                if title and link:
                    results.append({
                        "title": title,
                        "link": link,
                        "description": summary[:700],
                        "source": urllib.parse.urlparse(url).netloc,
                    })

        return results
    except Exception as error:
        logging.warning("Could not read feed %s: %s", url, error)
        return []


def score_news(item):
    text = (item["title"] + " " + item["description"]).lower()
    matches = sum(1 for keyword in KEYWORDS if keyword.lower() in text)
    urgent_matches = sum(
        1 for keyword in URGENT_KEYWORDS if keyword.lower() in text
    )

    # A keyword alone is not enough to call a story urgent.
    if matches < 2:
        return 0

    return matches + urgent_matches * 2


def make_message(item):
    title = item["title"]
    description = item["description"]
    link = item["link"]
    urgent = any(
        keyword.lower() in (title + " " + description).lower()
        for keyword in URGENT_KEYWORDS
    )

    heading = "🚨 خبر فوری" if urgent else "📰 خبر مهم"

    message = (
        f"{heading}\n\n"
        f"🔴 {title}\n\n"
    )

    if description:
        message += f"{description}\n\n"

    message += (
        f"🔗 منبع خبر:\n{link}\n\n"
        f"📡 NEWSKEYBAR | اخبار مهم\n"
        f"🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )

    return message


def send_to_rubika(message):
    if not BOT_TOKEN:
        logging.error("RUBIKA_TOKEN secret is missing.")
        return False

    # Intentionally do not guess Rubika API endpoints or methods.
    # Connect the official, verified Rubika bot send-message method here.
    logging.error(
        "Sending is not configured yet. Verify the official Rubika "
        "Bot API method before enabling automatic publication."
    )
    return False


def run_once():
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
            item["score"] = score_news(item)

            if item["score"] >= 3:
                candidates[digest] = item

    ranked = sorted(
        candidates.values(),
        key=lambda item: item["score"],
        reverse=True,
    )

    if not ranked:
        logging.info("No sufficiently important new stories.")
        return

    sent_count = 0

    for item in ranked:
        if sent_count >= MAX_POSTS_PER_RUN:
            break

        message = make_message(item)

        if send_to_rubika(message):
            posted.add(item["digest"])
            sent_count += 1
            logging.info("Published: %s", item["title"])

    state["posted"] = list(posted)
    save_state(state)


if __name__ == "__main__":
    logging.info("NEWSKEYBAR bot starting.")

    while True:
        try:
            run_once()
        except Exception:
            logging.exception("Unexpected bot error.")

        time.sleep(CHECK_INTERVAL)
```
