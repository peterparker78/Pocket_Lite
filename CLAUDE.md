# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pocket Lite is a distraction-free reading web app. Users paste a URL, and the app extracts and displays the main article text without ads or navigation clutter. It includes multi-strategy paywall bypass for 60+ sites, article tagging, search, notes, reading progress tracking, favorites, export (Markdown/TXT/EPUB), batch operations, and offline reading via service worker.

## Tech Stack

- Python 3.12+ with Flask (venv uses 3.14)
- Flask-SQLAlchemy with SQLite (`instance/articles.db`)
- Flask-Migrate for database migrations
- Flask-Limiter for rate limiting
- Playwright for headless browser fetching (primary), Selenium as fallback
- BeautifulSoup for HTML parsing, nh3 for HTML sanitization
- Flask-WTF for CSRF protection
- ebooklib for EPUB export
- Jinja2 templates with inline CSS (no build step)
- Node.js `docx` package (via `package.json`) for DOCX export support

## Development Commands

```bash
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Run server (http://127.0.0.1:5000)
python app.py

# Run server on production port (5003) with logging
./start_app.sh   # uses port 5003, logs to logs/app.log

# Run utils.py self-tests (PaywallDetector + fetch tests, no server needed)
python utils.py

# Run integration tests (requires server running on port 5000)
python test_final.py

# Database: initialize, migrate, create migration
python -c "from app import app, db; app.app_context().push(); db.create_all()"
flask db upgrade
flask db migrate -m "Description"
```

Debug mode is controlled by `FLASK_DEBUG` env var (defaults to off). `SECRET_KEY` is read from env or auto-generated with `os.urandom(32)`.

**Note:** `.gitignore` excludes `test_*.py` files, so tests are local-only and not committed.

## Architecture

The app is two files: `app.py` (Flask routes + Article model) and `utils.py` (content extraction engine). Templates are in `templates/`, all CSS is inline in `base.html`.

### Article Model (app.py)

```python
class Article(db.Model):
    id              # Integer, primary key
    url             # String(500), required
    title           # String(200)
    content         # Text, required — clean HTML from extraction
    summary         # Text — auto-generated sentence extraction
    images          # Text — JSON string of [{url, alt, caption}]
    tags            # String(500) — comma-separated (e.g. "tech,python")
    notes           # Text — user notes
    is_favorite     # Boolean
    reading_progress # Integer — scroll percentage (0-100)
    reading_time    # Integer — minutes
    word_count      # Integer
    created_at      # DateTime
    updated_at      # DateTime (auto on update)
```

### Routes (app.py)

| Route | Method | Description | Rate Limit |
|-------|--------|-------------|------------|
| `/` | GET | Library with filters, sort, pagination (20/page) | - |
| `/process` | POST | Fetch and save article | 10/min |
| `/article/<id>` | GET | Reading view | - |
| `/search?q=` | GET | AJAX autocomplete | - |
| `/update-tags/<id>` | POST | Update article tags | 30/min |
| `/toggle-favorite/<id>` | POST | Toggle favorite | 30/min |
| `/update-notes/<id>` | POST | Save notes | 30/min |
| `/update-progress/<id>` | POST | Save reading progress | 60/min |
| `/delete/<id>` | POST | Delete article | - |
| `/batch-delete` | POST | Bulk delete | 10/min |
| `/batch-tag` | POST | Bulk tag | 10/min |
| `/export/<id>?format=md\|txt\|epub` | GET | Export single | - |
| `/export-batch` | POST | Bulk export | - |
| `/health` | GET | Health check | - |

All POST endpoints are CSRF-protected (Flask-WTF). URL input is validated against SSRF via `validate_url()` in utils.py.

### utils.py — Content Extraction Engine

The core function is `fetch_article_content(url)` which orchestrates a strategy chain:

1. **Classify the URL** using site lists (`HARD_PAYWALL_SITES`, `CRAWLER_BYPASS_SITES`, `GOOGLE_REFERER_SITES`) and `PaywallDetector`
2. **Choose fetch strategy**: Googlebot UA for crawler-friendly sites → multi-strategy (Googlebot+JS, Facebook crawler, Twitter crawler, no-JS, Google referer) for hard paywalls → random UA rotation for standard sites
3. **Playwright fetch** with request interception blocking ads/analytics/media via `BLOCKED_DOMAINS`
4. **Fallbacks** if primary fails: Selenium (no JS), 12ft.io, Jina AI text extraction, Archive.is
5. **Content extraction**: `clean_article_html()` strips paywall elements using `PAYWALL_ELEMENT_PATTERNS`, then tries `ARTICLE_SELECTORS` in order to find the article body
6. **Post-processing**: `extract_article_images()` filters ad/tracking images, `generate_article_summary()` scores sentences by position/keywords

The `if __name__ == "__main__"` block runs self-tests: PaywallDetector classification on sample URLs, then live fetch tests using Playwright and Selenium against paulgraham.com.

### Key Configuration Constants (utils.py)

| Constant | Purpose |
|----------|---------|
| `HARD_PAYWALL_SITES` | Sites that get multi-strategy bypass attempts |
| `GOOGLE_REFERER_SITES` | Sites that unlock with Google referer header |
| `CRAWLER_BYPASS_SITES` | Sites that show full content to Googlebot/crawlers |
| `BLOCKED_DOMAINS` | Ad/analytics domains blocked during fetch |
| `PAYWALL_ELEMENT_PATTERNS` | CSS classes/IDs stripped before extraction |
| `ARTICLE_SELECTORS` | CSS selectors tried in order to find article body |
| `AD_IMAGE_PATTERNS` / `GOOD_IMAGE_PATTERNS` | Image classification patterns |
| `USER_AGENTS` | User agents for rotation |

### Templates

- `base.html` — All CSS variables, Google Fonts (Cormorant Garamond, Source Sans 3), night mode, service worker registration
- `home.html` — URL input form, article library list, search, filters, sort, batch ops, pagination
- `article.html` — Reading view with floating toolbar, collapsible sidebar (summary, notes, images, export)
- `static/service-worker.js` — Cache-first for static assets, network-first for dynamic content, offline fallback to cached pages

## Security Constraints

- **SSRF**: `validate_url()` blocks non-http(s) schemes, localhost, and private IPs
- **XSS**: `nh3.clean()` sanitizes all extracted HTML. Allowed tags: `p, h1-h6, blockquote, ul, ol, li, hr, br, em, strong, b, i, sub, sup`. No attributes permitted.
- **CSRF**: All state-changing endpoints require CSRF token via Flask-WTF
- **Rate Limiting**: Per-endpoint limits via Flask-Limiter (see route table above)

## Database Gotchas

Tags are stored as comma-separated strings, images as JSON strings. After adding new columns via migration, existing rows have `NULL` values. Templates must guard against this:

```jinja2
{# Correct #}
{% if article.reading_progress and article.reading_progress > 0 %}

{# Wrong — TypeError on NULL #}
{% if article.reading_progress > 0 %}
```

JavaScript must use `or 0` fallbacks: `let progress = {{ reading_progress or 0 }};`

There is also a standalone `migrate_db.py` for manual SQLite migrations (adds `summary` and `images` columns) outside of Flask-Migrate.

## Deployment (macOS LaunchAgent)

The app runs as a background service via `com.reader.app.plist` on port 5003:

```bash
# Install/reload the service
ln -sf $(pwd)/com.reader.app.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.reader.app.plist

# Check status / view logs
launchctl list | grep com.reader.app
tail -f logs/app.log logs/error.log
```

## Known Limitations

**Cannot bypass** (server-side auth or hard bot detection): ft.com, wsj.com, economist.com, statnews.com (STAT+ articles), bloomberg.com, thetimes.co.uk, nytimes.com (DataDome CAPTCHA)

**Archive.is**: CAPTCHA blocks automated access; only works for previously archived articles.

**Port 5000**: On macOS, AirPlay Receiver uses port 5000. Disable it in System Settings or use `app.run(debug=True, port=5001)`.

## Adding a New Paywall Site

1. Determine which strategy works: crawler UA, Google referer, or multi-strategy bypass
2. Add the domain to the appropriate list in utils.py (`CRAWLER_BYPASS_SITES`, `GOOGLE_REFERER_SITES`, or `HARD_PAYWALL_SITES`)
3. If the site has unique paywall DOM elements, add patterns to `PAYWALL_ELEMENT_PATTERNS`
4. Test with `python utils.py` (modify the test URL at bottom) or by running the server and submitting the URL
