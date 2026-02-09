import re
import time
import random
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import nh3

# Selenium imports
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.chrome import ChromeDriverManager


# Standard Chrome on Mac User-Agent
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Googlebot User-Agent (some sites show full content to crawlers)
GOOGLEBOT_USER_AGENT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

# Facebook crawler User-Agent (sites often allow for social sharing previews)
FACEBOOK_USER_AGENT = (
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
)

# Twitter crawler User-Agent
TWITTER_USER_AGENT = "Twitterbot/1.0"

# Extended User-Agent list for rotation
USER_AGENTS = [
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    # Googlebot variants
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html) Chrome/120.0.0.0 Safari/537.36",
    # Bingbot
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/120.0.0.0 Safari/537.36",
    # DuckDuckGo
    "DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckbot.html)",
]


def get_random_user_agent():
    """Get a random user agent for rotation."""
    return random.choice(USER_AGENTS)


def estimate_reading_time(word_count):
    """
    Estimate reading time in minutes based on word count.
    Average reading speed: 200-250 words per minute
    """
    if not word_count or word_count <= 0:
        return 1
    minutes = word_count / 200
    return max(1, round(minutes))

# Sites with hard paywalls - try multiple bypass strategies
HARD_PAYWALL_SITES = [
    "ft.com",
    "economist.com",
    "wsj.com",
    "bloomberg.com",
    "businessinsider.com",
    "barrons.com",
    "thetimes.co.uk",
    "telegraph.co.uk",
    "theathletic.com",
    "nytimes.com/athletic",
    "wired.com",
    # Additional financial/business news
    "marketwatch.com",
    "seekingalpha.com",
    "thestreet.com",
    "investors.com",
    "morningstar.com",
    "kiplinger.com",
    "financialpost.com",
    "marketscreener.com",
    "reuters.com",  # Some premium content
    "cnbc.com",  # Some premium content
    # Technology/Science paywalls
    "technologyreview.com",  # MIT Technology Review
    "scientificamerican.com",
    "nature.com",
    "science.org",
    "newscientist.com",
    "ieee.org",
    "acm.org",
    "spectrum.ieee.org",
    # News/Investigative
    "foreignpolicy.com",
    "theinformation.com",
    "axios.com",
    "politico.com",  # Some premium content
    "statnews.com",  # STAT+ articles
    "law360.com",
    "propublica.org",  # Sometimes
    "revealnews.org",
    # Regional newspapers
    "latimes.com",
    "chicagotribune.com",
    "bostonglobe.com",
    "seattletimes.com",
    "mercurynews.com",
    "denverpost.com",
    "dallasnews.com",
    "houstonchronicle.com",
    "philly.com",
    "miamiherald.com",
    "startribune.com",
    "plaindealer.com",
    "oregonlive.com",
    "sacbee.com",
    "sandiegouniontribune.com",
    "baltimoresun.com",
    "pilotonline.com",
    "reviewjournal.com",
    "ajc.com",  # Atlanta Journal-Constitution
    "detroitnews.com",
    "freep.com",  # Detroit Free Press
    "tampabay.com",
    "orlandosentinel.com",
    "sun-sentinel.com",
    "indyStar.com",
    "courier-journal.com",
    "jsonline.com",  # Milwaukee Journal Sentinel
    "kansascity.com",
    "stltoday.com",
    "tulsaworld.com",
    "oklahoman.com",
    "statesman.com",  # Austin American-Statesman
    "dallasnews.com",
    # UK/European news
    "theguardian.com",  # Some premium
    "independent.co.uk",
    "eveningstandard.co.uk",
    "scotsman.com",
    "heraldscotland.com",
    "irishtimes.com",
    "france24.com",  # Some premium
    "spiegel.de",  # Some premium
    "zeit.de",  # German
    "faz.net",  # Frankfurter Allgemeine
    "lemonde.fr",  # Some premium
    "figaro.fr",
    "corriere.it",
    "repubblica.it",
    "elmundo.es",
    "elpais.com",
    # Asian/Australian news
    "afr.com",  # Australian Financial Review
    "theaustralian.com.au",
    "smh.com.au",  # Sydney Morning Herald
    "theage.com.au",
    "couriermail.com.au",
    "dailytelegraph.com.au",
    "heraldsun.com.au",
    "scmp.com",  # South China Morning Post
    "japantimes.co.jp",
    "asahi.com",
    "mainichi.jp",
    "straitstimes.com",
    # Magazines
    "newyorker.com",  # Some articles
    "vanityfair.com",
    "gq.com",
    "esquire.com",
    "theatlantic.com",  # Some premium
    "time.com",  # Some premium
    "fortune.com",
    "fastcompany.com",
    "inc.com",
    "entrepreneur.com",
    "forbes.com",  # Some premium
    "hbr.org",
    # Academic/Educational
    "chronicle.com",  # Chronicle of Higher Education
    "insidehighered.com",
    "edweek.org",
    "timeshighereducation.com",
    "theconversation.com",  # Some university access
    "jstor.org",
    "ssrn.com",  # Some papers
    "researchgate.net",  # Some papers
    "academia.edu",
    # Sports
    "espn.com",  # ESPN+ content
    "espnplus.com",
    "cbssports.com",  # Some premium
    "nbcsports.com",
    "thesportsanalyst.com",
    "athlonsports.com",
    # Entertainment/Lifestyle
    "variety.com",
    "hollywoodreporter.com",
    "deadline.com",
    "billboard.com",
    "rollingstone.com",
    "pitchfork.com",
    "vulture.com",
    "eater.com",
    "thrillist.com",
    "apartmenttherapy.com",
]

# Sites that may respond to Google referer
GOOGLE_REFERER_SITES = [
    "nytimes.com",
    "washingtonpost.com",
    "theatlantic.com",
    "wired.com",
    "newyorker.com",
    "theguardian.com",
    "latimes.com",
    "chicagotribune.com",
    "bostonglobe.com",
    "technologyreview.com",
    "foreignpolicy.com",
    "forbes.com",
    "hbr.org",
    "scientificamerican.com",
    "nationalgeographic.com",
    "theverge.com",
    "vox.com",
    "polygon.com",
    "sbnation.com",
    "eater.com",
    "racked.com",
    "curbed.com",
]

# Sites that show full content to crawler user agents (for SEO/social sharing)
CRAWLER_BYPASS_SITES = [
    "substack.com",
    "newscientist.com",
    "nytimes.com",
    "medium.com",
    "ghost.org",
    "hashnode.com",
    "dev.to",
    "betterprogramming.pub",
    "towardsdatascience.com",
    "javascript.plainenglish.io",
    "blogspot.com",
    "wordpress.com",
    "techcrunch.com",
    "theverge.com",
    "arstechnica.com",
    "engadget.com",
    "gizmodo.com",
    "lifehacker.com",
    "kotaku.com",
    "jezebel.com",
    "avclub.com",
    "deadspin.com",
    "theringer.com",
    "defector.com",
    "aftermath.site",
    "platformer.news",
    "lennyrachitsky.com",
    "stratechery.com",
    "benthompson.com",
    "paulgraham.com",
]

# Archive.is base URL for cached content
ARCHIVE_IS_URL = "https://archive.is/newest/"

# Domains to block (ads, analytics, trackers)
BLOCKED_DOMAINS = [
    "doubleclick",
    "adsystem",
    "analytics",
    "googlesyndication",
    "adservice",
    "facebook.com/tr",
    "connect.facebook",
    "googletagmanager",
    "google-analytics",
    "scorecardresearch",
    "optimizely",
    "hotjar",
]

# Resource types to block (speed optimization)
BLOCKED_RESOURCE_TYPES = ["image", "media", "font"]

# Paywall element patterns to remove (class names or IDs)
PAYWALL_ELEMENT_PATTERNS = [
    "paywall",
    "subscribe-barrier",
    "subscription-barrier",
    "modal",
    "ad-container",
    "advertisement",
    "piano-offer",
    "metered-content",
    "gateway",
    "regwall",
    "pw-",
]

# Article body selectors (in order of preference)
ARTICLE_SELECTORS = [
    ".available-content",  # Substack
    ".body.markup",  # Substack alternative
    "article",
    "main",
    "[role='main']",
    ".post-content",
    ".article-content",
    ".article-body",
    ".story-body",
    ".entry-content",
    ".content-body",
    "#article-body",
]


def fetch_with_selenium_no_js(url):
    """
    Fetch page content using Selenium with JavaScript disabled.

    This is effective for bypassing soft paywalls that rely on JS to show
    subscription modals or block content.

    Features:
    - Tries Firefox first, falls back to Chrome if Firefox not installed
    - Uses webdriver_manager to auto-install drivers
    - JavaScript completely disabled (stops paywall scripts)
    - Headless mode (no browser window)
    - Fallback to JS-enabled mode if content is empty

    Args:
        url: The URL to fetch

    Returns:
        HTML content string, or None if fetch failed
    """

    def create_firefox_driver(disable_js=True):
        """Create a Firefox WebDriver with specified options."""
        options = FirefoxOptions()

        # Run in headless mode (no GUI)
        options.add_argument("--headless")

        # Set user agent to look like a real browser
        options.set_preference("general.useragent.override", USER_AGENT)

        # Disable JavaScript if requested (crucial for paywall bypass)
        if disable_js:
            options.set_preference("javascript.enabled", False)

        # Disable images for faster loading
        options.set_preference("permissions.default.image", 2)

        # Disable CSS for faster loading (optional)
        options.set_preference("permissions.default.stylesheet", 2)

        # Disable notifications
        options.set_preference("dom.webnotifications.enabled", False)

        # Use webdriver_manager to auto-install GeckoDriver (Selenium 4.0+ compatible)
        service = FirefoxService(GeckoDriverManager().install())

        driver = webdriver.Firefox(service=service, options=options)
        return driver

    def create_chrome_driver(disable_js=True):
        """Create a Chrome WebDriver with specified options (fallback)."""
        options = ChromeOptions()

        # Run in headless mode (no GUI)
        options.add_argument("--headless=new")

        # Set user agent
        options.add_argument(f"--user-agent={USER_AGENT}")

        # Disable JavaScript if requested
        # Note: Chrome uses experimental options for this
        if disable_js:
            options.add_experimental_option("prefs", {
                "profile.managed_default_content_settings.javascript": 2,
            })

        # Disable images for faster loading
        options.add_argument("--blink-settings=imagesEnabled=false")

        # Disable notifications
        options.add_argument("--disable-notifications")

        # Common Chrome flags for stability
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        # Use webdriver_manager to auto-install ChromeDriver
        service = ChromeService(ChromeDriverManager().install())

        driver = webdriver.Chrome(service=service, options=options)
        return driver

    def fetch_page(driver, target_url):
        """Load URL and extract page source."""
        try:
            driver.get(target_url)
            # Wait for content to load
            time.sleep(2)
            return driver.page_source
        except Exception as e:
            return None

    def has_meaningful_content(html):
        """Check if HTML has meaningful article content."""
        if not html:
            return False
        soup = BeautifulSoup(html, "html.parser")
        # Check for paragraph content
        paragraphs = soup.find_all("p")
        text_length = sum(len(p.get_text(strip=True)) for p in paragraphs)
        return text_length > 200  # At least 200 chars of paragraph text

    # Try Firefox first
    driver_creators = [
        ("Firefox", create_firefox_driver),
        ("Chrome", create_chrome_driver),
    ]

    for browser_name, create_driver in driver_creators:
        # First attempt: JavaScript disabled (for paywall bypass)
        try:
            driver = create_driver(disable_js=True)
            html_content = fetch_page(driver, url)
            driver.quit()

            # Check if we got meaningful content
            if has_meaningful_content(html_content):
                return html_content

        except Exception as e:
            # Browser not available or other error, try next
            continue

        # Fallback: JavaScript enabled (some sites need JS to render content)
        try:
            driver = create_driver(disable_js=False)
            html_content = fetch_page(driver, url)
            driver.quit()

            if html_content:
                return html_content

        except Exception as e:
            continue

    return None


def fetch_from_archive_is(url):
    """
    Fetch article content from archive.is as a fallback for hard paywalls.

    Archive.is (also known as archive.today) caches web pages. Many paywall
    sites have their content cached before the paywall was added or by users
    who had access.

    Args:
        url: The original article URL to find in archive.is

    Returns:
        Dict with 'title', 'text', 'original_url', or None if not found
    """
    import urllib.parse

    archive_url = ARCHIVE_IS_URL + urllib.parse.quote(url, safe="")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        try:
            # Navigate to archive.is with the original URL
            page.goto(archive_url, wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # Check if we got redirected to an archive page or a "not found" page
            current_url = page.url

            # Get page content for checks
            page_content = page.content()

            # Check for CAPTCHA/security challenge
            captcha_indicators = [
                "one more step",
                "security check",
                "captcha",
                "please complete",
                "verify you are human",
                "cloudflare",
            ]
            page_lower = page_content.lower()
            if any(indicator in page_lower for indicator in captcha_indicators):
                browser.close()
                return None

            # If still on archive.is/newest/, the page wasn't found
            if "/newest/" in current_url and "archive." in current_url:
                if "No results" in page_content or "not been archived" in page_content:
                    browser.close()
                    return None

            # We should now be on an archived page
            html_content = page_content
            browser.close()

            if not html_content or len(html_content) < 1000:
                return None

        except Exception as e:
            browser.close()
            return None

    # Parse the archived content
    soup = BeautifulSoup(html_content, "html.parser")

    # Archive.is wraps content in a specific structure
    # Look for the archived page content
    archived_content = soup.find("div", id="CONTENT") or soup.find("body")

    if not archived_content:
        return None

    # Remove archive.is toolbar/header elements
    for el in soup.find_all(["div", "header", "nav"], class_=lambda x: x and any(
        kw in str(x).lower() for kw in ["toolbar", "archive", "header", "nav"]
    )):
        el.decompose()

    # Extract title
    title = None
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Clean up archive.is title suffix
        if " - archive" in title.lower():
            title = title.rsplit(" - ", 1)[0]

    h1_tag = soup.find("h1")
    if h1_tag:
        h1_text = h1_tag.get_text(strip=True)
        if h1_text and (not title or len(h1_text) > 10):
            title = h1_text

    # Find article content using standard selectors
    article_element = None
    for selector in ARTICLE_SELECTORS:
        article_element = soup.select_one(selector)
        if article_element:
            break

    if not article_element:
        article_element = soup.find("body")

    if not article_element:
        return None

    # Clean the content
    cleaned_html = clean_article_html(article_element)

    if not cleaned_html or len(cleaned_html.strip()) < 100:
        return None

    return {
        "title": title,
        "text": cleaned_html,
        "original_url": url,
        "source": "archive.is",
    }


def fetch_from_12ft_io(url):
    """
    Fetch article content from 12ft.io as a fallback for paywalls.
    
    12ft.io is a popular service that bypasses paywalls by stripping
    them from news articles.
    
    Args:
        url: The original article URL
        
    Returns:
        Dict with 'title', 'text', 'original_url', or None if failed
    """
    import urllib.parse
    
    encoded_url = urllib.parse.quote(url, safe="")
    proxy_url = f"https://12ft.io/{encoded_url}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        
        try:
            page.goto(proxy_url, wait_until="networkidle", timeout=30000)
            time.sleep(3)
            
            html_content = page.content()
            browser.close()
            
            if not html_content or len(html_content) < 2000:
                return None
                
        except Exception as e:
            browser.close()
            return None
    
    # Parse content
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 12ft.io usually puts content in a clean wrapper
    content_div = soup.find("div", class_=lambda x: x and "article" in str(x).lower())
    if not content_div:
        content_div = soup.find("article")
    if not content_div:
        content_div = soup.find("main")
    if not content_div:
        content_div = soup.find("body")
    
    if not content_div:
        return None
    
    # Extract title
    title = None
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
    
    h1_tag = soup.find("h1")
    if h1_tag:
        h1_text = h1_tag.get_text(strip=True)
        if h1_text and (not title or len(h1_text) > 10):
            title = h1_text
    
    # Clean content
    cleaned_html = clean_article_html(content_div)
    
    if not cleaned_html or len(cleaned_html.strip()) < 200:
        return None
    
    return {
        "title": title,
        "text": cleaned_html,
        "original_url": url,
        "source": "12ft.io",
    }


def fetch_from_textise_dot_iitty(url):
    """
    Fetch article content from textise dot iitty service.
    
    textise dot iitty converts articles to plain text, removing
    paywalls and formatting.
    
    Args:
        url: The original article URL
        
    Returns:
        Dict with 'title', 'text', 'original_url', or None if failed
    """
    import urllib.parse
    
    # textise dot iitty proxy service
    encoded_url = urllib.parse.quote(url, safe="")
    proxy_url = f"https://r.jina.ai/http://{url}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        
        try:
            page.goto(proxy_url, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            
            html_content = page.content()
            browser.close()
            
            if not html_content or len(html_content) < 1000:
                return None
                
        except Exception as e:
            browser.close()
            return None
    
    # Jina AI returns plain text content
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Extract content - usually in body
    body = soup.find("body")
    if not body:
        return None
    
    text_content = body.get_text(separator="\n\n", strip=True)
    
    # Try to extract title from first line
    lines = [l.strip() for l in text_content.split("\n") if l.strip()]
    title = None
    if lines:
        title = lines[0]
        if len(title) > 100:
            title = title[:100] + "..."
    
    # Convert text to HTML paragraphs
    paragraphs = text_content.split("\n\n")
    html_paragraphs = []
    for para in paragraphs[1:] if title else paragraphs:  # Skip title if extracted
        if len(para.strip()) > 20:
            html_paragraphs.append(f"<p>{escape_html(para.strip())}</p>")

    cleaned_html = sanitize_html("\n".join(html_paragraphs))
    
    if not cleaned_html or len(cleaned_html.strip()) < 200:
        return None
    
    return {
        "title": title,
        "text": cleaned_html,
        "original_url": url,
        "source": "jina.ai",
    }


def fetch_article_content(url):
    """
    Fetch article content using Playwright with anti-bot measures.

    Features:
    - User-Agent spoofing (looks like real Chrome on Mac)
    - 1920x1080 viewport
    - Blocks ads, analytics, images, media, fonts
    - Random delay to mimic human behavior
    - BeautifulSoup parsing with paywall element removal
    - Extracts text from article body

    Args:
        url: The article URL to fetch

    Returns:
        Dict with 'title', 'text', 'original_url', or None if fetch failed
    """
    paywall_detector = PaywallDetector()
    url_lower = url.lower()

    # Check if this is a hard paywall site
    is_hard_paywall = any(site in url_lower for site in HARD_PAYWALL_SITES)

    # Check if JavaScript should be disabled
    is_nytimes = "nytimes.com" in url_lower
    disable_js = (
        is_nytimes or
        paywall_detector.is_suspected_paywall(url) or
        paywall_detector.contains_gateway_patterns(url)
    )

    # Check if site needs Google referer
    use_google_referer = any(site in url_lower for site in GOOGLE_REFERER_SITES)

    # Check if site responds to crawler user agents (e.g., Substack)
    use_crawler_ua = any(site in url_lower for site in CRAWLER_BYPASS_SITES)

    def block_requests(route):
        """Intercept and block unwanted requests."""
        request = route.request
        resource_type = request.resource_type
        request_url = request.url.lower()

        # Block specified resource types
        if resource_type in BLOCKED_RESOURCE_TYPES:
            route.abort()
            return

        # Block ad/analytics domains
        for domain in BLOCKED_DOMAINS:
            if domain in request_url:
                route.abort()
                return

        # Allow all other requests
        route.continue_()

    def try_fetch_with_strategy(browser, user_agent, referer=None, js_enabled=True):
        """Try fetching with a specific strategy."""
        context_options = {
            "user_agent": user_agent,
            "viewport": {"width": 1920, "height": 1080},
            "java_script_enabled": js_enabled,
        }

        if referer:
            context_options["extra_http_headers"] = {
                "Referer": referer,
            }

        context = browser.new_context(**context_options)
        page = context.new_page()
        page.route("**/*", block_requests)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(random.uniform(1, 2))
            html = page.content()
            context.close()
            return html
        except Exception:
            context.close()
            return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        html_content = None

        # For hard paywall sites, try multiple strategies
        if is_hard_paywall:
            strategies = [
                # Try Googlebot with JS enabled (works for Athletic/NYT)
                (GOOGLEBOT_USER_AGENT, "https://www.google.com/", True),
                # Try Facebook crawler (best for social sharing previews)
                (FACEBOOK_USER_AGENT, "https://www.facebook.com/", False),
                # Try Twitter crawler
                (TWITTER_USER_AGENT, "https://t.co/", False),
                # Try Googlebot without JS
                (GOOGLEBOT_USER_AGENT, "https://www.google.com/", False),
                # Try normal with Google referer
                (USER_AGENT, "https://www.google.com/", not disable_js),
            ]

            for user_agent, referer, js_enabled in strategies:
                html_content = try_fetch_with_strategy(browser, user_agent, referer, js_enabled)
                if html_content and len(html_content) > 5000:
                    # Check if we got actual content (not just paywall page)
                    if "subscribe" not in html_content.lower()[:2000] or len(html_content) > 20000:
                        break
                html_content = None
        elif use_crawler_ua:
            # Sites that show full content to crawlers (e.g., Substack)
            html_content = try_fetch_with_strategy(
                browser, GOOGLEBOT_USER_AGENT, "https://www.google.com/", True
            )
        else:
            # Standard approach for other sites
            context_options = {
                "user_agent": USER_AGENT,
                "viewport": {"width": 1920, "height": 1080},
                "java_script_enabled": not disable_js,
            }

            if use_google_referer:
                context_options["extra_http_headers"] = {
                    "Referer": "https://www.google.com/",
                }

            context = browser.new_context(**context_options)
            page = context.new_page()
            page.route("**/*", block_requests)

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                delay = random.uniform(1, 3)
                time.sleep(delay)
                html_content = page.content()
            except Exception:
                browser.close()
                return None

        browser.close()

    # Check if content is blocked (Access Denied, 403, etc.)
    content_blocked = False
    if html_content:
        content_lower = html_content.lower()
        if "access denied" in content_lower or "403 forbidden" in content_lower:
            content_blocked = True
            html_content = None

    # For hard paywall sites, try Selenium fallback before archive.is
    if not html_content and is_hard_paywall:
        selenium_html = fetch_with_selenium_no_js(url)
        if selenium_html:
            # Check if Selenium got blocked too
            selenium_lower = selenium_html.lower()
            if "access denied" not in selenium_lower and "403 forbidden" not in selenium_lower:
                html_content = selenium_html

    # If still no content, try alternative bypass services
    if not html_content:
        if is_hard_paywall:
            # Try archive.is
            archive_result = fetch_from_archive_is(url)
            if archive_result:
                return archive_result
            
            # Try 12ft.io
            result_12ft = fetch_from_12ft_io(url)
            if result_12ft:
                return result_12ft
            
            # Try Jina AI summarizer as last resort
            result_jina = fetch_from_textise_dot_iitty(url)
            if result_jina:
                return result_jina
        return None

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove paywall elements - collect first, then remove
    # Skip content elements (p, h1-h6, etc.) - some sites like Wired mark content with "paywall" class
    CONTENT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li", "hr"}
    elements_to_remove = []
    for element in soup.find_all(True):
        if element is None:
            continue

        # Skip content elements - they contain actual article text
        if element.name in CONTENT_TAGS:
            continue

        # Check class attribute
        classes = element.get("class", [])
        if isinstance(classes, list):
            class_str = " ".join(classes).lower()
        else:
            class_str = str(classes).lower()

        # Check id attribute
        element_id = element.get("id", "") or ""
        element_id = element_id.lower()

        # Mark for removal if matches paywall patterns
        for pattern in PAYWALL_ELEMENT_PATTERNS:
            if pattern in class_str or pattern in element_id:
                elements_to_remove.append(element)
                break

    # Remove collected elements
    for element in elements_to_remove:
        try:
            element.decompose()
        except Exception:
            pass

    # Extract title
    title = None
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Try h1 if title is generic or missing
    h1_tag = soup.find("h1")
    if h1_tag:
        h1_text = h1_tag.get_text(strip=True)
        if h1_text and (not title or len(h1_text) > 10):
            title = h1_text

    # Find article content element with minimum content threshold
    # Some sites have small <article> elements for widgets/sidebars
    MIN_CONTENT_LENGTH = 500
    article_element = None
    cleaned_html = None

    for selector in ARTICLE_SELECTORS:
        candidate = soup.select_one(selector)
        if candidate:
            candidate_html = clean_article_html(candidate)
            if candidate_html and len(candidate_html) >= MIN_CONTENT_LENGTH:
                article_element = candidate
                cleaned_html = candidate_html
                break

    # If no selector met threshold, try body
    if not article_element:
        body = soup.find("body")
        if body:
            article_element = body
            cleaned_html = clean_article_html(body)

    if not article_element or not cleaned_html:
        return None

    # Check if content looks like a CAPTCHA/security page
    def looks_like_captcha(html_content):
        """Detect if content is a CAPTCHA or security challenge page."""
        if not html_content:
            return False
        content_lower = html_content.lower()
        captcha_phrases = [
            "one more step",
            "security check",
            "captcha",
            "please complete",
            "verify you are human",
            "cloudflare",
            "access denied",
            "403 forbidden",
        ]
        return any(phrase in content_lower for phrase in captcha_phrases)

    # Check if content looks like a paywall page
    def looks_like_paywall(html_content):
        """Detect if content appears to be a paywall page."""
        if not html_content:
            return True
        content_lower = html_content.lower()
        # Common paywall phrases
        paywall_phrases = [
            "subscribe to continue",
            "subscribe to read",
            "subscribers only",
            "subscription required",
            "become a subscriber",
            "sign up to continue",
            "create an account to continue",
            "register to continue reading",
            "this article is for subscribers",
            "to read the full story",
            "already a subscriber?",
        ]
        phrase_count = sum(1 for phrase in paywall_phrases if phrase in content_lower)
        # If multiple paywall phrases or content is very short with one phrase
        return phrase_count >= 2 or (phrase_count >= 1 and len(html_content) < 500)

    # Reject CAPTCHA pages entirely
    if looks_like_captcha(cleaned_html):
        return None

    if not cleaned_html or len(cleaned_html.strip()) < 50 or (is_hard_paywall and looks_like_paywall(cleaned_html)):
        # For hard paywall sites, try archive.is as fallback
        if is_hard_paywall:
            archive_result = fetch_from_archive_is(url)
            if archive_result:
                # Also extract images and summary from archive result
                archive_soup = BeautifulSoup(archive_result["text"], "html.parser")
                archive_result["images"] = extract_article_images(archive_soup, url)
                archive_result["summary"] = generate_article_summary(archive_result["text"])
                return archive_result
        return None

    # Extract images from the article
    article_images = extract_article_images(soup, url)
    
    # Generate summary
    article_summary = generate_article_summary(cleaned_html)

    return {
        "title": title,
        "text": cleaned_html,
        "original_url": url,
        "images": article_images,
        "summary": article_summary,
    }


def clean_article_html(element):
    """
    Clean article HTML: remove links, images, and unwanted elements.
    Preserve headlines, paragraphs, blockquotes, lists, and section separators.

    Args:
        element: BeautifulSoup element containing article content

    Returns:
        Cleaned HTML string with proper formatting
    """
    # Create a copy to avoid modifying the original
    soup = BeautifulSoup(str(element), "html.parser")

    # Elements to completely remove
    REMOVE_TAGS = [
        "script", "style", "noscript", "iframe", "embed", "object",
        "nav", "footer", "header", "aside", "form", "button", "input",
        "img", "picture", "figure", "figcaption", "svg", "canvas", "video", "audio",
        "advertisement", "ad", "social-share", "share-buttons", "related-articles",
    ]

    # Remove unwanted elements
    for tag in REMOVE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # Remove elements with paywall/ad classes
    elements_to_remove = []
    # Content elements should not be removed even if they match patterns
    # (e.g., Wired marks content paragraphs with class="paywall")
    CONTENT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li", "hr"}
    for el in soup.find_all(True):
        if el is None:
            continue
        # Skip content elements - they contain the actual article text
        if el.name in CONTENT_TAGS:
            continue
        classes = el.get("class", [])
        if isinstance(classes, list):
            class_str = " ".join(classes).lower()
        else:
            class_str = str(classes).lower()

        element_id = (el.get("id", "") or "").lower()

        # Check for patterns to remove
        # Note: patterns should be specific to avoid false positives
        # e.g., "ad-" would match "lead-article", so use "ad-slot", "ad-container" etc.
        remove_patterns = [
            "paywall", "subscribe", "advertisement", "ad-slot", "ad-container",
            "ad-wrapper", "social-share", "share-button",
            "related-articles", "newsletter", "signup", "popup", "modal",
            "sidebar", "comment", "footer-", "header-nav", "nav-bar", "menu-",
            "author-bio", "byline-", "metadata", "timestamp",
        ]

        for pattern in remove_patterns:
            if pattern in class_str or pattern in element_id:
                elements_to_remove.append(el)
                break

    for el in elements_to_remove:
        try:
            el.decompose()
        except Exception:
            pass

    # Convert links to plain text (preserve the link text, remove the href)
    for a_tag in soup.find_all("a"):
        a_tag.unwrap()

    # Check if we have proper semantic elements with actual content
    # Only count elements that have meaningful text (not just hr tags)
    text_elements = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"])
    total_text_length = sum(len(el.get_text(strip=True)) for el in text_elements)

    # If we have substantial text in semantic elements, use them
    if total_text_length > 200:
        return sanitize_html(extract_semantic_content(soup))

    # Fallback for legacy HTML (like paulgraham.com) - extract text and create paragraphs
    return sanitize_html(extract_legacy_content(soup))


def extract_semantic_content(soup):
    """Extract content from HTML with proper semantic elements (p, h1-h6, etc.)."""
    output_parts = []
    seen_text = set()

    for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "ul", "ol", "hr"]):
        if el.name == "hr":
            output_parts.append("<hr>")
            continue

        text = el.get_text(strip=True)

        if not text or len(text) < 3:
            continue

        text_hash = hash(text[:100])
        if text_hash in seen_text:
            continue
        seen_text.add(text_hash)

        # Skip navigation/menu items
        skip_patterns = [
            "skip to", "jump to", "read more", "continue reading",
            "sign up", "subscribe", "log in", "sign in", "newsletter",
            "share this", "follow us", "advertisement", "sponsored",
        ]
        text_lower = text.lower()
        if any(pattern in text_lower for pattern in skip_patterns) and len(text) < 50:
            continue

        if el.name in ["ul", "ol"]:
            list_items = []
            for li in el.find_all("li"):
                li_text = li.get_text(strip=True)
                if li_text:
                    list_items.append(f"<li>{escape_html(li_text)}</li>")
            if list_items:
                output_parts.append(f"<{el.name}>{''.join(list_items)}</{el.name}>")
            continue

        if el.name == "blockquote":
            output_parts.append(f"<blockquote><p>{escape_html(text)}</p></blockquote>")
            continue

        if el.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            output_parts.append(f"<{el.name}>{escape_html(text)}</{el.name}>")
            continue

        output_parts.append(f"<p>{escape_html(text)}</p>")

    return "\n".join(output_parts)


def extract_legacy_content(soup):
    """Extract content from legacy HTML without proper semantic elements."""
    # Get all text, preserving line breaks
    # Replace <br> tags with newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Get text content
    text = soup.get_text(separator="\n", strip=False)

    # Clean up the text
    lines = text.split("\n")
    paragraphs = []
    current_para = []

    for line in lines:
        line = line.strip()
        if not line:
            # Empty line - end current paragraph
            if current_para:
                para_text = " ".join(current_para)
                if len(para_text) > 10:  # Only keep substantial paragraphs
                    paragraphs.append(para_text)
                current_para = []
        else:
            current_para.append(line)

    # Don't forget the last paragraph
    if current_para:
        para_text = " ".join(current_para)
        if len(para_text) > 10:
            paragraphs.append(para_text)

    # Skip navigation/menu items
    skip_patterns = [
        "skip to", "jump to", "read more", "continue reading",
        "sign up", "subscribe", "log in", "sign in", "newsletter",
        "share this", "follow us", "advertisement", "sponsored",
        "copyright", "all rights reserved", "privacy policy",
    ]

    # Build HTML output
    output_parts = []
    seen_text = set()

    for para in paragraphs:
        # Skip duplicates
        text_hash = hash(para[:100])
        if text_hash in seen_text:
            continue
        seen_text.add(text_hash)

        # Skip navigation items
        para_lower = para.lower()
        if any(pattern in para_lower for pattern in skip_patterns) and len(para) < 50:
            continue

        output_parts.append(f"<p>{escape_html(para)}</p>")

    return "\n".join(output_parts)


def escape_html(text):
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# Tags allowed in sanitized article HTML (no attributes permitted)
SAFE_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "hr",
    "br", "em", "strong", "b", "i", "sub", "sup",
}


def sanitize_html(html_content):
    """
    Sanitize HTML to prevent stored XSS while preserving article formatting.

    Uses nh3 to strip all tags except a safe whitelist and removes all
    attributes (no onclick, onerror, style, etc.).
    """
    if not html_content:
        return html_content
    return nh3.clean(html_content, tags=SAFE_TAGS, attributes={})


# Ad/tracking image patterns to filter out
AD_IMAGE_PATTERNS = [
    "adsystem",
    "adservice",
    "googlesyndication",
    "doubleclick",
    "googletag",
    "facebook.com/tr",
    "analytics",
    "tracking",
    "beacon",
    "pixel",
    "ads",
    "advertisement",
    "sponsored",
    "affiliate",
    "banner",
    "popup",
    "newsletter-signup",
    "social-share",
    "icon-",
    "logo-",
    "avatar",
    "profile-pic",
    "author-image",
    "emoji",
    "icon_",
    "_icon",
    "button",
    "cta-",
    "subscribe",
    "download-app",
]

# Good image indicators (likely article content)
GOOD_IMAGE_PATTERNS = [
    "article",
    "feature",
    "hero",
    "lead",
    "main",
    "content",
    "story",
    "photo",
    "image",
    "gallery",
    "caption",
    "illustration",
    "diagram",
    "chart",
    "infographic",
]

# Minimum image dimensions to consider (avoid tiny icons)
MIN_IMAGE_WIDTH = 150
MIN_IMAGE_HEIGHT = 100


def is_likely_ad_image(img_tag, img_url="", img_classes="", img_alt=""):
    """
    Determine if an image is likely an ad or non-content image.
    
    Args:
        img_tag: BeautifulSoup img tag
        img_url: Image URL
        img_classes: Image CSS classes
        img_alt: Image alt text
    
    Returns:
        True if likely an ad/unwanted image, False if likely content
    """
    url_lower = img_url.lower()
    classes_lower = img_classes.lower()
    alt_lower = img_alt.lower()
    
    # Check for ad patterns in URL
    for pattern in AD_IMAGE_PATTERNS:
        if pattern in url_lower:
            return True
        if pattern in classes_lower:
            return True
        if pattern in alt_lower and len(alt_lower) < 50:
            return True
    
    # Check parent element for ad indicators
    parent = img_tag.find_parent() if img_tag else None
    if parent:
        parent_classes = parent.get("class", [])
        if isinstance(parent_classes, list):
            parent_classes = " ".join(parent_classes)
        parent_classes = parent_classes.lower()
        for pattern in ["ad", "advertisement", "sponsored", "promo", "newsletter"]:
            if pattern in parent_classes:
                return True
    
    # Check dimensions if available (tiny images are likely icons)
    width = img_tag.get("width", "") if img_tag else ""
    height = img_tag.get("height", "") if img_tag else ""
    
    # Try to extract numeric dimensions
    try:
        w = int("".join(filter(str.isdigit, str(width)))) if width else 0
        h = int("".join(filter(str.isdigit, str(height)))) if height else 0
        if 0 < w < 100 or 0 < h < 80:
            return True  # Likely an icon
    except (ValueError, TypeError):
        pass
    
    return False


def is_likely_content_image(img_tag, img_url="", img_classes="", img_alt=""):
    """
    Determine if an image is likely article content (photo, illustration, etc.).
    
    Args:
        img_tag: BeautifulSoup img tag
        img_url: Image URL
        img_classes: Image CSS classes
        img_alt: Image alt text
    
    Returns:
        True if likely content image, False otherwise
    """
    url_lower = img_url.lower()
    classes_lower = img_classes.lower()
    alt_lower = img_alt.lower()
    
    # Check for good content patterns
    for pattern in GOOD_IMAGE_PATTERNS:
        if pattern in url_lower or pattern in classes_lower:
            return True
    
    # Descriptive alt text suggests content image
    if len(img_alt) > 20 and not any(p in alt_lower for p in ["advertisement", "sponsored", "click here"]):
        return True
    
    # Large images are likely content
    width = img_tag.get("width", "") if img_tag else ""
    height = img_tag.get("height", "") if img_tag else ""
    
    try:
        w = int("".join(filter(str.isdigit, str(width)))) if width else 0
        h = int("".join(filter(str.isdigit, str(height)))) if height else 0
        if w >= 400 or h >= 300:
            return True
    except (ValueError, TypeError):
        pass
    
    # Check if inside article content area
    parent = img_tag.find_parent() if img_tag else None
    if parent:
        article_parents = ["article", "main", "[role='main']", ".post-content", ".article-content", ".entry-content"]
        for selector in article_parents:
            # Simple check - in real implementation would use proper CSS selector
            parent_tag = parent.name.lower() if parent.name else ""
            if parent_tag in ["article", "main"]:
                return True
    
    return False


def extract_article_images(soup, base_url=""):
    """
    Extract content images from article HTML, filtering out ads and icons.
    
    Args:
        soup: BeautifulSoup object of the article
        base_url: Base URL for resolving relative image URLs
    
    Returns:
        List of dicts with image info: {'url': ..., 'alt': ..., 'caption': ...}
    """
    images = []
    seen_urls = set()
    
    # Find all image tags
    img_tags = soup.find_all(["img", "picture"])
    
    for img in img_tags:
        # Get image source
        img_url = (img.get("src") or 
                   img.get("data-src") or 
                   img.get("data-original") or
                   img.get("data-lazy-src") or
                   "")
        
        # Check for source tag in picture elements
        if img.name == "picture":
            sources = img.find_all("source")
            for source in sources:
                srcset = source.get("srcset", "")
                if srcset:
                    # Take first srcset URL
                    img_url = srcset.split(",")[0].split()[0]
                    break
            if not img_url:
                img_in_picture = img.find("img")
                if img_in_picture:
                    img_url = (img_in_picture.get("src") or 
                               img_in_picture.get("data-src") or "")
        
        if not img_url:
            continue
        
        # Skip data URIs (usually tiny icons)
        if img_url.startswith("data:"):
            continue
        
        # Resolve relative URLs
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        elif img_url.startswith("/"):
            from urllib.parse import urljoin
            img_url = urljoin(base_url, img_url)
        
        # Skip duplicates
        if img_url in seen_urls:
            continue
        seen_urls.add(img_url)
        
        # Get image metadata
        img_classes = img.get("class", [])
        if isinstance(img_classes, list):
            img_classes = " ".join(img_classes)
        
        img_alt = img.get("alt", "") or ""
        
        # Filter out ad images
        if is_likely_ad_image(img, img_url, img_classes, img_alt):
            continue
        
        # Look for caption
        caption = ""
        # Check for figcaption
        parent_figure = img.find_parent("figure")
        if parent_figure:
            figcaption = parent_figure.find("figcaption")
            if figcaption:
                caption = figcaption.get_text(strip=True)
        
        # Check for common caption classes
        if not caption:
            parent = img.find_parent()
            if parent:
                caption_el = (parent.find(class_=lambda x: x and "caption" in str(x).lower()) or
                             parent.find(class_=lambda x: x and "credit" in str(x).lower()))
                if caption_el:
                    caption = caption_el.get_text(strip=True)
        
        images.append({
            "url": img_url,
            "alt": img_alt,
            "caption": caption,
        })
    
    # Sort to prioritize likely content images first
    def image_priority(img_info):
        score = 0
        if img_info["caption"]:
            score += 10
        if len(img_info["alt"]) > 20:
            score += 5
        if any(p in img_info["url"].lower() for p in GOOD_IMAGE_PATTERNS):
            score += 3
        return -score  # Negative for descending sort
    
    images.sort(key=image_priority)
    
    # Limit to reasonable number (avoid galleries overwhelming)
    return images[:8]


def generate_article_summary(html_content, max_sentences=5):
    """
    Generate a summary of article content by extracting key sentences.
    
    Uses a simple algorithm:
    - Extract first paragraph (usually the lede)
    - Look for sentences containing important keywords
    - Prioritize sentences early in the article
    
    Args:
        html_content: HTML content of the article
        max_sentences: Maximum number of sentences in summary
    
    Returns:
        Summary text string
    """
    from bs4 import BeautifulSoup
    import re
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Get all paragraph text
    paragraphs = soup.find_all(["p", "h2", "h3", "h4"])
    
    if not paragraphs:
        return ""
    
    # Collect all sentences with their position
    sentences_with_pos = []
    position = 0
    
    for p in paragraphs:
        text = p.get_text(strip=True)
        if not text:
            continue
        
        # Split into sentences (simple approach)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 40 and len(sent) < 300:  # Reasonable sentence length
                sentences_with_pos.append((position, sent))
                position += 1
    
    if not sentences_with_pos:
        return ""
    
    # Score sentences
    def score_sentence(pos_sent):
        pos, sent = pos_sent
        score = 0
        sent_lower = sent.lower()
        
        # Position bonus (earlier sentences more important)
        if pos == 0:
            score += 100  # First sentence is usually the lede
        elif pos < 3:
            score += 50
        elif pos < 6:
            score += 20
        
        # Length preference - not too short, not too long
        words = len(sent.split())
        if 15 <= words <= 40:
            score += 10
        
        # Content indicators
        important_terms = [
            "announced", "released", "reported", "said", "according to",
            "study", "research", "found", "discovered", "revealed",
            "new", "first", "major", "significant", "important",
            "will", "plans to", "expected", "predicted",
            "because", "due to", "caused by", "result of",
            "however", "although", "despite", "while",
            "for example", "such as", "including",
            "company", "organization", "government", "officials",
            "million", "billion", "percent", "growth", "decline",
        ]
        for term in important_terms:
            if term in sent_lower:
                score += 5
        
        # Penalize certain patterns
        skip_patterns = [
            "read more", "click here", "sign up", "subscribe",
            "follow us", "share this", "related articles",
            "advertisement", "sponsored", "click to",
            "image credit", "photo by", "source:",
        ]
        for pattern in skip_patterns:
            if pattern in sent_lower:
                score -= 50
        
        return score
    
    # Score and sort
    scored = [(score_sentence(s), s[1]) for s in sentences_with_pos]
    scored.sort(reverse=True)
    
    # Take top sentences
    top_sentences = [s[1] for s in scored[:max_sentences]]
    
    # Re-sort by original position for coherent flow
    original_order = []
    for sent in top_sentences:
        for pos, original_sent in sentences_with_pos:
            if sent == original_sent:
                original_order.append((pos, sent))
                break
    
    original_order.sort()
    
    summary = " ".join([s[1] for s in original_order])
    return summary


class PaywallDetector:
    """Detect paywalled sites and paywall gateway patterns in URLs."""

    # Known paywalled site patterns
    PAYWALL_SITES = [
        r"nytimes\.com",
        r"wsj\.com",
        r"medium\.com",
        r"washingtonpost\.com",
        r"hbr\.org",
        r"economist\.com",
        r"ft\.com",
        r"bloomberg\.com",
        r"theatlantic\.com",
        r"newyorker\.com",
        r"wired\.com",
        r"thetimes\.co\.uk",
        r"telegraph\.co\.uk",
        # Additional news sites
        r"theguardian\.com",
        r"latimes\.com",
        r"chicagotribune\.com",
        r"bostonglobe\.com",
        r"seattletimes\.com",
        r"mercurynews\.com",
        r"denverpost\.com",
        r"dallasnews\.com",
        r"inquirer\.com",
        r"startribune\.com",
        r"jsonline\.com",
        # Business/Financial
        r"businessinsider\.com",
        r"forbes\.com",
        r"marketwatch\.com",
        r"seekingalpha\.com",
        r"barrons\.com",
        r"financialpost\.com",
        r"morningstar\.com",
        r"kiplinger\.com",
        r"fortune\.com",
        r"fastcompany\.com",
        r"inc\.com",
        r"entrepreneur\.com",
        # Technology/Science
        r"technologyreview\.com",
        r"scientificamerican\.com",
        r"nature\.com",
        r"science\.org",
        r"ieee\.org",
        r"acm\.org",
        r"spectrum\.ieee\.org",
        r"newscientist\.com",
        # Premium news
        r"foreignpolicy\.com",
        r"theinformation\.com",
        r"axios\.com",
        r"politico\.com",
        r"statnews\.com",
        r"law360\.com",
        r"propublica\.org",
        # International
        r"irishtimes\.com",
        r"spiegel\.de",
        r"zeit\.de",
        r"faz\.net",
        r"lemonde\.fr",
        r"corriere\.it",
        r"elpais\.com",
        r"scmp\.com",
        r"afr\.com",
        r"theaustralian\.com\.au",
        r"smh\.com\.au",
        # Magazines
        r"vanityfair\.com",
        r"gq\.com",
        r"esquire\.com",
        r"time\.com",
        r"rollingstone\.com",
        r"billboard\.com",
        # Academic
        r"chronicle\.com",
        r"insidehighered\.com",
        r"timeshighereducation\.com",
        r"jstor\.org",
        # Sports
        r"theathletic\.com",
        r"espn\.com",
        r"espnplus\.com",
        # Entertainment
        r"variety\.com",
        r"hollywoodreporter\.com",
        r"deadline\.com",
        r"pitchfork\.com",
        r"vulture\.com",
    ]

    # URL path patterns that indicate paywall gateways
    GATEWAY_PATTERNS = [
        r"/subscribe",
        r"/subscription",
        r"/pay",
        r"/payment",
        r"/login",
        r"/signin",
        r"/sign-in",
        r"/premium",
        r"/member",
        r"/membership",
        r"/register",
        r"/checkout",
        r"/unlock",
        r"/access",
    ]

    def __init__(self):
        # Compile regex patterns for better performance
        self._site_pattern = re.compile(
            "|".join(self.PAYWALL_SITES), re.IGNORECASE
        )
        self._gateway_pattern = re.compile(
            "|".join(self.GATEWAY_PATTERNS), re.IGNORECASE
        )

    def is_suspected_paywall(self, url):
        """
        Check if URL is from a known paywalled site.

        Args:
            url: The URL string to check

        Returns:
            True if the URL matches a known paywall site pattern
        """
        if not url:
            return False
        return bool(self._site_pattern.search(url))

    def contains_gateway_patterns(self, url):
        """
        Check if URL path contains paywall gateway keywords.

        Args:
            url: The URL string to check

        Returns:
            True if the URL contains gateway patterns like /subscribe, /pay, etc.
        """
        if not url:
            return False
        return bool(self._gateway_pattern.search(url))

    def analyze(self, url):
        """
        Full analysis of a URL for paywall indicators.

        Args:
            url: The URL string to analyze

        Returns:
            Dict with analysis results
        """
        return {
            "url": url,
            "is_paywall_site": self.is_suspected_paywall(url),
            "has_gateway_pattern": self.contains_gateway_patterns(url),
        }


if __name__ == "__main__":
    # Test the PaywallDetector
    detector = PaywallDetector()

    test_urls = [
        "https://www.nytimes.com/2024/01/15/technology/ai-news.html",
        "https://www.wsj.com/articles/stock-market-today",
        "https://medium.com/@user/my-article-123",
        "https://www.washingtonpost.com/politics/2024/story.html",
        "https://hbr.org/2024/01/leadership-article",
        "https://www.bbc.com/news/world-12345",
        "https://www.paulgraham.com/read.html",
        "https://example.com/subscribe/premium",
        "https://news.site.com/login?redirect=/article",
        "https://blog.example.com/free-article",
    ]

    print("PaywallDetector Test Results")
    print("=" * 70)

    for url in test_urls:
        result = detector.analyze(url)
        paywall = "Yes" if result["is_paywall_site"] else "No"
        gateway = "Yes" if result["has_gateway_pattern"] else "No"
        print(f"\nURL: {url}")
        print(f"  Paywall site: {paywall}")
        print(f"  Gateway pattern: {gateway}")

    print("\n" + "=" * 70)

    # Test fetch_article_content
    print("\nTesting fetch_article_content...")
    print("=" * 70)
    test_url = "https://www.paulgraham.com/read.html"
    print(f"Fetching: {test_url}")
    print("(This will take a few seconds due to human-mimicking delay...)")

    result = fetch_article_content(test_url)
    if result:
        print(f"\nSuccess!")
        print(f"  Title: {result['title']}")
        print(f"  URL: {result['original_url']}")
        print(f"  Text length: {len(result['text'])} characters")
        print(f"\n  First 300 chars of text:")
        print(f"  {result['text'][:300]}...")
    else:
        print("Failed to fetch content")

    print("\n" + "=" * 70)

    # Test fetch_with_selenium_no_js
    print("\nTesting fetch_with_selenium_no_js...")
    print("=" * 70)
    test_url = "https://www.paulgraham.com/read.html"
    print(f"Fetching with Selenium (JS disabled): {test_url}")
    print("(This will auto-install GeckoDriver on first run...)")

    html = fetch_with_selenium_no_js(test_url)
    if html:
        print(f"\nSuccess!")
        print(f"  HTML length: {len(html)} characters")
        # Quick check for content
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title")
        print(f"  Title: {title.get_text(strip=True) if title else 'N/A'}")
    else:
        print("Failed to fetch content")

    print("\n" + "=" * 70)
    print("All tests complete!")
