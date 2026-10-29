import calendar
import datetime as dt
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

def norm(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())

def keytext(value):
    return ''.join((c for c in norm(value) if c.isalnum()))

def require_text(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label} 必须为非空字符串，最长 {limit} 字符')
    return value.strip()

def url_syntax(url):
    require_text(url, 'URL', 4000)
    p = urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('仅接受不含账号密码的 HTTP(S) URL')
    if any((ord(c) < 33 for c in url)):
        raise ValueError('URL 不可包含空白或控制字符')
    return url
