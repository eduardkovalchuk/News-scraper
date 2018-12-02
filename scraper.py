# -*- coding: utf-8 -*-

import os
import json
import requests
from bs4 import BeautifulSoup
from mongo_setup import Database
import gridfs
from selenium import webdriver
import time
import logging
import re
import pymongo


NEW = "NEW"
INACTIVE= "INACTIVE"
SETUP = "SETUP"
BANNED = "BANNED"
IN_PROCESS = "IN_PROCESS"
PROCESSED = "PROCESSED"
FAILED = "FAILED"

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
DRIVER_BIN = os.path.join(PROJECT_ROOT, "bin/chromedriver")


class Scraper:

    tsn_resource = 'https://tsn.ua/'
    ukrnet_resource = 'https://www.ukr.net/'

    db_name = 'scraper_db'
    category_coll = 'categories'
    articles_coll = 'articles'


    def __init__(self, limit=10):
        self.limit = limit  # max number of articles per category
        self.db = Database(self.db_name).connect_db()
        self.category_coll = self.init_collection(self.category_coll)
        self.articles_coll = self.init_collection(self.articles_coll)
        self.logger = self.init_logger()
        self.driver = webdriver.Chrome(executable_path = DRIVER_BIN)
        self.image_storage = os.path.join(PROJECT_ROOT, "image_storage/")


    def init_logger(self):
        '''
        Initialize log file.
        '''
        logger = logging.getLogger('scraper_app')
        logger.setLevel(logging.INFO)

        # create a file handler
        handler = logging.FileHandler('scraper_logfile.log')
        handler.setLevel(logging.INFO)

        # create a logging format
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)

        # add the handlers to the logger
        logger.addHandler(handler)
        return logger


    def init_collection(self, name):
        if name in self.db.collection_names():
            self.db[name].drop()
        return self.db[name]



    # def db_collections(self):
    #     '''
    #     creates mongodb collections if they don't exist
    #     otherwise cleans the data in the old collections
    #     '''

    #     # check if collections exist
    #     # if yes, drop them to refresh the data
    #     if self.category_coll or self.articles_coll in self.db.collection_names():
    #         self.db[self.category_coll].drop()
    #         self.db[self.articles_coll].drop()

    #     # create new collections
    #     self.category_coll =  self.db[self.category_coll]
    #     self.articles_coll = self.db[self.articles_coll]


    def insert_one_to_collection(self, data, collection):
        try:
            collection.insert_one(data)
        except pymongo.errors.DuplicateKeyError:
            pass

    def insert_many_to_collection(self, data, collection):
        try:
            collection.insert_many(data)
        except pymongo.errors.DuplicateKeyError:
            pass


    def download_image(self, image_url):
        '''
        download images from news articles
        to local storage
        '''
        if not image_url.startswith(("data:image", "javascript")):
            local_filename = image_url.split('/')[-1].split("?")[0]

            r = requests.get(image_url, stream=True, verify=False)
            with open(self.image_storage + local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    f.write(chunk)


    def upload_image_to_mongo(self, image_url):
        response = requests.get(image_url, stream=True)
        fs = gridfs.GridFS(self.db)
        img = response.raw.read()
        fs.put(img, filename=local_filename)


    def get_page_content(self, url):
        self.driver.get(url)
        page = self.driver.page_source
        return page


    def parse_page_content(self, url, parser_lib):
        page_obj = self.get_page_content(url)
        soup = BeautifulSoup(page_obj, parser_lib)
        return soup


    def tsn_categories(self):
        categories = self.gather_categories(self.tsn_resource, 'ul.c-app-nav-more-list li a')
        return categories

    def ukrnet_categories(self):
        categories = self.gather_categories(self.ukrnet_resource, 'h2.feed__section--title a')
        return categories


    def gather_categories(self, url, selector):
        categories = []
        soup = self.parse_page_content(url, "html.parser")
        all_categories = soup.select(selector)

        for item in all_categories:
            category = {}
            link = str(item.attrs.get('href'))
            if link.startswith('javascript'):
                continue
            if not link.startswith('https:'):
                link = 'https:' + link
            category['link'] = link
            category['name'] = item.get_text().strip()
            categories.append(category)

        self.insert_many_to_collection(categories, self.category_coll)
        return categories


    def search_by_category(self, category_name, category_list):
        category_name = category_name.decode('utf-8')
        # category_name = category_name.encode('utf-8')
        category_obj = next(item for item in category_list if item['name'] == category_name)
        link = category_obj['link']
        if 'ukr.net' in link:
            articles = self.get_ukrnet_articles(category_name, link)
        else:
            articles = self.get_tsn_articles(category_name, link)
        return articles


    def get_ukrnet_articles(self, category_name, url):
        '''
        retrieve all articles from ukr.net by given category link
        '''
        count = 0
        result = []
        soup = self.parse_page_content(url, "html.parser")
        all_articles = soup.select('div.im-tl a')
        for item in all_articles:
            if count <= self.limit:
                article = {}
                link = item.attrs.get('href')
                article['link'] = link
                article['category'] = category_name
                article['content'] = item.contents[0].encode('utf-8')
                result.append(article)
                self.insert_one_to_collection(article, self.articles_coll)
            else:
                break
            count += 1

        return result


    def get_tsn_articles(self, category_name, url):
        '''
        retrieve all articles from tsn.ua by given category link
        '''
        count = 0
        result = []

        data = []  # temporary storage

        # first parse through the list of articles
        soup = self.parse_page_content(url, "html.parser")
        all_articles = soup.select('div.c-entry-embed a.c-post-img-wrap')
        for item in all_articles:

            # iterate limit amount of articles
            if count <= self.limit:
                article = {}
                link = item.attrs.get('href')
                img_src = item.find('img').get('src')
                if link.endswith(".html"):
                    article['link'] = link
                    if img_src is not None:
                        article['img_src'] = img_src
                        self.download_image(img_src)

                    article['category'] = category_name
                    data.append(article)
                count += 1
            else:
                break

        # then iterate over each article
        for article in data:
            new_soup = self.parse_page_content(article['link'], "html5lib")
            news_content = new_soup.select('div.e-content p')

            text_content = [] # article content
            for chunk in news_content:
                text_content.append(chunk.get_text().strip(''))
            article_text = ' '.join(text_content)

            news_header = new_soup.select('div.c-post-meta h1') # article title
            if news_header:
                header_text = "".join(news_header[0].contents)

            article_image = new_soup.find('figure', class_='js-lightgallery')
            if article_image:
                img_src = article_image.find('img').get('src') # articles image
                download_image(img_src)

            news_chunk = {}
            news_chunk['category'] = article['category']
            news_chunk['link'] = article['link']
            news_chunk['title'] = header_text
            # news_chunk['title'] = ''
            news_chunk['content'] = article_text
            news_chunk['images'] = []
            if 'img_src' in article:
                news_chunk['images'].append(article['img_src']) # caption image
            if article_image:
                news_chunk['images'].append(img_src) # article image

            result.append(news_chunk)
            self.insert_one_to_collection(news_chunk, self.articles_coll)

        return result

    def search_by_text(self, text):
        category_links = []
        category_links += self.ukrnet_categories()
        category_links += self.tsn_categories()
        result = self.website_search_by_text(text, category_links)


    def website_search_by_text(self, text_searched, category_links):
        result = []

        text_searched = text_searched.decode('utf-8')
        for link in category_links:
            article = {}
            soup = self.parse_page_content(link['link'], "html.parser")
            all_articles = soup.find_all('a', text=re.compile(text_searched))
            for item in all_articles:
                article['link'] = item.attrs.get('href')
                article['category'] = link['name']
                article['content'] = (item.contents[0].strip()).encode('utf-8')
                self.insert_one_to_collection(article, self.articles_coll)
                result.append(article)
        return result


    def collect_ukrnet_articles(self):
        '''
        outdated
        '''
        categories = self.ukrnet_categories()

        for category in categories:
            count = 0
            soup = self.parse_page_content(category['link'], "html.parser")

            all_articles = soup.select('div.im-tl a')
            for item in all_articles:
                # only 10 first articles
                if count < self.limit:
                    article = {}
                    link = item.attrs.get('href')
                    article['link'] = link
                    article['category'] = category['name']
                    article['content'] = item.contents[0].encode('utf-8')
                    self.insert_one_to_collection(article, self.articles_coll)
                else:
                    break
                count += 1


    def run(self):
        # self.tsn_categories()
        # self.collect_ukrnet_articles()
        # self.search_by_category('Економіка', self.tsn_categories())
        self.get_tsn_articles('Економіка', "https://tsn.ua/groshi")
        self.driver.quit()


if __name__ == '__main__':
    scraper = Scraper()
    scraper.run()

























