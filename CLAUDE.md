# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pocket Lite is a distraction-free reading web app. Users paste a URL, and the app extracts and displays the main article text without ads or navigation clutter. Features include:
- **Night mode, font resizing, print/PDF export**
- **Ad blocking and paywall element removal**
- **Multi-strategy paywall bypass** (60+ sites supported)
- **Article tagging with filtering**
- **Auto-generated article summaries** - Key points extracted from content
- **Article image gallery** - Relevant images extracted and displayed in sidebar
- **Personal notes** - Add notes to each article with auto-save
- **Reading progress tracking** - Visual progress bar and resume position
- **Reading time estimates** - Calculated based on word count
- **Favorites/bookmarks** - Star important articles
- **Search functionality** - Search by title, content, or URL
- **Full-text export** - Markdown, plain text, or EPUB
- **Batch operations** - Delete or tag multiple articles at once
- **Pagination** - For large article libraries
- **Keyboard shortcuts** - Quick navigation and actions
- **Offline reading** - Service worker for offline access
- **Rate limiting** - Prevent abuse on process endpoint
- **Flask-Migrate** - Database migration management
- **Quick access to original URLs**

## Tech Stack

- Python 3.12+ with Flask (venv uses 3.14)
- Flask-SQLAlchemy with SQLite (`instance/articles.db`)
- Flask-Migrate for database migrations
- Flask-Limiter for rate limiting
- Playwright for headless browser fetching (primary)
- Selenium with webdriver-manager as fallback
- BeautifulSoup for HTML parsing
- ebooklib for EPUB export

## Development Commands

```bash
# Setup
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Initialize database (first time)
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Run migrations
flask db upgrade

# Run server (http://127.0.0.1:5000)
python app.py

# Run utils.py self-tests (PaywallDetector + fetch tests)
python utils.py

# Create new migration
flask db migrate -m "Description"

# Run tests (requires server running on port 5000)
python test_final.py
```

## Architecture

**app.py** - Flask routes and Article model
- `GET /` - Homepage with URL form, saved articles, tag filtering, search, sorting, pagination
- `POST /process` - Fetch URL via `fetch_article_content()`, save to DB (rate limited: 10/min)
- `GET /article/<id>` - Display saved article with tags, notes, images, reading progress
- `POST /delete/<id>` - Delete article
- `POST /batch-delete` - Delete multiple articles at once
- `POST /batch-tag` - Add tags to multiple articles
- `POST /update-tags/<id>` - Update article tags (JSON API)
- `POST /toggle-favorite/<id>` - Toggle favorite status
- `POST /update-notes/<id>` - Update personal notes
- `POST /update-progress/<id>` - Update reading progress
- `GET /export/<id>?format=md|txt|epub` - Export article
- `POST /export-batch` - Export multiple articles
- `GET /search?q=...` - AJAX search endpoint

**utils.py** - Core content extraction
- `fetch_article_content(url)` - Main entry point, orchestrates strategy selection
- `fetch_with_selenium_no_js(url)` - Selenium fallback with JS disabled
- `fetch_from_archive_is(url)` - Archive.is fallback
- `fetch_from_12ft_io(url)` - 12ft.io paywall bypass
- `fetch_from_textise_dot_iitty(url)` - Jina AI text extraction
- `clean_article_html(element)` - Strips ads/paywalls, converts to clean HTML
- `extract_article_images(soup, url)` - Extract content images, filter ads
- `generate_article_summary(html)` - Generate article summary from content
- `estimate_reading_time(word_count)` - Calculate reading time in minutes
- `get_random_user_agent()` - Rotate user agents
- `PaywallDetector` class - Identifies paywall sites and gateway URLs

**templates/** - Jinja2 templates
- `base.html` - CSS variables, Google Fonts (Cormorant Garamond, Source Sans 3), service worker
- `home.html` - URL input form, article library list, search, filters, sort, batch ops, pagination
- `article.html` - Reading view with floating toolbar, sidebar (summary, notes, images, export)

**static/** - Static assets
- `service-worker.js` - Service worker for offline reading

## Fetch Strategy Chain

The `fetch_article_content()` function selects strategy based on URL:

1. **Crawler bypass** - Sites in `CRAWLER_BYPASS_SITES` (e.g., Substack, nytimes.com) get Googlebot UA
2. **Hard paywall sites** - Try multiple strategies: Googlebot+JS → Facebook crawler → Twitter crawler → Googlebot (no JS) → Google referer
3. **User-agent rotation** - Random UA from list of 10+ real browser UAs
4. **Google referer sites** - Add Google referer header (washingtonpost, theatlantic, etc.)
5. **Standard sites** - Normal Chrome UA, JS disabled for suspected paywalls
6. **Selenium fallback** - For hard paywall sites if Playwright fails
7. **12ft.io** - Popular paywall bypass service
8. **Jina AI** - Text extraction fallback
9. **Archive.is** - Last resort for hard paywalls

## Supported Paywall Sites

### News & Journalism
- **Works well**: substack.com, medium.com, nytimes.com, washingtonpost.com, theguardian.com, telegraph.co.uk, newscientist.com, wired.com, theatlantic.com, newyorker.com, businessinsider.com, axios.com, politico.com, hbr.org
- **Regional US**: latimes.com, chicagotribune.com, bostonglobe.com, seattletimes.com, denverpost.com, dallasnews.com, startribune.com, jsonline.com
- **UK/EU**: thetimes.co.uk, ft.com, economist.com, independent.co.uk, irishtimes.com, spiegel.de, lemonde.fr
- **Asia/Pacific**: scmp.com, smh.com.au, theaustralian.com.au, japantimes.co.jp

### Business & Finance
- bloomberg.com, wsj.com, barrons.com, marketwatch.com, seekingalpha.com, fortune.com, forbes.com, fastcompany.com, inc.com

### Technology & Science
- technologyreview.com (MIT), scientificamerican.com, nature.com, ieee.org, spectrum.ieee.org, arstechnica.com, theverge.com, techcrunch.com

### Magazines & Culture
- vanityfair.com, gq.com, esquire.com, rollingstone.com, billboard.com, time.com

### Academic & Education
- chronicle.com, insidehighered.com, timeshighereducation.com

## Key Configuration (utils.py)

| Constant | Purpose |
|----------|---------|
| `HARD_PAYWALL_SITES` | Sites that use multi-strategy bypass |
| `GOOGLE_REFERER_SITES` | Sites that respond to Google referer header |
| `CRAWLER_BYPASS_SITES` | Sites that show full content to Googlebot |
| `BLOCKED_DOMAINS` | Ad/analytics domains blocked during fetch |
| `PAYWALL_ELEMENT_PATTERNS` | CSS classes/IDs removed before extraction |
| `ARTICLE_SELECTORS` | CSS selectors tried in order to find article body |
| `AD_IMAGE_PATTERNS` | Patterns to identify ad images |
| `GOOD_IMAGE_PATTERNS` | Patterns to identify content images |
| `USER_AGENTS` | List of user agents for rotation |

## Database Schema

```sql
CREATE TABLE article (
    id INTEGER PRIMARY KEY,
    url VARCHAR(500) NOT NULL,
    title VARCHAR(200),
    content TEXT NOT NULL,
    summary TEXT DEFAULT '',
    images TEXT DEFAULT '',      -- JSON string of image URLs
    tags VARCHAR(500) DEFAULT '',
    notes TEXT DEFAULT '',       -- Personal notes
    is_favorite BOOLEAN DEFAULT 0,
    reading_progress INTEGER DEFAULT 0,  -- Scroll position %
    reading_time INTEGER DEFAULT 0,      -- Minutes
    word_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Known Limitations

**Cannot bypass** (server-side auth or bot detection):
- ft.com, wsj.com, economist.com, statnews.com (STAT+ articles), bloomberg.com (bot detection), thetimes.co.uk

**Archive.is limitations**:
- CAPTCHA blocks automated access (detected and returns error)
- Only works if article was previously archived

## Troubleshooting

### Port 5000 Already in Use
On macOS, AirPlay Receiver uses port 5000. Either:
1. Disable AirPlay Receiver in System Settings → General → AirDrop & Handoff
2. Or run the app on a different port: `app.run(debug=True, port=5001)`

### Database Migration Issues
After adding new columns (like `reading_progress`, `notes`, etc.), existing articles may have `NULL` values. Templates should handle this:
```jinja2
{# Correct - handle NULL values #}
{% if article.reading_progress and article.reading_progress > 0 %}

{# Incorrect - will cause TypeError #}
{% if article.reading_progress > 0 %}
```
Always use `or 0` fallbacks in JavaScript:
```javascript
let progress = {{ reading_progress or 0 }};
```

## Features

### Article Summary
Automatically extracts key sentences to create a summary displayed in the sidebar. Uses a scoring algorithm based on:
- Position in article (first sentences prioritized)
- Presence of important keywords ("announced", "study", "reported", etc.)
- Sentence length and structure

### Image Extraction
Extracts article images while filtering out:
- Advertisements and sponsored content
- Icons, logos, and avatars
- Tracking pixels and beacons
- Social media buttons

Images are displayed in a gallery with lightbox support for viewing full size.

### Reading Progress Tracking
- Visual progress bar at top of page
- Scroll position saved automatically every 10% or 30 seconds
- Resume reading where you left off
- Progress displayed in article list

### Export Formats
- **Markdown (.md)** - Clean markdown with frontmatter
- **Plain Text (.txt)** - Simple text format
- **EPUB (.epub)** - E-book format for e-readers
- **Batch Export** - Export multiple articles as ZIP or combined file

### Keyboard Shortcuts

**Home Page:**
- `/` - Focus search
- `n` - Focus URL input
- `m` - Toggle night mode
- `j/k` - Navigate pages
- `Ctrl+a` - Select all articles

**Article Page:**
- `+`/`-` - Increase/decrease font size
- `m` - Toggle night mode
- `p` - Print
- `d` - Delete article
- `e` - Export article
- `b` - Back to library
- `Esc` - Close lightbox

### Batch Operations
- Select multiple articles with checkboxes
- Bulk delete selected articles
- Add tags to multiple articles at once
- Export multiple articles together

### Rate Limiting
- Process endpoint: 10 requests per minute per IP
- General: 200 requests per day, 50 per hour per IP

## macOS Auto-Start

```bash
cp com.reader.app.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.reader.app.plist
```

Logs in `logs/app.log` and `logs/error.log`.
