# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pocket Lite is a distraction-free reading web app. Users paste a URL, and the app extracts and displays the main article text without ads or navigation clutter. Includes night mode, font resizing, print/PDF export, ad blocking, paywall element removal, and soft paywall bypass.

## Tech Stack

- Python 3.14 with Flask web framework
- Flask-SQLAlchemy with SQLite database
- Playwright for headless browser fetching with anti-bot measures
- Selenium with webdriver-manager for alternative fetching with JS disabled
- BeautifulSoup for HTML parsing and content cleaning
- Custom CSS with Google Fonts (no Bootstrap)

## Requirements

```
flask
flask-sqlalchemy
requests
beautifulsoup4
trafilatura
playwright
selenium
webdriver-manager
```

## Development Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Initialize database (first time only)
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Run the development server
python app.py

# Run utils.py tests
python utils.py
```

The server runs at http://127.0.0.1:5000

## Architecture

```
Pocket_Lite/
├── app.py                 # Flask application with routes
├── utils.py               # fetch_article_content, clean_article_html, PaywallDetector
├── requirements.txt       # Python dependencies
├── CLAUDE.md              # Documentation for Claude Code
├── instance/
│   └── articles.db        # SQLite database
├── templates/
│   ├── base.html          # Base template with CSS variables and Google Fonts
│   ├── home.html          # Homepage with URL form and article library
│   └── article.html       # Reading view with floating toolbar
├── logs/                  # launchd service logs
└── com.reader.app.plist   # macOS auto-start configuration
```

## Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Homepage with URL input and saved articles list |
| `/process` | POST | Fetches URL with Playwright, extracts text, saves to database |
| `/article/<id>` | GET | Display a saved article |
| `/delete/<id>` | POST | Delete an article from database |

## Key Functions (utils.py)

**`fetch_article_content(url)`** - Main fetching function that returns `{'title', 'text', 'original_url'}`:

1. **Browser Setup:**
   - Launches headless Chromium
   - User-Agent spoofing (Chrome 120 on macOS)
   - 1920x1080 viewport
   - Disables JavaScript for nytimes.com and other paywall sites

2. **Request Blocking:**
   - Blocks images, media, fonts (speed optimization)
   - Blocks ad/tracker domains

3. **Human Mimicking:**
   - Random 1-3 second delay after page load

4. **BeautifulSoup Parsing:**
   - Removes paywall elements (class/id matching patterns)
   - Extracts title from `<title>` or `<h1>`
   - Extracts text using article selectors with fallbacks

**`fetch_with_selenium_no_js(url)`** - Alternative fetcher with JavaScript disabled:

1. **Browser Fallback:**
   - Tries Firefox first (with GeckoDriver)
   - Falls back to Chrome if Firefox not installed
   - Uses webdriver-manager for automatic driver installation

2. **JavaScript Disabled Mode:**
   - Disables JS completely to bypass soft paywalls
   - Falls back to JS-enabled if content is empty

3. **Configuration:**
   - Headless mode (no browser window)
   - Custom User-Agent (Chrome 120 on macOS)
   - Images and CSS disabled for faster loading

**`fetch_from_archive_is(url)`** - Fallback fetcher for hard paywalls:

1. **Archive.is Lookup:**
   - Constructs URL: `https://archive.is/newest/<encoded_url>`
   - Navigates to most recent archived version
   - Checks if archive exists (handles "No results" page)

2. **Content Extraction:**
   - Removes archive.is toolbar/header elements
   - Uses same article selectors as main fetcher
   - Cleans content with `clean_article_html()`

3. **Returns:**
   - Same format as `fetch_article_content()` plus `source: "archive.is"`

**`PaywallDetector` class:**
- `is_suspected_paywall(url)` - Checks against 13 known paywall sites
- `contains_gateway_patterns(url)` - Detects /subscribe, /pay, /login paths
- `analyze(url)` - Returns dict with both checks

## Paywall Element Patterns (utils.py)

Elements with these class/id patterns are removed before text extraction:
- paywall, subscribe-barrier, subscription-barrier, modal
- ad-container, advertisement, piano-offer, metered-content
- gateway, regwall, pw-

## Article Selectors (utils.py)

Text extraction tries these selectors in order:
1. `<article>`, `<main>`, `[role='main']`
2. `.post-content`, `.article-content`, `.article-body`
3. `.story-body`, `.entry-content`, `.content-body`, `#article-body`
4. Fallback to `<body>` element

## Content Processing (utils.py)

**`clean_article_html(element)`** - Cleans fetched HTML for distraction-free reading:

1. **Removes unwanted elements:**
   - Scripts, styles, iframes, forms, buttons
   - Images, videos, SVGs, canvas elements
   - Navigation, footer, header, aside elements

2. **Removes elements by class/id patterns:**
   - paywall, subscribe, advertisement, ad-, social
   - share, related, newsletter, signup, popup, modal
   - sidebar, comment, author-bio, metadata

3. **Converts links to plain text:**
   - `<a href="...">text</a>` becomes just `text`

4. **Preserves structure:**
   - Headlines (h1-h6)
   - Paragraphs (p)
   - Blockquotes
   - Lists (ul, ol, li)
   - Section separators (hr)

5. **Legacy HTML support:**
   - Falls back to `extract_legacy_content()` for old-style HTML
   - Handles sites like paulgraham.com that don't use `<p>` tags
   - Creates paragraphs from text separated by blank lines

## Paywall Sites (utils.py)

JavaScript is disabled for these sites:
- nytimes.com (explicit check), wsj.com, medium.com, washingtonpost.com
- hbr.org, economist.com, ft.com, bloomberg.com, theatlantic.com
- newyorker.com, wired.com, thetimes.co.uk, telegraph.co.uk

## Hard Paywall Bypass (utils.py)

**Multi-Strategy Approach** for sites with server-side paywall detection:

1. **User-Agent Spoofing:**
   - Facebook crawler: `facebookexternalhit/1.1`
   - Twitter crawler: `Twitterbot/1.0`
   - Googlebot: `Googlebot/2.1`

2. **Referer Spoofing:**
   - Sets referer header to appear as if coming from Google, Facebook, or Twitter

3. **Archive.is Fallback:**
   - When direct fetch fails, attempts to retrieve cached version from archive.is
   - Uses `https://archive.is/newest/<url>` to get most recent archived copy
   - Works for articles that were archived before paywall was added

**Hard Paywall Sites** (uses all bypass strategies):
- ft.com, economist.com, wsj.com, bloomberg.com, businessinsider.com, barrons.com

**`fetch_from_archive_is(url)`** function:
- Fetches cached article from archive.is
- Removes archive.is toolbar/header elements
- Returns same format as `fetch_article_content()`
- Added `source: "archive.is"` field to indicate cached content

**Paywall Detection:**
- Checks for paywall phrases: "subscribe to continue", "subscribers only", etc.
- If content appears to be paywall page, tries archive.is fallback

## Blocked Domains (utils.py)

Ad/analytics domains blocked during fetch:
- doubleclick, adsystem, analytics, googlesyndication, adservice
- facebook.com/tr, connect.facebook, googletagmanager
- google-analytics, scorecardresearch, optimizely, hotjar

## Database Model

**Article** (`app.py:11`)
- `id` - Integer, primary key
- `url` - String(500), the source URL
- `title` - String(200), extracted article title
- `content` - Text, extracted article content
- `created_at` - DateTime, when article was saved

## UI Design

**Typography:**
- **Headlines**: Cormorant Garamond (elegant serif from Google Fonts)
- **Body Text**: Source Sans 3 (clean, readable sans-serif)
- **Drop Cap**: First letter of article styled with accent color

**Color Palette:**

| Element | Light Mode | Dark Mode |
|---------|------------|-----------|
| Background | #FAF8F5 (warm parchment) | #0F1419 (deep ink) |
| Text | #2C2C2C (charcoal) | #E7E9EA (off-white) |
| Accent | #B8472D (terracotta) | #E8694A (coral) |
| Secondary BG | #F3F0EB | #1A2028 |

**Visual Features:**
- Subtle paper grain texture overlay
- Glassmorphism floating toolbar with backdrop blur
- Smooth fade-in animations on page load
- SVG icons (Feather icons style)
- Justified text with auto-hyphenation in article view

## UI Features

- **Night Mode** - Toggle dark/light theme (saved to localStorage)
- **Font Resize** - A+/A- buttons to adjust text size (1.0rem-1.8rem)
- **Print/PDF** - Print button opens browser print dialog
- **Delete** - Remove articles from homepage or reading view
- **Drop Cap** - Decorative first letter on article paragraphs
- **Section Separators** - `<hr>` tags rendered as `***` dividers

## Auto-Start on macOS

The `com.reader.app.plist` file configures launchd to run the server automatically.

```bash
# Install and start
cp com.reader.app.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.reader.app.plist

# Stop
launchctl unload ~/Library/LaunchAgents/com.reader.app.plist

# View logs
cat logs/app.log
cat logs/error.log
```

## Customization

**Add paywall sites** - Edit `PAYWALL_SITES` in `PaywallDetector` class (`utils.py`):
```python
PAYWALL_SITES = [
    r"nytimes\.com",
    r"newsite\.com",  # Add new site
]
```

**Add blocked domains** - Edit `BLOCKED_DOMAINS` in `utils.py`:
```python
BLOCKED_DOMAINS = [
    "doubleclick",
    "newadnetwork",  # Add new ad domain
]
```

**Add paywall element patterns** - Edit `PAYWALL_ELEMENT_PATTERNS` in `utils.py`:
```python
PAYWALL_ELEMENT_PATTERNS = [
    "paywall",
    "new-paywall-class",  # Add new pattern
]
```

**Add article selectors** - Edit `ARTICLE_SELECTORS` in `utils.py`:
```python
ARTICLE_SELECTORS = [
    "article",
    ".new-content-class",  # Add new selector
]
```

## Troubleshooting

**ModuleNotFoundError: No module named 'selenium'**
- Run `pip install selenium webdriver-manager`
- Restart the Flask server after installation

**Firefox not installed (Selenium)**
- The app automatically falls back to Chrome if Firefox is unavailable
- Install Firefox for best paywall bypass results

**GeckoDriver/ChromeDriver errors**
- webdriver-manager automatically downloads the correct driver
- Drivers are cached in `~/.wdm/` directory

**AttributeError during paywall element removal**
- Fixed: Elements are now collected first, then removed in a separate loop
- This prevents iteration issues when BeautifulSoup modifies the DOM

**Empty article content**
- Selenium tries JS-disabled first, then JS-enabled as fallback
- Check if the site requires JavaScript to render content
