#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
BLOGCTL = Path(os.environ.get('BLOGCTL_PATH', ROOT / 'bin' / 'blogctl'))
STATE_FILE = Path(os.environ.get('NTFY_STATE_FILE', Path(os.environ.get('BLOG_STATE_DIR', ROOT / 'state')) / 'ntfy-last-id'))
MAX_ATTACHMENT_BYTES = int(os.environ.get('NTFY_MAX_ATTACHMENT_BYTES', str(5 * 1024 * 1024)))
POLL_INTERVAL = int(os.environ.get('NTFY_POLL_INTERVAL', '5'))
USER_AGENT = os.environ.get('NTFY_USER_AGENT', 'markdown-blog-ntfy-publisher/2.0')

BASE_URL = os.environ.get('NTFY_BASE_URL', '').rstrip('/')
TOPIC = os.environ.get('NTFY_TOPIC', '')
TOKEN = os.environ.get('NTFY_TOKEN', '')


def log(msg: str) -> None:
    print(time.strftime('%Y-%m-%d %H:%M:%S'), msg, flush=True)


def require_config() -> None:
    missing = [name for name, value in (
        ('NTFY_BASE_URL', BASE_URL),
        ('NTFY_TOPIC', TOPIC),
        ('NTFY_TOKEN', TOKEN),
    ) if not value]
    if missing:
        raise SystemExit('missing configuration: ' + ', '.join(missing))
    parsed = urlparse(BASE_URL)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise SystemExit('NTFY_BASE_URL must be an https URL')


def read_cursor() -> str:
    if STATE_FILE.exists():
        value = STATE_FILE.read_text(encoding='utf-8').strip()
        if value:
            return value
    value = str(int(time.time()))
    write_cursor(value)
    return value


def write_cursor(value: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(value + '\n', encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE_FILE)


def auth_request(url: str) -> Request:
    return Request(url, headers={
        'Authorization': f'Bearer {TOKEN}',
        'User-Agent': USER_AGENT,
        'Accept': 'application/x-ndjson, application/json, text/plain',
    })


def attachment_markdown(event: dict) -> str:
    attachment = event.get('attachment') or {}
    if not isinstance(attachment, dict):
        return ''
    name = str(attachment.get('name') or '').strip()
    url = str(attachment.get('url') or '').strip()
    if not name.lower().endswith(('.md', '.markdown')):
        return ''
    if not url:
        raise RuntimeError(f'markdown attachment {name!r} has no URL')

    target = urlparse(url)
    base = urlparse(BASE_URL)
    if target.scheme != 'https' or target.netloc != base.netloc or not target.path.startswith('/file/'):
        raise RuntimeError('attachment URL must be an ntfy-hosted HTTPS /file/ URL')

    declared_size = attachment.get('size')
    if isinstance(declared_size, int) and declared_size > MAX_ATTACHMENT_BYTES:
        raise RuntimeError(f'attachment too large: {declared_size} bytes')

    with urlopen(auth_request(url), timeout=30) as response:
        length = response.headers.get('Content-Length')
        if length and int(length) > MAX_ATTACHMENT_BYTES:
            raise RuntimeError(f'attachment too large: {length} bytes')
        data = response.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise RuntimeError('attachment exceeds 5 MiB limit')
    try:
        return data.decode('utf-8-sig').strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError('markdown attachment is not UTF-8') from exc


def message_body(event: dict) -> str:
    body = str(event.get('message') or '').strip()
    attachment = event.get('attachment') or {}
    if isinstance(attachment, dict):
        name = str(attachment.get('name') or '').strip()
        if name and body == f'You received a file: {name}':
            return ''
    return body


def strip_redundant_h1(title: str, content: str) -> str:
    """Remove the first Markdown H1 when it duplicates the ntfy Title.

    YAML front matter, when present, is preserved unchanged.
    """
    prefix = ''
    body = content

    if body.startswith('---\n'):
        end = body.find('\n---\n', 4)
        if end != -1:
            end += len('\n---\n')
            prefix = body[:end]
            body = body[end:]

    # Ignore blank lines between front matter and the first heading.
    leading_len = len(body) - len(body.lstrip('\r\n'))
    leading = body[:leading_len]
    rest = body[leading_len:]

    first_line, sep, remainder = rest.partition('\n')
    if first_line.endswith('\r'):
        first_line = first_line[:-1]

    if first_line.startswith('# ') and first_line[2:].strip() == title.strip():
        body = remainder.lstrip('\r\n') if sep else ''
        return prefix + ('\n' if prefix and body else '') + body

    return prefix + leading + rest


def build_content(event: dict, attached_override: str | None = None) -> tuple[str, str]:
    title = str(event.get('title') or '').strip()
    if not title:
        raise ValueError('message has no title; skipped')

    body = message_body(event)
    attached = attachment_markdown(event) if attached_override is None else attached_override.strip()
    if body and attached:
        content = body.rstrip() + '\n' + attached.lstrip()
    elif body:
        content = body
    elif attached:
        content = attached
    else:
        raise ValueError('message has neither body nor .md attachment; skipped')
    content = strip_redundant_h1(title, content)
    return title, content.rstrip() + '\n'


def publish_event(event: dict) -> None:
    title, content = build_content(event)
    proc = subprocess.run(
        [str(BLOGCTL), 'publish', '--stdin', '--title', title],
        input=content,
        text=True,
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or '').strip()
        raise RuntimeError(f'blog publish failed: {detail[:500]}')
    result = (proc.stdout or '').strip()
    log(f'published title={title!r}' + (f' ({result})' if result else ''))


def poll_once(cursor: str) -> tuple[str, int]:
    query = urlencode({'poll': '1', 'since': cursor})
    url = f"{BASE_URL}/{quote(TOPIC, safe='')}/json?{query}"
    processed = 0

    with urlopen(auth_request(url), timeout=30) as response:
        for raw in response:
            line = raw.decode('utf-8').strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get('event') != 'message':
                continue

            event_id = str(event.get('id') or '').strip()
            if not event_id or event_id == cursor:
                continue

            try:
                publish_event(event)
            except ValueError as exc:
                log(f'skipped id={event_id}: {exc}')
            # Advance only after success or an intentionally skipped invalid message.
            write_cursor(event_id)
            cursor = event_id
            processed += 1

    return cursor, processed


def main() -> None:
    require_config()
    cursor = read_cursor()
    log(f'polling topic={TOPIC!r} since={cursor!r} interval={POLL_INTERVAL}s')
    delay = 2

    while True:
        try:
            cursor, _ = poll_once(cursor)
            delay = 2
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            return
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError) as exc:
            log(f'poll/processing error: {type(exc).__name__}: {exc}')
            cursor = read_cursor()
            time.sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == '__main__':
    main()
