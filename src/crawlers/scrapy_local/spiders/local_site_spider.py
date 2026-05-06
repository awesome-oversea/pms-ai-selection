from __future__ import annotations

import scrapy


class LocalSiteSpider(scrapy.Spider):
    name = "local_site"

    def __init__(self, start_url: str = "", query: str = "", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url] if start_url else []
        self.query = query

    def parse(self, response: scrapy.http.Response):
        for card in response.css(".product-card"):
            href = card.css("a::attr(href)").get() or ""
            yield {
                "source": "scrapy_runtime",
                "engine": "scrapy-compatible",
                "query": self.query,
                "title": (card.css(".title::text").get() or "").strip(),
                "category": (card.css(".category::text").get() or "").strip(),
                "summary": (card.css(".summary::text").get() or "").strip(),
                "url": response.urljoin(href),
                "render_mode": "static-html",
            }
