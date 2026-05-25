"""
URL-based paywall detection.

A lightweight, regex-only classifier — no network calls. Used by the
fetcher to decide whether to apply paywall-bypass strategies before
falling back to a normal fetch.
"""
import re


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
        self._site_pattern = re.compile("|".join(self.PAYWALL_SITES), re.IGNORECASE)
        self._gateway_pattern = re.compile("|".join(self.GATEWAY_PATTERNS), re.IGNORECASE)

    def is_suspected_paywall(self, url):
        if not url:
            return False
        return bool(self._site_pattern.search(url))

    def contains_gateway_patterns(self, url):
        if not url:
            return False
        return bool(self._gateway_pattern.search(url))

    def analyze(self, url):
        return {
            "url": url,
            "is_paywall_site": self.is_suspected_paywall(url),
            "has_gateway_pattern": self.contains_gateway_patterns(url),
        }
