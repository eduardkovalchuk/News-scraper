import os
import json
import requests
from bs4 import BeautifulSoup
from mongo_setup import Database
import gridfs
from selenium import webdriver
import time



LIMIT = 1  # number of articles in each category to 10
requests.packages.urllib3.disable_warnings()  # turn off SSL warnings

# db configuration
db_name = 'scraper_db'
my_db = Database(db_name).connect_db()

# clean old data from collections
if "tsn_categories" or "tsn_articles" in my_db.collection_names():
    my_db["tsn_categories"].drop()
    my_db["tsn_articles"].drop()
tsn_category_coll = my_db["tsn_categories"]
tsn_articles_coll = my_db["tsn_articles"]

if "ukr_categories" or "ukr_articles" in my_db.collection_names():
    my_db["ukr_categories"].drop()
    my_db["ukr_articles"].drop()
ukr_category_coll = my_db["ukr_categories"]
ukr_articles_coll = my_db["ukr_articles"]


def download_image(image_url):
    dir_name = 'image_storage/'
    path = os.path.join(dir_name)
    local_filename = image_url.split('/')[-1].split("?")[0]

    r = requests.get(image_url, stream=True, verify=False)
    with open(path + local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            f.write(chunk)


def upload_image_mongo(image_url):
    response = requests.get(image_url, stream=True)
    fs = gridfs.GridFS(my_db)
    img = response.raw.read()
    fs.put(img, filename=local_filename)


# ------------------ TSN.UA ------------------

base_url = "https://tsn.ua/"
data = []

# PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
# DRIVER_BIN = os.path.join(PROJECT_ROOT, "bin/chromedriver")

# driver = webdriver.Chrome(executable_path = DRIVER_BIN)
# driver.get(base_url)

# page = driver.page_source
# soup = BeautifulSoup(page, "html.parser")



r = requests.get(base_url)
soup = BeautifulSoup(r.text, "html.parser")
# all_categories = soup.find_all('ul', class_='c-app-nav-more-list')


# collect category links
categories = []
all_categories = soup.select('ul.c-app-nav-more-list li a')
for item in all_categories:
    category = {}
    category['link'] = item.attrs.get('href')
    # category['name'] = "".join(item.contents).split()[0]
    category['name'] = item.get_text().strip()
    categories.append(category)

tsn_category_coll.insert_many(categories)  # write category's data to DB


for category in categories:
    count = 0
    # parse each category
    r = requests.get(category['link'])
    # driver.get(category['link'])
    # page = driver.page_source
    soup = BeautifulSoup(r.text, "html.parser")


    all_articles = soup.select('div.c-entry-embed a.c-post-img-wrap')
    for item in all_articles:
        # only 20 first articles
        if count < LIMIT:
            article = {}
            link = item.attrs.get('href')
            img_src = item.find('img').get('src')
            if link.endswith(".html"):
                article['link'] = link
                if img_src is not None:
                    article['img_src'] = img_src
                    download_image(img_src)

                article['category'] = category['name']
                data.append(article)
            count += 1
        else:
            break


for article in data:
    # parse each article in articles
    r = requests.get(article['link'])
    # driver.get(article['link'])
    # page = driver.page_source
    soup = BeautifulSoup(r.text, "html5lib")
    news_content = soup.select('div.e-content p')

    text_content = [] # article content
    for chunk in news_content:
        text_content.append(chunk.get_text().strip(''))
    article_text = ' '.join(text_content)

    news_header = soup.select('div.c-post-meta h1') # article title
    if news_header:
        header_text = "".join(news_header[0].contents)

    article_image = soup.find('figure', class_='js-lightgallery')
    if article_image:
        img_src = article_image.find('img').get('src') # articles image
        download_image(img_src)

    news_chunk = {}
    news_chunk['category'] = article['category']
    news_chunk['link'] = article['link']
    news_chunk['title'] = header_text
    news_chunk['content'] = article_text
    news_chunk['images'] = []
    if 'img_src' in article:
        news_chunk['images'].append(article['img_src']) # caption image
    if article_image:
        news_chunk['images'].append(img_src) # article image

    tsn_articles_coll.insert_one(news_chunk)



# # ------------------ UKR.NET ------------------

# base_url = "https://www.ukr.net/"

# PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
# DRIVER_BIN = os.path.join(PROJECT_ROOT, "bin/chromedriver")

# driver = webdriver.Chrome(executable_path = DRIVER_BIN)
# driver.get(base_url)


# page = driver.page_source
# soup = BeautifulSoup(page, "html.parser")
# all_categories = soup.select('h2.feed__section--title a')


# categories = []
# for item in all_categories:
#     category = {}
#     # check if the link is correct
#     if item.attrs.get('href').endswith('.html'):
#         category['link'] = 'https:' + item.attrs.get('href')
#         category['name'] = item.get_text().strip()
#         categories.append(category)
# ukr_category_coll.insert_many(categories)  # write category's data to DB


# for category in categories:
#     count = 0
    
#     driver.get(category['link'])
#     page = driver.page_source
#     soup = BeautifulSoup(page, "html.parser")

#     all_articles = soup.select('div.im-tl a')
#     for item in all_articles:
#         # only 10 first articles
#         if count < LIMIT:
#             article = {}
#             link = item.attrs.get('href')
#             article['link'] = link
#             article['category'] = category['name']
#             article['content'] = item.contents[0].encode('utf-8')
#             ukr_articles_coll.insert_one(article)
#         else:
#             break
#         count += 1

# driver.quit()



















