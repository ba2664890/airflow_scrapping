from unittest import loader
import scrapy, re
from scrapy.loader import ItemLoader
from itemloaders.processors import MapCompose, TakeFirst
import scrapy_playwright
from Emploi_senegal.items import JobItem


class Emploi_senegalSpider(scrapy.Spider):
    name = "Emploi_senegal"
    allowed_domains = ["emploisenegal.com"]
    start_urls = ["https://www.emploisenegal.com/recherche-jobs-senegal"]

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
            "Referer": "https://www.emploisenegal.com",
        },
        # Playwright
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "http":  "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "firefox",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True, "timeout": 30_000},
        "ITEM_PIPELINES": {
            "Emploi_senegal.pipelines.DuplicatesPipeline": 100,
            "Emploi_senegal.pipelines.EmploiSenegalPostgreSQLPipeline": 400,
        }

    }

    # ------------------------------------------------------------------
    # 1) PAGE LISTING : extrait les liens vers les fiches + pagination
    # ------------------------------------------------------------------
    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        scrapy_playwright.page.PageMethod(
                            "wait_for_selector", "div.card-job", timeout=15_000
                        )
                    ],
                },
                callback=self.parse,
            )

    def parse(self, response):
        # 1.1 fiches visibles sur la page
        for card in response.css("div.card-job"):
            detail_link = card.css("h3 a::attr(href)").get()
            if detail_link:
                yield response.follow(detail_link, callback=self.parse_detail)

        # 1.2 pagination
        next_page = response.css("li.pager-next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse, meta=response.meta)

    # ------------------------------------------------------------------
    # 2) PAGE DÉTAIL : extraction complète
    # ------------------------------------------------------------------
    def parse_detail(self, response):
        loader = ItemLoader(item=JobItem(), response=response)

        loader.add_css("title", "h1::text")
        loader.add_css("company_name", "div.card-block-company h3 a::text")
        loader.add_css("company_sectors", "div.field-name-field-entreprise-secteur .field-item ::text")
        loader.add_css("description", "div.card-job-description *::text")
        loader.add_css("contract", "li.withicon.file-signature span ::text")
        loader.add_css("region", "li.withicon.location-dot span ::text")
        loader.add_css("education", "li.withicon.graduation-cap span ::text")
        loader.add_css("experience", "li.withicon.chart span ::text")
        loader.add_css("skills", "li.withicon.briefcase span ::text")
        loader.add_css("posted", "time::attr(datetime)")
        loader.add_css("metier_type", "li.withicon.filter-slider span ::text")
        loader.add_css("metiers", "li.withicon.suitcase span ::text")
        loader.add_css("job_missions", "section:nth-of-type(1) div.job-description *::text")
        loader.add_css("job_profile", "section:nth-of-type(2) div.job-qualifications *::text")
        loader.add_css("job_criteria", "section:nth-of-type(3) ul.arrow-list li ::text")
        loader.add_css("job_skills", "section:nth-of-type(3) ul.skills li ::text")
        loader.add_css("job_count", "section:nth-of-type(3) ul.arrow-list li:last-child span ::text")
        # nettoyages rapides
        def _clean(txt):
            return re.sub(r"\s+", " ", txt.replace(":", "").strip())

        loader.add_value("url", response.url)
        loader.add_value("source", self.name)

        # on applique le même cleaner à tous les champs « texte »
        for field in ("contract", "region", "education", "experience", "skills"):
            loader.add_value(field, loader.get_collected_values(field), MapCompose(_clean))

        yield loader.load_item() 