"""Free, keyless research sources. Every result keeps its real URL.

- Hacker News (Algolia API): stories and comments where people describe problems.
- Stack Exchange API: questions on softwarerecs / webapps / freelancing / workplace etc.
- DuckDuckGo HTML results: existing products, competitors and their pricing pages.

If the network is down, the tools return nothing and every claim downstream
is labelled ASSUMPTION. Nothing is invented to fill the gap.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx

UA = "open-venture-builder/0.1 (+research bot; respects robots; low volume)"
CACHE_DIR = Path(os.getenv("RESEARCH_CACHE", "runs/cache"))
SE_SITES = ["softwarerecs", "webapps", "freelancing", "workplace", "ux", "superuser", "pm", "writers", "academia", "graphicdesign"]


@dataclass
class Source:
    id: str
    url: str
    title: str
    text: str
    origin: str
    engagement: int = 0
    date: str = ""
    query: str = ""
    meta: dict = field(default_factory=dict)

    def short(self, n: int = 400) -> str:
        return (self.text or "")[:n]


def _clean(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _cached_get(url: str, params: dict | None = None, timeout: float = 20) -> str | None:
    key = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    f = CACHE_DIR / f"{key}.txt"
    if f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
        return f.read_text(encoding="utf-8")
    for attempt in range(2):
        try:
            r = httpx.get(url, params=params, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
            if r.status_code == 200:
                f.write_text(r.text, encoding="utf-8")
                return r.text
            if r.status_code in (429, 503):
                time.sleep(2 + attempt * 3)
                continue
            return None
        except Exception:
            time.sleep(1)
    return None


def search_hn(query: str, n: int = 8) -> list[Source]:
    out = []
    for tags in ("comment", "story"):
        raw = _cached_get("https://hn.algolia.com/api/v1/search",
                          {"query": query, "tags": tags, "hitsPerPage": n})
        if not raw:
            continue
        try:
            hits = json.loads(raw).get("hits", [])
        except json.JSONDecodeError:
            continue
        for h in hits:
            text = _clean(h.get("comment_text") or h.get("story_text") or "")
            title = _clean(h.get("title") or h.get("story_title") or "")
            if not (text or title):
                continue
            out.append(Source(id="", url=f"https://news.ycombinator.com/item?id={h['objectID']}",
                              title=title or text[:80], text=text or title, origin="hackernews",
                              engagement=int(h.get("points") or 0) + int(h.get("num_comments") or 0),
                              date=(h.get("created_at") or "")[:10], query=query))
    return out


def search_stackexchange(query: str, sites: list[str] | None = None, n: int = 5) -> list[Source]:
    out = []
    for site in (sites or SE_SITES[:4]):
        raw = _cached_get("https://api.stackexchange.com/2.3/search/excerpts",
                          {"q": query, "site": site, "pagesize": n, "order": "desc", "sort": "relevance"})
        if not raw:
            continue
        try:
            items = json.loads(raw).get("items", [])
        except json.JSONDecodeError:
            continue
        for it in items:
            qid = it.get("question_id")
            if not qid:
                continue
            out.append(Source(id="", url=f"https://{site}.stackexchange.com/q/{qid}" if site not in ("superuser",) else f"https://superuser.com/q/{qid}",
                              title=_clean(it.get("title", "")), text=_clean(it.get("excerpt", "")), origin=f"stackexchange:{site}",
                              engagement=int(it.get("score") or 0) + int(it.get("answer_count") or 0),
                              date=time.strftime("%Y-%m-%d", time.gmtime(it.get("creation_date", 0))), query=query))
    return out


def search_web(query: str, n: int = 6) -> list[Source]:
    raw = _cached_get("https://html.duckduckgo.com/html/", {"q": query})
    if not raw:
        return []
    out = []
    blocks = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
                        raw, flags=re.S)
    for href, title, snippet in blocks:
        url = href
        if "uddg=" in href:
            url = unquote(parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query).get("uddg", [href])[0])
        if "duckduckgo.com/y.js" in url or not url.startswith("http"):
            continue  # skip ads
        out.append(Source(id="", url=url, title=_clean(title), text=_clean(snippet), origin="web", query=query))
        if len(out) >= n:
            break
    return out


def search_github(query: str, n: int = 5) -> list[Source]:
    """Existing open-source tools for the same job (competitors / alternatives)."""
    raw = _cached_get("https://api.github.com/search/repositories",
                      {"q": query, "sort": "stars", "order": "desc", "per_page": n})
    if not raw:
        return []
    try:
        items = json.loads(raw).get("items", [])
    except json.JSONDecodeError:
        return []
    return [Source(id="", url=it["html_url"], title=it.get("full_name", ""),
                   text=_clean(it.get("description") or ""), origin="github",
                   engagement=int(it.get("stargazers_count") or 0), date=(it.get("pushed_at") or "")[:10], query=query)
            for it in items if it.get("html_url")]


def search_show_hn(query: str, n: int = 6) -> list[Source]:
    """Products people launched for this problem ("Show HN" posts)."""
    raw = _cached_get("https://hn.algolia.com/api/v1/search", {"query": query, "tags": "show_hn", "hitsPerPage": n})
    if not raw:
        return []
    try:
        hits = json.loads(raw).get("hits", [])
    except json.JSONDecodeError:
        return []
    return [Source(id="", url=f"https://news.ycombinator.com/item?id={h['objectID']}", title=_clean(h.get("title", "")),
                   text=_clean(h.get("story_text") or h.get("title") or ""), origin="show_hn",
                   engagement=int(h.get("points") or 0) + int(h.get("num_comments") or 0),
                   date=(h.get("created_at") or "")[:10], query=query, meta={"product_url": h.get("url") or ""})
            for h in hits]


class SourceRegistry:
    """Numbers sources S1, S2... and lets agents cite only sources that exist."""

    def __init__(self):
        self.items: dict[str, Source] = {}
        self._urls: set[str] = set()

    def add_all(self, sources: list[Source]) -> list[Source]:
        added = []
        for s in sources:
            if s.url in self._urls:
                continue
            s.id = f"S{len(self.items) + 1}"
            self.items[s.id] = s
            self._urls.add(s.url)
            added.append(s)
        return added

    def get(self, sid: str) -> Source | None:
        return self.items.get(str(sid).strip().strip("[]"))

    def urls(self, ids) -> list[str]:
        return [self.items[i].url for i in ids if i in self.items]

    def to_list(self) -> list[dict]:
        return [asdict(s) for s in self.items.values()]


def quote_in_source(quote: str, source: Source, min_words: int = 4) -> bool:
    """True if the quote (or a long enough run of its words) really appears in the source text."""
    def norm(s):
        return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()
    q, t = norm(quote), " ".join(norm(source.text + " " + source.title))
    if len(q) < min_words:
        return False
    if " ".join(q) in t:
        return True
    win = max(min_words, min(8, len(q)))
    return any(" ".join(q[i:i + win]) in t for i in range(0, len(q) - win + 1))
