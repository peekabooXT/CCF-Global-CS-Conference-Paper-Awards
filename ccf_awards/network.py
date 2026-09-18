"""Bounded public-page fetcher. No login, cookies, browser, or private-network crawling."""
import io
import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from .model import now, url_syntax

USER_AGENT = "CCFAwardsAgent/0.1"
MAX_BYTES = 8 * 1024 * 1024


def public_url(url):
    url_syntax(url)
    host = urlsplit(url).hostname
    try:
        addresses = socket.getaddrinfo(host, urlsplit(url).port or (443 if url.startswith("https:") else 80))
    except OSError as exc:
        raise ValueError("域名解析失败") from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("采集器仅访问公共互联网地址")
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("LLM API 返回重定向，已停止；请配置最终的 HTTPS API 地址")


def get_bytes(url):
    public_url(url)
    opener = urllib.request.build_opener(SafeRedirect())
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
            with opener.open(req, timeout=25) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("网页/PDF 超过 8 MiB，请提供更小的来源")
                return data, response.headers.get_content_type(), response.headers.get_content_charset() or "utf-8", response.url
        except urllib.error.HTTPError as exc:
            if attempt < 2 and (exc.code == 429 or 500 <= exc.code < 600):
                time.sleep(1 + attempt)
                continue
            raise


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.hidden, self.anchor = [], [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1
        if self.hidden:
            return
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.anchor = [attrs["href"], ""]
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self.hidden:
            self.hidden -= 1
        if tag == "a" and self.anchor:
            self.links.append(tuple(self.anchor))
            self.anchor = None
        if not self.hidden and tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.anchor:
                self.anchor[1] += data


def decode_document(data, mime, charset, url, pdf_page_limit=None):
    links = []
    if "pdf" in mime or data.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("读取 PDF 需先运行 python -m pip install -r requirements-pdf.txt") from exc
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > 200:
            raise ValueError("PDF 超过 200 页，请提供单篇论文")
        pages = reader.pages[:pdf_page_limit] if pdf_page_limit else reader.pages
        text = "\n".join(page.extract_text() or "" for page in pages)
    else:
        try:
            raw = data.decode(charset, errors="replace")
        except LookupError:
            raw = data.decode("utf-8", errors="replace")
        if "html" in mime or "<html" in raw[:500].lower():
            parser = PageText()
            parser.feed(raw)
            text = "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())
            for href, label in parser.links:
                absolute = urldefrag(urljoin(url, href))[0]
                if urlsplit(absolute).scheme in ("http", "https"):
                    links.append({"url": absolute, "label": " ".join(label.split())})
            text += "\n\n[页面真实链接]\n" + "\n".join(x["label"] + " : " + x["url"] for x in links)
        elif mime.startswith("text/"):
            text = raw
        else:
            raise ValueError("仅支持 HTML、纯文本和可提取文本的 PDF")
    if len(text.strip()) < 15:
        raise ValueError("未读到足够的正文；可能是扫描 PDF 或动态网页，请手动导出文本")
    return text, links


class Fetcher:
    def __init__(self):
        self.robots = {}
        self.last_at = 0.0

    def allowed(self, url):
        p = urlsplit(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self.robots:
            robot = urllib.robotparser.RobotFileParser()
            try:
                data, _, charset, _ = get_bytes(root + "/robots.txt")
                robot.parse(data.decode(charset, errors="replace").splitlines())
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 410):
                    robot.parse([])
                else:
                    raise ValueError(f"无法确认 robots.txt（HTTP {exc.code}），请改用手动文本") from exc
            self.robots[root] = robot
        if not self.robots[root].can_fetch(USER_AGENT, url):
            raise ValueError("网站 robots.txt 不允许采集该页面，请使用获准的来源")

    def fetch(self, url, sid, role):
        self.allowed(url)
        time.sleep(max(0, 1 - (time.monotonic() - self.last_at)))
        self.last_at = time.monotonic()
        data, mime, charset, final_url = get_bytes(url)
        if final_url != url:
            self.allowed(final_url)
        text, links = decode_document(data, mime, charset, final_url, 3 if role == "metadata" else None)
        return dict(id=sid, url=final_url, requested_url=url, role=role, text=text,
                    mime=mime, retrieved_at=now(), acquisition="http",
                    extraction_scope="PDF first 3 pages for author metadata" if role == "metadata" and ("pdf" in mime or data.startswith(b"%PDF")) else "full document"), links


def crawl(seed_urls, extra_urls=(), max_pages=4, notify=lambda _: None, strict_seeds=True):
    if not 1 <= max_pages <= 20:
        raise ValueError("max-pages 应在 1–20 之间")
    if len(seed_urls) + len(extra_urls) > max_pages:
        raise ValueError("显式 URL 数量超过 max-pages，请增大上限")
    fetcher, sources, errors, visited = Fetcher(), [], [], set()
    queue = [(u, "award", strict_seeds) for u in seed_urls] + [(u, "metadata", True) for u in extra_urls]
    attempts = 0
    while queue and attempts < max_pages:
        url, role, required = queue.pop(0)
        url = urldefrag(url)[0]
        if url in visited:
            continue
        visited.add(url)
        attempts += 1
        notify(f"读取 {url}")
        try:
            source, links = fetcher.fetch(url, f"s{len(sources)+1}", role)
            sources.append(source)
            if role == "award":
                for link in links:
                    hay = (link["url"] + " " + link["label"]).casefold()
                    if urlsplit(link["url"]).netloc == urlsplit(source["url"]).netloc and any(
                            word in hay for word in ("award", "best-paper", "best_paper", "获奖", "最佳论文")):
                        queue.append((link["url"], "award", False))
        except Exception as exc:
            errors.append(dict(url=url, error=str(exc), required=required))
    if not sources or not any(s["role"] == "award" for s in sources):
        raise ValueError("未取得任何获奖来源：" + json.dumps(errors, ensure_ascii=False))
    if any(e["required"] for e in errors):
        raise ValueError("指定来源读取失败，请修正后重试：" + json.dumps(errors, ensure_ascii=False))
    return sources, errors


def read_local_source(path, source_url, role="award", sid="s1"):
    url_syntax(source_url)
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("本地来源超过 8 MiB")
    mime = "application/pdf" if path.suffix.lower() == ".pdf" else "text/html" if path.suffix.lower() in (".html", ".htm") else "text/plain"
    text, _ = decode_document(path.read_bytes(), mime, "utf-8", source_url, 3 if role == "metadata" else None)
    return dict(id=sid, url=source_url, role=role, text=text, retrieved_at=now(), acquisition="local_user_file",
                extraction_scope="PDF first 3 pages for author metadata" if role == "metadata" and mime == "application/pdf" else "full document")
