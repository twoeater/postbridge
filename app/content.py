from __future__ import annotations

import markdown
import nh3
from markdown.extensions.tables import TableExtension

# Keep safe data: images because Postbridge intentionally supports inline/base64
# images, but never allow data: URLs on links or other elements. SVG is excluded
# because it can carry active content in some browser contexts.
_ALLOWED_DATA_IMAGE_PREFIXES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/gif;base64,",
    "data:image/webp;base64,",
    "data:image/avif;base64,",
)


def _attribute_filter(tag: str, attribute: str, value: str) -> str | None:
    normalized = value.lstrip().lower()
    if normalized.startswith("data:"):
        if tag == "img" and attribute == "src" and normalized.startswith(_ALLOWED_DATA_IMAGE_PREFIXES):
            return value
        return None
    return value


_HTML_CLEANER = nh3.Cleaner(
    # nh3's defaults intentionally reject data:. Add it to the URL-scheme
    # parser, then constrain it to safe raster image sources above.
    url_schemes=set(nh3.ALLOWED_URL_SCHEMES) | {"data"},
    attribute_filter=_attribute_filter,
    link_rel="noopener noreferrer",
)


def sanitize_html(value: str) -> str:
    """Return allowlist-sanitized HTML safe to render as trusted markup."""
    return _HTML_CLEANER.clean(value)


def render_markdown(body: str) -> str:
    """Render Markdown and sanitize the generated HTML before persistence."""
    rendered = markdown.markdown(
        body,
        extensions=[
            "fenced_code",
            TableExtension(use_align_attribute=True),
            "sane_lists",
            "nl2br",
        ],
    )
    return sanitize_html(rendered)
