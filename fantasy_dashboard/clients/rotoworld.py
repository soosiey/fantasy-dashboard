import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse

import requests

from fantasy_dashboard.models.news import PlayerNewsModel


# Extract player-news cards from NBC Sports' server-rendered Rotoworld page.
class _PlayerNewsParser(HTMLParser):
    FIELD_CLASSES: ClassVar[dict[str, str]] = {
        "PlayerNewsPost-name-container": "player_name",
        "PlayerNewsPost-headline": "title",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: list[dict[str, str]] = []
        self._current_post: dict[str, str] | None = None
        self._captures = {field: 0 for field in self.FIELD_CLASSES.values()}
        self._elements: list[tuple[str, set[str], bool, bool]] = []
        self._inside_analysis = 0
        self._analysis_seen = False
        self._anchor_text = ""
        self._anchor_can_be_author = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        starts_post = "PlayerNewsPost" in classes

        if starts_post:
            self._current_post = {
                "player_name": "",
                "title": "",
                "date": "",
                "author": "",
                "source_url": "",
            }
            self._inside_analysis = 0
            self._analysis_seen = False
            self._anchor_text = ""
            self._anchor_can_be_author = False

        captured_fields: set[str] = set()
        if self._current_post is not None:
            for css_class, field in self.FIELD_CLASSES.items():
                if css_class in classes:
                    self._captures[field] += 1
                    captured_fields.add(field)

            if "PlayerNewsPost-date" in classes:
                self._current_post["date"] = attributes.get("data-date") or ""

            # The first NBC link in a card leads to that player's Rotoworld page.
            # Keep the UI on Rotoworld rather than forwarding to an external report.
            href = attributes.get("href")
            if tag == "a" and href:
                self._anchor_text = ""
                candidate_url = urljoin(RotoworldClient.PLAYER_NEWS_URL, href)
                candidate_host = (urlparse(candidate_url).hostname or "").casefold()
                is_rotoworld_link = candidate_host == "nbcsports.com" or (
                    candidate_host.endswith(".nbcsports.com")
                )
                self._anchor_can_be_author = self._analysis_seen and is_rotoworld_link
                if (
                    not self._analysis_seen
                    and not self._current_post["source_url"]
                    and is_rotoworld_link
                ):
                    self._current_post["source_url"] = candidate_url

        is_analysis = "PlayerNewsPost-analysis" in classes
        if is_analysis:
            self._inside_analysis += 1

        self._elements.append((tag, captured_fields, starts_post, is_analysis))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._current_post is None:
            return

        for field, depth in self._captures.items():
            if depth:
                self._current_post[field] += f" {data}"
        if self._anchor_can_be_author:
            self._anchor_text += f" {data}"

    def handle_endtag(self, tag: str) -> None:
        if (
            tag == "a"
            and self._current_post is not None
            and self._anchor_can_be_author
            and not self._current_post["author"]
        ):
            self._current_post["author"] = " ".join(self._anchor_text.split())
        if tag == "a":
            self._anchor_text = ""
            self._anchor_can_be_author = False

        # Unwind through the matching element so mildly malformed HTML is tolerated.
        while self._elements:
            open_tag, captured_fields, starts_post, is_analysis = self._elements.pop()
            for field in captured_fields:
                self._captures[field] -= 1
            if is_analysis:
                self._inside_analysis -= 1
                self._analysis_seen = self._inside_analysis == 0

            if starts_post and self._current_post is not None:
                post = {
                    field: " ".join(value.split())
                    for field, value in self._current_post.items()
                }
                if post["player_name"] and post["title"]:
                    self.posts.append(post)
                self._current_post = None

            if open_tag == tag:
                break


# Fetch matching cards while limiting requests across NBC's paginated feed.
class RotoworldClient:
    PLAYER_NEWS_URL = "https://www.nbcsports.com/fantasy/football/player-news"

    def __init__(
        self,
        timeout: float = 10.0,
        max_pages: int = 10,
        max_news_age: timedelta = timedelta(days=7),
    ) -> None:
        self.timeout = timeout
        self.max_pages = max_pages
        self.max_news_age = max_news_age

    @staticmethod
    def _normalize_name(player_name: str) -> str:
        words = re.findall(r"[a-z0-9]+", player_name.casefold())
        if words and words[-1] in {"jr", "sr", "ii", "iii", "iv", "v"}:
            words.pop()
        return " ".join(words)

    def _is_recent(self, news_date: str) -> bool:
        if not news_date:
            return False

        try:
            published_at = datetime.fromisoformat(news_date.replace("Z", "+00:00"))
        except ValueError:
            return False

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - published_at
        return timedelta(0) <= age <= self.max_news_age

    def get_recent_news(
        self, rotoworld_id: int, player_name: str
    ) -> list[PlayerNewsModel]:
        if not player_name.strip():
            return []

        target_name = self._normalize_name(player_name)
        news_items: list[PlayerNewsModel] = []
        seen_items: set[tuple[str, str]] = set()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; FantasyDashboard/1.0; "
                "+https://www.nbcsports.com/fantasy/football/player-news)"
            )
        }

        # NBC no longer publishes legacy IDs, so missing IDs fall back to names.
        for page in range(1, self.max_pages + 1):
            params: dict[str, Any] = {
                "f3": "",
                "f0": "All News",
                "f1": "Positions",
            }
            if page > 1:
                params["p"] = page
            response = requests.get(
                self.PLAYER_NEWS_URL,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()

            parser = _PlayerNewsParser()
            parser.feed(response.text)
            for post in parser.posts:
                if self._normalize_name(post["player_name"]) != target_name:
                    continue
                if not self._is_recent(post["date"]):
                    continue

                item_key = (post["title"], post["date"])
                if item_key in seen_items:
                    continue
                seen_items.add(item_key)
                news_items.append(
                    PlayerNewsModel(
                        title=post["title"],
                        date=post["date"],
                        author=post["author"],
                        source_url=(
                            post["source_url"] or self.PLAYER_NEWS_URL
                        ),
                    )
                )

            if not parser.posts:
                break

        return news_items
