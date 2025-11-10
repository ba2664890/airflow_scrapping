import scrapy ,re
from scrapy.loader import ItemLoader
from Emploi_senegal.items import emploi_expatdakar

# Après
try:
    from itemloaders.processors import TakeFirst, MapCompose
except ModuleNotFoundError:
    from scrapy.loader.processors import TakeFirst, MapCompose

from itemloaders.processors import Join
from datetime import datetime


class ExpatDakarSpider(scrapy.Spider):
    name = "emploi_expatdakar"
    allowed_domains = ["www.expat-dakar.com"]
    start_urls = ["https://www.expat-dakar.com/emploi"]

    custom_settings = {
        "DOWNLOAD_DELAY": 1,
        "CONCURRENT_REQUESTS": 16,
        "ROBOTSTXT_OBEY": False,
        "DEFAULT_REQUEST_HEADERS": {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Referer": "https://www.expat-dakar.com",
        },
        "ITEM_PIPELINES": {
            "Emploi_senegal.pipelines.DuplicatesPipeline": 100,
            "Emploi_senegal.pipelines.ExpatDakarPipeline": 500,
        }
        
    }

    # ------------------------------------------------------------------
    # 1) PAGE LISTING : extrait les liens vers les fiches + pagination
    # ------------------------------------------------------------------
    def parse(self, response):
        # 1.1 Extraire toutes les fiches
        for link in response.css('a.listing-card__inner[href*="/annonce/"]::attr(href)').getall():
            yield response.follow(link, callback=self.parse_detail)

        # 1.2 Pagination : bouton "Suivant"
        next_page = response.css('a[rel="next"]::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)


    def parse_detail(self, response):
        loader = ItemLoader(item=emploi_expatdakar(), response=response)

        # Titre
        loader.add_css("title", "h1.listing-item__header::text", TakeFirst())

        # Date de publication
        def clean_date(value):
            return value.strip()

        loader.add_css(
            "posted_date",
            "div.listing-item__details__date::text",
            MapCompose(str.strip, clean_date)
        )

        # Référence de l'annonce
        loader.add_css(
            "ad_id",
            "div.listing-item__details__ad-id::text",
            MapCompose(lambda x: re.search(r"\d+", x).group() if re.search(r"\d+", x) else None)
        )

        # Localisation
        loader.add_css("location", "span.listing-item__address-location::text", TakeFirst())
        loader.add_css("region", "span.listing-item__address-region::text", TakeFirst())

        # Propriétés de l'annonce (scrapping dynamique par titre)
        def get_property(title):
            # Utilise des guillemets doubles si le titre contient une apostrophe
            if "'" in title:
                return response.xpath(f'//dt[contains(@class, "listing-item__properties__title") and contains(., "{title}")]/following-sibling::dd[1]/text()').get()
            else:
                return response.xpath(f"//dt[contains(@class, 'listing-item__properties__title') and contains(., '{title}')]/following-sibling::dd[1]/text()").get()
        loader.add_value("employeur", get_property("Employeur"))
        loader.add_value("secteur", get_property("Secteur d'activité"))
        loader.add_value("type_contrat", get_property("Type de contrat"))
        loader.add_value("niveau", get_property("Niveau d'emploi"))
        loader.add_value("niveau_etude", get_property("Niveau d'étude"))
        loader.add_value("experience", get_property("Des années d'expérience"))
        loader.add_value("nb_postes", get_property("Nombre de postes"))

        # Description complète
        loader.add_css("description", "div.listing-item__description *::text", Join("\n"))

        # URL source
        loader.add_value("url", response.url)
        loader.add_value("source", "expat-dakar")

        return loader.load_item()
