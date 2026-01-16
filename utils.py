import re
import time
import random
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

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

    # Check if JavaScript should be disabled
    # Specifically disable JS for nytimes.com and other paywall sites
    is_nytimes = "nytimes.com" in url.lower()
    disable_js = (
        is_nytimes or
        paywall_detector.is_suspected_paywall(url) or
        paywall_detector.contains_gateway_patterns(url)
    )

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

    with sync_playwright() as p:
        # Launch headless Chromium
        browser = p.chromium.launch(headless=True)

        # Create context with spoofed User-Agent and viewport
        # Specifically disable JavaScript for nytimes.com and paywall sites
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=not disable_js,
        )

        page = context.new_page()

        # Set up request interception for ad blocking
        page.route("**/*", block_requests)

        try:
            # Navigate to URL and wait for content
            page.goto(url, wait_until="networkidle", timeout=30000)

            # Random delay to mimic human reading (1-3 seconds)
            delay = random.uniform(1, 3)
            time.sleep(delay)

            # Get the full HTML content
            html_content = page.content()

        except Exception as e:
            browser.close()
            return None

        browser.close()

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove paywall elements - collect first, then remove
    elements_to_remove = []
    for element in soup.find_all(True):
        if element is None:
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

    # Find article content element
    article_element = None
    for selector in ARTICLE_SELECTORS:
        article_element = soup.select_one(selector)
        if article_element:
            break

    # Fallback to body
    if not article_element:
        article_element = soup.find("body")

    if not article_element:
        return None

    # Clean up the article content
    cleaned_html = clean_article_html(article_element)

    if not cleaned_html or len(cleaned_html.strip()) < 50:
        return None

    return {
        "title": title,
        "text": cleaned_html,
        "original_url": url,
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
    for el in soup.find_all(True):
        if el is None:
            continue
        classes = el.get("class", [])
        if isinstance(classes, list):
            class_str = " ".join(classes).lower()
        else:
            class_str = str(classes).lower()

        element_id = (el.get("id", "") or "").lower()

        # Check for patterns to remove
        remove_patterns = [
            "paywall", "subscribe", "advertisement", "ad-", "social",
            "share", "related", "newsletter", "signup", "popup", "modal",
            "sidebar", "comment", "footer", "header", "nav", "menu",
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
        return extract_semantic_content(soup)

    # Fallback for legacy HTML (like paulgraham.com) - extract text and create paragraphs
    return extract_legacy_content(soup)


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
