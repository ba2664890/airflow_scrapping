import scrapy
from scrapy.spiders import Spider
from scrapy.http import Request
from scrapy_playwright.page import PageMethod
from scrapy.loader import ItemLoader
from Emploi_senegal.items import emploidakar
import hashlib

class EmploiDakarSpider(Spider):
    name = "emploidakar"
    allowed_domains = ["emploidakar.com"]
    start_urls = ["https://www.emploidakar.com/offres-demploi-au-senegal/"]

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS": 1,
        "ROBOTSTXT_OBEY": False,
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Referer": "https://www.emploidakar.com",
        },
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True, "timeout": 30_000},
        "ITEM_PIPELINES": {
            "Emploi_senegal.pipelines.DuplicatesPipeline": 100,
            "Emploi_senegal.pipelines.SQLAlchemyPipeline": 400,
        }
    }

    

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_selector", "ul.job_listings li.job_listing", timeout=10_000)
                    ],
                    "playwright_navigate_timeout": 15_000,
                    "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
                },
                callback=self.parse,
                errback=self.err_listing,
            )

    def err_listing(self, failure):
        self.logger.warning("LISTING TIMEOUT/ERROR : %s", failure.request.url)

    def parse(self, response):
        # 1) cartes page 1
        yield from self._cards(response)

        # 2) vraie pagination WP Job Manager
        for p in range(2, 18):          # 17 pages vues dans la pagination
            ajax_url = (
                f"https://www.emploidakar.com/jm-ajax/get_listings/"
                f"?page={p}&per_page=15&orderby=featured&order=DESC"
            )
            self.logger.info("AJAX URL = %s", ajax_url)
            yield scrapy.Request(
                ajax_url,
                callback=self.parse_ajax,
                headers={"X-Requested-With": "XMLHttpRequest",
                        "Referer": "https://www.emploidakar.com/offres-demploi-au-senegal/"},
                meta={"handle_httpstatus_list": [404, 500]},
            )

    def parse_ajax(self, response):
        if response.status != 200:
            self.logger.warning("AJAX HTTP %s → %s", response.status, response.url)
            return
        # WP Job Manager renvoie un JSON { html: "..."  }
        data = response.json()
        html_fragment = data.get("html", "")
        if not html_fragment.strip():
            return
        selector = scrapy.Selector(text=html_fragment, type="html")
        yield from self._cards(selector)  

    def _cards(self, selector):
        """Extrait les liens détail depuis n’importe quel fragment."""
        for li in selector.css("li.job_listing"):
            href = li.css("a::attr(href)").get()
            if href:
                yield scrapy.Request(
                    href.strip(),          # enlève les éventuels espaces
                    callback=self.parse_detail,
                    meta={
                        "playwright": True,
                        "playwright_page_methods": [
                            PageMethod("wait_for_selector", "div.job_description", timeout=10_000)
                        ],
                        "playwright_navigate_timeout": 15_000,
                        "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
                    },
                    errback=self.err_detail,
                )

    def err_detail(self, failure):
        self.logger.warning("Détail timeout/erreur : %s", failure.request.url)


    def parse_detail(self, response):
        loader = ItemLoader(item=emploidakar(), response=response)
        loader.add_css("title", "h1.entry-title::text")
        loader.add_css("location", "li.location a::text")
        loader.add_css("contract_type", "li.job-type::text")
        loader.add_css("posted_date", "li.date-posted time::attr(datetime)")
        loader.add_css("company_name", "div.company_header strong::text")
        loader.add_css("company_logo", "div.company img.company_logo::attr(src)")
        loader.add_value("url", response.url)
        loader.add_value("source", "emploidakar")
        loader.add_value("id", hashlib.md5(response.url.encode()).hexdigest())
        loader.add_css("description_p", "div.job_description p::text")
        for ul in response.css("div.job_description ul"):
            loader.add_value("description_ul", " ".join(ul.css("::text").getall()).strip())
        return loader.load_item()