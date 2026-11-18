"""Blog text helpers: safe Markdown rendering and the publish SEO checklist.

Google does not expose an official pass/fail API. These checks are a practical
best-practice gate: required checks protect the basics that help a page get
indexed and read cleanly, while advisory checks surface improvements without
blocking the master account.
"""

from __future__ import annotations

import re

import bleach
from markdown_it import MarkdownIt

from .models import BlogPost

_MARKDOWN = MarkdownIt("commonmark", {"html": False, "breaks": True})
_MARKDOWN.enable(["table", "strikethrough"])

ALLOWED_TAGS = [
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "s", "del", "code", "pre",
    "blockquote", "ul", "ol", "li",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "loading", "width", "height"],
    "code": ["class"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_FENCE_RE = re.compile(r"```.*?```", re.S)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_MARK_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)
_LIST_MARK_RE = re.compile(r"^\s*[-*+]\s+", re.M)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_H2_RE = re.compile(r"^\s{0,3}##\s+\S", re.M)
_H2_HTML_RE = re.compile(r"<h2\b", re.I)
_FAQ_RE = re.compile(r"(?:^|\n)\s*#{2,3}\s*(?:faq|frequently asked questions)\b", re.I)
_BARE_URL_RE = re.compile(r"https?://[^\s<]+", re.I)
_LINK_COUNT_RE = re.compile(r"\[[^\]]+\]\([^)]+\)|https?://[^\s<]+", re.I)
_REPEATED_CHAR_RE = re.compile(r"(.)\1{9,}")
_UNSAFE_MARKDOWN_LINK_RE = re.compile(
    r"!?\[([^\]]*)\]\(\s*(?:javascript|data|vbscript|file):[^)]*\)",
    re.I,
)
_UNSAFE_BARE_URL_RE = re.compile(
    r"\b(?:javascript|data|vbscript|file):[^\s<>)\]]*",
    re.I,
)
_SPAM_PHRASES = (
    "viagra", "cialis", "casino", "crypto giveaway", "free followers",
    "buy backlinks", "seo service", "whatsapp me", "telegram me",
)


def _clean_html(html):
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def _add_image_loading(html):
    def replace(match):
        tag = match.group(0)
        if "loading=" in tag.lower():
            return tag
        return tag[:-1] + ' loading="lazy">'

    return re.sub(r"<img\b[^>]*>", replace, html, flags=re.I)


def _nofollow_links(html):
    def replace(match):
        tag = match.group(0)
        tag = re.sub(r'\s+rel="[^"]*"', "", tag, flags=re.I)
        return tag[:-1] + ' rel="nofollow noopener">'

    return re.sub(r"<a\b[^>]*>", replace, html, flags=re.I)


def _remove_unsafe_links(value, *, include_bare_urls=False):
    """Drop unsafe Markdown destinations before Markdown sees them.

    ``markdown-it`` and Bleach both refuse to emit an unsafe ``href``, but an
    unsupported link destination is left as literal Markdown text. Removing it
    up front keeps source-like strings such as ``javascript:`` out of public
    HTML altogether.
    """

    value = _UNSAFE_MARKDOWN_LINK_RE.sub(r"\1", value or "")
    if include_bare_urls:
        value = _UNSAFE_BARE_URL_RE.sub("", value)
    return value


def render_blog_markdown(value):
    """Render Markdown to a strict HTML allowlist for article bodies."""

    safe_value = _remove_unsafe_links(value)
    return _add_image_loading(_clean_html(_MARKDOWN.render(safe_value))).strip()


def render_comment(value):
    """Render a comment as plain Markdown with every link marked nofollow."""

    safe_value = _remove_unsafe_links(value, include_bare_urls=True)
    return _nofollow_links(_clean_html(_MARKDOWN.render(safe_value))).strip()


def plain_text(value):
    """Reduce Markdown to readable text for word counts and keyword checks."""

    text = _FENCE_RE.sub(" ", value or "")
    text = _IMAGE_RE.sub(" ", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _HEADING_MARK_RE.sub("", text)
    text = _LIST_MARK_RE.sub("", text)
    text = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def word_count(value):
    return len(plain_text(value).split())


def _first_paragraph(value):
    for block in re.split(r"\n\s*\n", (value or "").strip()):
        block = block.strip()
        if not block or block.startswith("#") or block.startswith("```"):
            continue
        return plain_text(block)
    return ""


def _link_targets(value):
    return [target.strip() for _label, target in _LINK_RE.findall(value or "")]


def _check(label, passed, detail, required=True):
    return {
        "label": label,
        "passed": bool(passed),
        "required": bool(required),
        "detail": detail,
    }


def _normalise_keyword(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def evaluate_seo(data, exclude_pk=None):
    """Return the master-visible SEO report for a draft or saved post.

    ``data`` may come from a bound form or from a model instance. Unique checks
    use the database so the same rule applies before and after saving.
    """

    title = (data.get("title") or "").strip()
    slug = (data.get("slug") or "").strip()
    body = data.get("body") or ""
    excerpt = (data.get("excerpt") or "").strip()
    keyword = (data.get("focus_keyword") or "").strip()
    seo_title = (data.get("seo_title") or "").strip() or title
    description = (data.get("meta_description") or "").strip() or excerpt
    featured_image = bool(data.get("featured_image"))
    alt_text = (data.get("featured_image_alt") or "").strip()

    title_len = len(seo_title)
    description_len = len(description)
    words = word_count(body)
    first_paragraph = _first_paragraph(body)
    keyword_lower = keyword.lower()
    keyword_haystack = _normalise_keyword(keyword)
    slug_haystack = _normalise_keyword(slug)
    text = plain_text(body)
    text_lower = text.lower()

    title_exists = bool(
        title
        and BlogPost.objects.filter(title__iexact=title)
        .exclude(pk=exclude_pk)
        .exists()
    )
    slug_exists = bool(
        slug
        and BlogPost.objects.filter(slug__iexact=slug)
        .exclude(pk=exclude_pk)
        .exists()
    )

    h2_count = len(_H2_RE.findall(body)) + len(_H2_HTML_RE.findall(body))
    targets = _link_targets(body)
    internal_targets = [
        target for target in targets
        if target.startswith("/") and not target.startswith("//")
    ]
    useful_internal = [
        target for target in internal_targets
        if target.startswith("/services")
        or target.startswith("/tools")
        or target.startswith("/blog")
    ]
    phrase_count = (
        text_lower.count(keyword_lower)
        if keyword_lower and " " in keyword_lower
        else len(re.findall(rf"\b{re.escape(keyword_lower)}\b", text_lower))
        if keyword_lower
        else 0
    )
    stuffing_limit = max(6, int(words * 0.03))
    stuffing_rate = round((phrase_count / words) * 100, 1) if words else 0.0

    hard = [
        _check(
            "Unique title and web address",
            not title_exists and not slug_exists,
            "The title and slug must not already belong to another post."
            if title_exists or slug_exists
            else "No duplicate title or slug found.",
        ),
        _check(
            "SEO title is 30–60 characters",
            30 <= title_len <= 60,
            f"Current title is {title_len} characters. Add the SEO title field if the post title is longer.",
        ),
        _check(
            "Meta description is 120–160 characters",
            120 <= description_len <= 160,
            f"Current description is {description_len} characters. The excerpt is used when the field is blank.",
        ),
        _check(
            "Focus keyword is set",
            bool(keyword),
            "Add the main phrase a customer would search for."
            if not keyword
            else f"Focus keyword: {keyword}.",
        ),
        _check(
            "Keyword appears in title, slug and first paragraph",
            bool(keyword) and keyword_lower in seo_title.lower()
            and bool(keyword_haystack) and keyword_haystack in slug_haystack
            and bool(keyword_lower) and keyword_lower in first_paragraph.lower(),
            "Use the phrase in the SEO title, web address and opening paragraph.",
        ),
        _check(
            "At least 300 words",
            words >= 300,
            f"The article currently reads as {words} words.",
        ),
        _check(
            "At least one H2 subheading",
            h2_count >= 1,
            f"Found {h2_count} H2 subheading(s). Use ## in Markdown.",
        ),
        _check(
            "Links to a service, tool or blog page",
            bool(useful_internal),
            "Add at least one relative link such as /services/collision/ or /tools/mpi-claim-navigator/.",
        ),
        _check(
            "Featured image has alt text",
            not featured_image or bool(alt_text),
            "Describe the image for screen readers and image search."
            if featured_image
            else "No image uploaded, so alt text is not required.",
        ),
        _check(
            "Focus keyword is not stuffed",
            not keyword or phrase_count <= stuffing_limit,
            f"The phrase appears {phrase_count} times in {words} words ({stuffing_rate}%). "
            f"Keep it at or below {stuffing_limit} mentions.",
        ),
    ]

    long_paragraphs = 0
    for block in re.split(r"\n\s*\n", body):
        block_text = plain_text(block)
        if len(block_text.split()) > 120:
            long_paragraphs += 1

    has_external = any(
        url.startswith(("http://", "https://"))
        and not url.startswith(("https://mapleleafauto.ca", "http://mapleleafauto.ca"))
        for url in _BARE_URL_RE.findall(body)
    )

    warnings = [
        _check(
            "Featured image added",
            featured_image,
            "An original image helps the article stand up in search and social sharing.",
            required=False,
        ),
        _check(
            "FAQ or questions section",
            bool(_FAQ_RE.search(body)),
            "A short FAQ can earn extra search visibility.",
            required=False,
        ),
        _check(
            "Short paragraphs",
            long_paragraphs == 0,
            f"{long_paragraphs} paragraph(s) run over 120 words."
            if long_paragraphs
            else "Paragraph length reads well.",
            required=False,
        ),
        _check(
            "External authoritative citation",
            has_external,
            "Where useful, link to MPI, Transport Canada or another primary source.",
            required=False,
        ),
    ]

    passed = all(check["passed"] for check in hard)
    return {
        "hard": hard,
        "warnings": warnings,
        "passed": passed,
        "hard_failures": [check for check in hard if not check["passed"]],
        "advisories": [check for check in warnings if not check["passed"]],
        "word_count": words,
        "keyword_uses": phrase_count,
        "keyword_density": stuffing_rate,
    }


def post_seo_data(post):
    """Build the checklist input dictionary from a saved post."""

    return {
        "pk": post.pk,
        "title": post.title,
        "slug": post.slug,
        "excerpt": post.excerpt,
        "body": post.body,
        "focus_keyword": post.focus_keyword,
        "seo_title": post.seo_title,
        "meta_description": post.meta_description,
        "featured_image": bool(post.featured_image),
        "featured_image_alt": post.featured_image_alt,
    }
