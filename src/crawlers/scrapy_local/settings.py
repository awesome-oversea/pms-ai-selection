BOT_NAME = "pms_local_crawl"

SPIDER_MODULES = ["src.crawlers.scrapy_local.spiders"]
NEWSPIDER_MODULE = "src.crawlers.scrapy_local.spiders"

ROBOTSTXT_OBEY = False
LOG_ENABLED = False
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
USER_AGENT = "PMS-SelectionBot/1.0"

DOWNLOAD_TIMEOUT = 15
FEED_EXPORT_ENCODING = "utf-8"
