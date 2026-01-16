# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pocket Lite is a distraction-free reading web app. Users paste a URL, and the app extracts and displays the main article text without ads or navigation clutter. Features night mode, font resizing, print/PDF export, ad blocking, paywall element removal, and multi-strategy paywall bypass.

## Tech Stack

- Python 3.14 with Flask
- Flask-SQLAlchemy with SQLite (`instance/articles.db`)
- Playwright for headless browser fetching
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

# Run utils.py tests
python utils.py
```

## Architecture

**app.py** - Flask routes and Article database model
- `GET /` - Homepage with URL form and saved articles
- `POST /process` - Fetch URL, extract content, save to DB
- `GET /article/<id>` - Display saved article
- `POST /delete/<id>` - Delete article

**utils.py** - Core content extraction logic
- `fetch_article_content(url)` - Main entry point, returns `{title, text, original_url}`
- `fetch_with_selenium_no_js(url)` - Selenium fallback with JS disabled
- `fetch_from_archive_is(url)` - Archive.is fallback for hard paywalls
- `clean_article_html(element)` - Strips ads, paywalls, converts to clean HTML
- `PaywallDetector` class - Identifies paywall sites and gateway URLs

**templates/** - Jinja2 templates with custom CSS (no Bootstrap)
- `base.html` - CSS variables, Google Fonts (Cormorant Garamond, Source Sans 3)
- `home.html` - URL input form, article library list
- `article.html` - Reading view with floating toolbar

## Fetch Strategy Chain

1. **Playwright** with User-Agent spoofing (Googlebot, Facebook, Twitter crawlers)
2. **Selenium** with JS disabled (for sites blocking Playwright)
3. **Archive.is** cached version (last resort for hard paywalls)

Hard paywall sites (ft.com, economist.com, wsj.com, bloomberg.com, etc.) try all strategies before returning.

## Key Configuration (utils.py)

| Constant | Purpose |
|----------|---------|
| `HARD_PAYWALL_SITES` | Sites that use multi-strategy bypass |
| `GOOGLE_REFERER_SITES` | Sites that respond to Google referer header |
| `BLOCKED_DOMAINS` | Ad/analytics domains blocked during fetch |
| `PAYWALL_ELEMENT_PATTERNS` | CSS classes/IDs removed before extraction |
| `ARTICLE_SELECTORS` | CSS selectors tried in order to find article body |

## Database Model (app.py:11)

```python
class Article:
    id: Integer (primary key)
    url: String(500)
    title: String(200)
    content: Text  # Cleaned HTML from clean_article_html()
    created_at: DateTime
```

## Known Limitations

**Cannot bypass** (server-side auth required):
- thetimes.co.uk, ft.com, wsj.com, economist.com, statnews.com (STAT+ articles)

**Archive.is limitations**:
- CAPTCHA blocks automated access (detected and returns error)
- Only works if article was previously archived

**Sites that work**:
- telegraph.co.uk (Selenium), nytimes.com (JS disabled), washingtonpost.com (Google referer), medium.com, paulgraham.com

## Customization

Edit these in `utils.py`:
- `PAYWALL_SITES` in `PaywallDetector` - Add new paywall sites
- `BLOCKED_DOMAINS` - Add new ad/tracker domains
- `PAYWALL_ELEMENT_PATTERNS` - Add new paywall element patterns
- `ARTICLE_SELECTORS` - Add new content selectors

## macOS Auto-Start

```bash
cp com.reader.app.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.reader.app.plist
```

Logs in `logs/app.log` and `logs/error.log`.
