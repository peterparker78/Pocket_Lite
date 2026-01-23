# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pocket Lite is a distraction-free reading web app. Users paste a URL, and the app extracts and displays the main article text without ads or navigation clutter. Features night mode, font resizing, print/PDF export, ad blocking, paywall element removal, multi-strategy paywall bypass, article tagging with filtering, and quick access to original URLs.

## Tech Stack

- Python 3.12+ with Flask (venv uses 3.14)
- Flask-SQLAlchemy with SQLite (`instance/articles.db`)
- Playwright for headless browser fetching (primary)
- Selenium with webdriver-manager as fallback
- BeautifulSoup for HTML parsing

## Development Commands

```bash
# Setup
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Initialize database (first time)
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Run server (http://127.0.0.1:5000)
python app.py

# Run utils.py self-tests (PaywallDetector + fetch tests)
python utils.py

# Run integration tests (requires server running on port 5000)
python test_final.py
```

## Architecture

**app.py** - Flask routes and Article model (`Article` at line 11)
- `GET /` - Homepage with URL form, saved articles, and tag filtering (`?tag=`)
- `POST /process` - Fetch URL via `fetch_article_content()`, save to DB
- `GET /article/<id>` - Display saved article with tags and Open Original button
- `POST /delete/<id>` - Delete article
- `POST /update-tags/<id>` - Update article tags (JSON API)

**utils.py** - Core content extraction (all fetch logic lives here)
- `fetch_article_content(url)` (line 388) - Main entry point, orchestrates strategy selection
- `fetch_with_selenium_no_js(url)` (line 122) - Selenium fallback with JS disabled
- `fetch_from_archive_is(url)` (line 262) - Archive.is fallback for hard paywalls
- `clean_article_html(element)` (line 695) - Strips ads/paywalls, converts to clean HTML
- `PaywallDetector` class (line 906) - Identifies paywall sites and gateway URLs

**templates/** - Jinja2 templates with custom CSS (no Bootstrap)
- `base.html` - CSS variables, Google Fonts (Cormorant Garamond, Source Sans 3)
- `home.html` - URL input form, article library list, tag filter badges
- `article.html` - Reading view with floating toolbar, Open Original button, tag editing

## Fetch Strategy Chain

The `fetch_article_content()` function selects strategy based on URL:

1. **Crawler bypass** - Sites in `CRAWLER_BYPASS_SITES` (e.g., Substack, nytimes.com) get Googlebot UA
2. **Hard paywall sites** - Try multiple strategies: Googlebot+JS → Facebook crawler → Twitter crawler → Googlebot (no JS) → Google referer
3. **Google referer sites** - Add Google referer header (washingtonpost, theatlantic, etc.)
4. **Standard sites** - Normal Chrome UA, JS disabled for suspected paywalls
5. **Selenium fallback** - For hard paywall sites if Playwright fails
6. **Archive.is** - Last resort for hard paywalls

## Key Configuration (utils.py)

| Constant | Line | Purpose |
|----------|------|---------|
| `HARD_PAYWALL_SITES` | 38 | Sites that use multi-strategy bypass (includes nytimes.com/athletic, wired.com) |
| `GOOGLE_REFERER_SITES` | 53 | Sites that respond to Google referer header |
| `CRAWLER_BYPASS_SITES` | 62 | Sites that show full content to crawler UAs (includes nytimes.com) |
| `BLOCKED_DOMAINS` | 72 | Ad/analytics domains blocked during fetch |
| `PAYWALL_ELEMENT_PATTERNS` | 91 | CSS classes/IDs removed before extraction |
| `ARTICLE_SELECTORS` | 106 | CSS selectors tried in order to find article body |
| `MIN_CONTENT_LENGTH` | 611 | Minimum characters (500) for valid article content |

## Known Limitations

**Cannot bypass** (server-side auth required):
- thetimes.co.uk, ft.com, wsj.com, economist.com, statnews.com (STAT+ articles)

**Archive.is limitations**:
- CAPTCHA blocks automated access (detected and returns error)
- Only works if article was previously archived

**Sites that work**:
- substack.com (crawler UA), telegraph.co.uk (Selenium), nytimes.com (crawler UA), nytimes.com/athletic (Googlebot+JS), washingtonpost.com (Google referer), medium.com, paulgraham.com, newscientist.com (crawler UA), wired.com (Facebook crawler)

## Customization

Edit constants at the top of `utils.py`:
- `PAYWALL_SITES` in `PaywallDetector` (line 910) - Add new paywall sites
- `HARD_PAYWALL_SITES` (line 38) - Add sites needing multi-strategy bypass
- `CRAWLER_BYPASS_SITES` (line 62) - Add sites that show full content to Googlebot
- `BLOCKED_DOMAINS` (line 72) - Add new ad/tracker domains
- `PAYWALL_ELEMENT_PATTERNS` (line 91) - Add new paywall element patterns
- `ARTICLE_SELECTORS` (line 106) - Add new content selectors

## macOS Auto-Start

```bash
cp com.reader.app.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.reader.app.plist
```

Logs in `logs/app.log` and `logs/error.log`.
