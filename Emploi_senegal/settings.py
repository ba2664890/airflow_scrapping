BOT_NAME = "Emploi_senegal"

SPIDER_MODULES = ["Emploi_senegal.spiders"]
NEWSPIDER_MODULE = "Emploi_senegal.spiders"

# Playwright
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
DOWNLOAD_HANDLERS = {
    "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
PLAYWRIGHT_BROWSER_TYPE = "firefox"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True, "timeout": 30_000}
PLAYWRIGHT_CONTEXT_ARGS = {"viewport": {"width": 1366, "height": 768}}

# Politesse
ROBOTSTXT_OBEY = False
DOWNLOAD_DELAY = 2
CONCURRENT_REQUESTS = 1

custom_settings = {
    "DOWNLOAD_DELAY": 1,
    # ↓↓↓  ESSENTIEL  ↓↓↓
    "DOWNLOAD_HANDLERS": {
        'http': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
        'https': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
    },
    "PLAYWRIGHT_BROWSER_TYPE": "firefox",
    "PLAYWRIGHT_LAUNCH_OPTIONS": {
        "headless": True,
    },
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",  # déjà OK
}


# --- configuration par pipeline ---------------------------------------------


DATABASE = {
    "database": "scrapy_immo",
    "user":     "Cardan",
    "password": "Fatimata05?",
    "host":     "localhost",
    "port":     5432,
}

# Désactivez les logs trop verbeux
LOG_LEVEL = "INFO"