import scrapy
import re
from datetime import datetime, timedelta
from scrapy.loader import ItemLoader
try:
    from itemloaders.processors import TakeFirst, MapCompose
except ModuleNotFoundError:
    from scrapy.loader.processors import TakeFirst, MapCompose
from Emploi_senegal.items import concoursn_stage


class ConcoursnStagesSpider(scrapy.Spider):
    name = "concoursn_stages"
    allowed_domains = ["concoursn.com"]
    start_urls = ["https://concoursn.com/category/maroc/stages/"]

    custom_settings = {
        "DOWNLOAD_DELAY": 1,
        "CONCURRENT_REQUESTS": 8,
        "ROBOTSTXT_OBEY": False,
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
        },
        "ITEM_PIPELINES": {
            "Emploi_senegal.pipelines.DuplicatesPipeline": 100,
            "Emploi_senegal.pipelines.ConcoursnPipeline": 500,
        }
    }

    def parse(self, response):
        # Extraction des liens vers les fiches de stage
        for article in response.css('article.vce-post'):
            link = article.css('h2.entry-title a::attr(href)').get()
            if link:
                yield response.follow(link, callback=self.parse_detail)

        # Pagination - suivre le lien "Voir Plus"
        next_page = response.css('nav#vce-pagination.vce-load-more a::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_detail(self, response):
        loader = ItemLoader(item=concoursn_stage(), response=response)

        # Titre
        loader.add_css("title", "h1.entry-title::text", TakeFirst())

        # URL
        loader.add_value("url", response.url)

        # Source
        loader.add_value("source", "concoursn")

        # Catégories
        loader.add_css("categories", "span.meta-category a::text")

        # Tags
        loader.add_css("tags", "div.meta-tags a::text")

        # Date de publication (format relatif)
        loader.add_css("posted_date_raw", "span.updated::text", TakeFirst())

        # Description complète
        loader.add_css("description", "div.entry-content *::text")

        # Extraction de l'entreprise depuis le titre (pattern "Entreprise recrute")
        title = response.css("h1.entry-title::text").get()
        if title:
            # Patterns courants : "Entreprise recrute", "Entreprise recherche", etc.
            match = re.search(r'^([^-]+?)\s+(?:recrute|recherche|recrutement)', title, re.IGNORECASE)
            if match:
                loader.add_value("company", match.group(1).strip())
            else:
                loader.add_value("company", None)

        return loader.load_item()