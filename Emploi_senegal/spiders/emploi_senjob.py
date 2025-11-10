import logging
from Emploi_senegal.items import emploi_senjob
import scrapy, hashlib, re
from datetime import datetime
from scrapy.loader import ItemLoader
from itemloaders.processors import TakeFirst, MapCompose


def clean_text(val):
    return re.sub(r"\s+", " ", val).strip()


class EmploiSenjobSpider(scrapy.Spider):
    name = "emploi_senjob"
    start_urls = ["https://senjob.com/sn/offres-d-emploi.php"]

    custom_settings = {
        'PLAYWRIGHT_BROWSER_TYPE': "firefox",
        'LOG_LEVEL': 'DEBUG',
        'LOG_ENABLED': True,
        'ROBOTSTXT_OBEY': False,
        "DOWNLOAD_DELAY": 1,
        "CONCURRENT_REQUESTS": 1,
        "ITEM_PIPELINES": {
            'Emploi_senegal.pipelines.DuplicatesPipeline': 100,
            'Emploi_senegal.pipelines.senjobPipeline': 300,
        }
    }

    def parse(self, response):
        # 1) extraction des lignes d’offres
        self.logger.info(f"PAGE LISTING: len(response.css('table#offresenjobs tr'))={len(response.css('table#offresenjobs tr'))}")
        for tr in response.css("table#offresenjobs tr"):
            loader = ItemLoader(item=emploi_senjob(), selector=tr)
            loader.default_output_processor = TakeFirst()

            # titre + lien détail
            loader.add_css("title", "a::text", MapCompose(str.strip))
            detail = tr.css("a::attr(href)").get()
            if detail and "page=" not in detail:
                detail = response.urljoin(detail.strip())

                # localisation & dates (avec nettoyage)
                loader.add_xpath(
                    "location",
                    './/span[@class="glyphicon glyphicon-map-marker"]/parent::span/text()',
                    MapCompose(clean_text),
                )


                posted_date_list = tr.xpath('.//span[@class="glyphicon glyphicon-calendar"]/parent::span//text()').getall()
                posted_date_list = [txt.strip() for txt in posted_date_list if txt.strip()]

                # Extraire uniquement la date (YYYY-MM-DD)
                posted_date = None
                for txt in posted_date_list:
                    if re.match(r"\d{4}-\d{2}-\d{2}", txt):
                        posted_date = txt
                        break

                # Charger dans l’item
                if posted_date:
                    loader.add_value("posted_date", posted_date)



                expiration_list = tr.xpath('.//span[@class="glyphicon glyphicon-time"]/parent::span//text()').getall()
                expiration_clean = expiration_list[1].strip() if expiration_list else None
                loader.add_value("expiration", expiration_clean)

                item = loader.load_item()
                item["url"] = detail
                item["source"] = "senjob"
                item["id"] = hashlib.md5(detail.encode()).hexdigest()

                # on suit le lien détail pour salaire, description, catégories
                if detail:
                    yield scrapy.Request(detail, callback=self.parse_detail, meta={"item": item})
            else:
                continue
        # 2) pagination
        num_page = response.css('div.resultsOffre.activepage span::text').get()
        num_page = int(num_page)
        if num_page < 9:
            self.logger.info(f"Suivant page: {num_page+1}")
            num_page = f"/sn/offres-d-emploi.php?page={num_page+1}"
            yield scrapy.Request(response.urljoin(num_page), callback=self.parse)
            

    def parse_detail(self, response):
        item = response.meta["item"]
        loader = ItemLoader(item=item, response=response)

        # Récupérer tout le texte
        raw_texts = response.css("table tr td table tr td td::text").getall()

        # Nettoyer (strip et enlever les vides)
        clean_texts = [t.strip() for t in raw_texts if t.strip()]

        # Debug : afficher ce qu'on a
        print(clean_texts)
        self.logger.info(f"DETAIL: (clean_texts)={clean_texts}")
        # Extraire le salaire (ex: "100000/ mois")
        salaire = None
        for t in clean_texts:
            if re.search(r"mois", t, re.IGNORECASE):  # pattern salaire mensuel
                salaire = t
                break
        loader.add_value("salaire", salaire) 

        raw_texts = response.css("table tr td table tr td strong::text").getall()
        loader.add_value("contract_type", raw_texts)
        # description & catégories
        loader.add_css("description", "div.view *::text")
        loader.add_css("categorie", "div.tagcompt::text")

        return loader.load_item()
    
    def start_requests(self):
        self.logger.setLevel(logging.DEBUG)          # on s’assure de voir nos logs
        self.logger.info(">>> START_REQUESTS APPELÉ, start_urls = %s", self.start_urls)
        for url in self.start_urls:
            self.logger.info(">>> YIELD REQUEST : %s", url)
            yield scrapy.Request(url, callback=self.parse, dont_filter=True)
