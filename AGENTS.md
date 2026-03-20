# AGENTS.md - Pocket Lite

This file provides comprehensive guidance for AI coding agents working with the Pocket Lite codebase.

## Project Overview

**Pocket Lite** is a distraction-free reading web application. Users paste a URL, and the app extracts and displays the main article text without ads or navigation clutter. The app features multi-strategy paywall bypass for 60+ sites, article tagging, search, personal notes, reading progress tracking, favorites, export capabilities (Markdown/TXT/EPUB), batch operations, and offline reading via service worker.

## Technology Stack

- **Backend**: Python 3.12+ with Flask
- **Database**: SQLite (`instance/articles.db`) via Flask-SQLAlchemy
- **Migrations**: Flask-Migrate (Alembic)
- **Rate Limiting**: Flask-Limiter
- **Security**: Flask-WTF (CSRF protection)
- **Content Fetching**: Playwright (primary), Selenium (fallback)
- **HTML Parsing**: BeautifulSoup4
- **HTML Sanitization**: nh3
- **EPUB Export**: ebooklib
- **Frontend**: Jinja2 templates with inline CSS (no build step)
- **Typography**: Google Fonts (Cormorant Garamond, Source Sans 3)

## Project Structure

```
Pocket_Lite/
├── app.py                    # Main Flask application (routes, Article model)
├── utils.py                  # Content extraction engine (~2000 lines)
├── requirements.txt          # Python dependencies
├── package.json              # Node.js dependencies (docx library)
├── migrate_db.py             # Standalone SQLite migration script
├── test_app.py               # Playwright UI tests
├── test_final.py             # Integration tests
├── com.reader.app.plist      # macOS LaunchAgent config
├── README.md                 # Brief project description
├── CLAUDE.md                 # Additional developer guidance
├── AGENTS.md                 # This file
├── instance/
│   └── articles.db           # SQLite database
├── logs/
│   ├── app.log               # Application logs
│   └── error.log             # Error logs
├── migrations/               # Flask-Migrate files
│   ├── alembic.ini
│   ├── env.py
│   ├── script.py.mako
│   └── versions/             # Migration scripts
├── static/
│   └── service-worker.js     # Offline reading support
└── templates/
    ├── base.html             # Base template with CSS variables
    ├── home.html             # Library/listing page
    └── article.html          # Reading view
```

## Development Commands

### Setup

```bash
# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Running the Application

```bash
# Start development server (http://127.0.0.1:5000)
python app.py

# With debug mode
FLASK_DEBUG=1 python app.py

# Alternative port (macOS AirPlay uses port 5000)
python -c "from app import app; app.run(debug=True, port=5001)"
```

### Database Operations

```bash
# Initialize database (creates tables)
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# Run migrations
flask db upgrade

# Create new migration
flask db migrate -m "Description of changes"

# Manual migration (legacy)
python migrate_db.py
```

### Testing

```bash
# Run utils.py self-tests (PaywallDetector + fetch tests, no server needed)
python utils.py

# Run integration tests (requires server running on port 5000)
python test_final.py

# Run UI tests with screenshots
python test_app.py
```

## Architecture

### app.py - Routes and Data Model

The `Article` model stores all article data:

```python
class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)        # Clean HTML
    summary = db.Column(db.Text, default="")            # Auto-generated
    images = db.Column(db.Text, default="")             # JSON string of URLs
    tags = db.Column(db.String(500), default="")        # Comma-separated
    notes = db.Column(db.Text, default="")              # User notes
    is_favorite = db.Column(db.Boolean, default=False)
    reading_progress = db.Column(db.Integer, default=0)  # Scroll %
    reading_time = db.Column(db.Integer, default=0)      # Minutes
    word_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Key Routes:**

| Route | Method | Description | Rate Limit |
|-------|--------|-------------|------------|
| `/` | GET | Library with filters, sort, pagination | - |
| `/process` | POST | Fetch and save article | 10/min |
| `/article/<id>` | GET | Reading view | - |
| `/search` | GET | AJAX search autocomplete | - |
| `/update-tags/<id>` | POST | Update article tags | 30/min |
| `/toggle-favorite/<id>` | POST | Toggle favorite status | 30/min |
| `/update-notes/<id>` | POST | Save personal notes | 30/min |
| `/update-progress/<id>` | POST | Update reading progress | 60/min |
| `/delete/<id>` | POST | Delete article | - |
| `/batch-delete` | POST | Bulk delete | 10/min |
| `/batch-tag` | POST | Bulk tag | 10/min |
| `/export/<id>` | GET | Export (md/txt/epub) | - |
| `/export-batch` | POST | Bulk export | - |
| `/health` | GET | Health check | - |

### utils.py - Content Extraction Engine

The core function is `fetch_article_content(url)` which orchestrates a strategy chain:

1. **URL Classification**: Uses `PaywallDetector` and site lists to determine strategy
2. **Strategy Selection**:
   - Crawler-friendly sites → Googlebot UA
   - Hard paywalls → Multi-strategy (Googlebot+JS, Facebook crawler, Twitter crawler, no-JS, Google referer)
   - Standard sites → Random UA rotation
3. **Playwright Fetch**: Request interception blocks ads/analytics/media via `BLOCKED_DOMAINS`
4. **Fallbacks**: Selenium (no JS), 12ft.io, Jina AI, Archive.is
5. **Content Extraction**: `clean_article_html()` strips paywall elements, tries `ARTICLE_SELECTORS`
6. **Post-processing**: Image extraction, summary generation

**Key Configuration Constants:**

| Constant | Purpose |
|----------|---------|
| `HARD_PAYWALL_SITES` | Sites requiring multi-strategy bypass |
| `GOOGLE_REFERER_SITES` | Sites unlocking with Google referer |
| `CRAWLER_BYPASS_SITES` | Sites showing full content to crawlers |
| `BLOCKED_DOMAINS` | Ad/analytics domains blocked during fetch |
| `PAYWALL_ELEMENT_PATTERNS` | CSS classes/IDs stripped before extraction |
| `ARTICLE_SELECTORS` | CSS selectors tried in order |
| `AD_IMAGE_PATTERNS` / `GOOD_IMAGE_PATTERNS` | Image classification |
| `USER_AGENTS` | User agents for rotation |

### Templates

- **base.html**: CSS variables, Google Fonts, night mode, CSRF helper, service worker registration
- **home.html**: URL input, article library, search, filters, sort, batch operations, pagination
- **article.html**: Reading view, floating toolbar, collapsible sidebar (summary, notes, images, export)

All CSS is inline within templates using Jinja2 `{% block extra_styles %}`.

## Database Considerations

### NULL Value Handling

After migrations, existing rows have `NULL` values. Templates must guard against this:

```jinja2
{# Correct #}
{% if article.reading_progress and article.reading_progress > 0 %}

{# Wrong - TypeError on NULL #}
{% if article.reading_progress > 0 %}
```

JavaScript must use fallbacks:
```javascript
let progress = {{ reading_progress or 0 }};
```

### Storage Format

- **tags**: Comma-separated string (e.g., "tech,programming,python")
- **images**: JSON string array of objects with `url`, `alt`, `caption`
- **content**: Clean HTML with allowed tags only

## Security Considerations

1. **SSRF Protection**: `validate_url()` in utils.py blocks:
   - Non-http/https schemes
   - Localhost/private IP addresses
   - Internal network URLs

2. **XSS Prevention**:
   - `nh3.clean()` sanitizes all extracted HTML
   - Allowed tags: `p, h1-h6, blockquote, ul, ol, li, hr, br, em, strong, b, i, sub, sup`
   - No attributes permitted

3. **CSRF Protection**: All state-changing endpoints require CSRF token

4. **Rate Limiting**: Configured per-endpoint to prevent abuse

## Known Limitations

**Cannot bypass** (server-side auth or hard bot detection):
- ft.com, wsj.com, economist.com, bloomberg.com, thetimes.co.uk
- nytimes.com (DataDome CAPTCHA protection)
- statnews.com (STAT+ articles)

**Archive.is**: CAPTCHA blocks automated access; only works for previously archived articles.

**Port 5000**: On macOS, AirPlay Receiver uses port 5000. Disable in System Settings or use port 5001.

## Code Style Guidelines

- **Python**: PEP 8, 4-space indentation
- **Docstrings**: Google style for all public functions
- **Comments**: Explain "why" not "what" for complex logic
- **Error Handling**: Graceful degradation with logging
- **Type Safety**: Defensive coding for database NULLs

## Adding New Paywall Sites

1. Determine which strategy works: crawler UA, Google referer, or multi-strategy bypass
2. Add domain to the appropriate list in `utils.py`:
   - `CRAWLER_BYPASS_SITES` - Shows content to crawlers
   - `GOOGLE_REFERER_SITES` - Unlocks with Google referer header
   - `HARD_PAYWALL_SITES` - Requires multiple bypass attempts
3. If site has unique paywall DOM elements, add patterns to `PAYWALL_ELEMENT_PATTERNS`
4. Test with `python utils.py` or by running the server and submitting the URL

## Deployment

### macOS LaunchAgent

The `com.reader.app.plist` file configures the app to auto-start on macOS:

```bash
# Install
ln -sf /Users/zahidbashir/Documents/Projects/Pocket_Lite/com.reader.app.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.reader.app.plist

# Check status
launchctl list | grep com.reader.app

# View logs
tail -f logs/app.log logs/error.log
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | Flask session security | Random 32-byte hex |
| `FLASK_DEBUG` | Debug mode | 0 |

## Testing Strategy

1. **Unit Tests**: Run `python utils.py` for PaywallDetector and fetch tests
2. **Integration Tests**: Start server, then run `python test_final.py`
3. **UI Tests**: `test_app.py` captures screenshots of key user flows
4. **Manual Testing**: Submit URLs from various sites to verify extraction

## Dependencies

### Python (requirements.txt)

- Flask>=3.0.0
- Flask-SQLAlchemy>=3.1.0
- Flask-Migrate>=4.0.0
- Flask-Limiter>=3.5.0
- Flask-WTF>=1.2.0
- playwright>=1.40.0
- beautifulsoup4>=4.12.0
- selenium>=4.15.0
- webdriver-manager>=4.0.0
- ebooklib>=0.18
- nh3>=0.2.0
- python-frontmatter>=1.0.0
- lxml>=4.9.0

### Node.js (package.json)

- docx@^9.5.1 (for potential Word export feature)

## Offline Support

The service worker (`static/service-worker.js`) implements:
- Cache-first strategy for static assets
- Network-first for dynamic content
- Offline fallback to cached pages

## License

This is a personal project. All code is original unless otherwise noted.
