from parsing_base import Parser
from bs4 import BeautifulSoup
import csv_writer
import time
import xml_writer
import apteka
import sys
import json
import db


class GorZdrafParser(Parser):

    def __init__(self):
        super().__init__()
        self.host = 'https://gorzdrav.org'
        self.apteks = []
        self.name = 'горздрав'

    def get_url_categories_with_pages(self):
        resp = self.request.get(self.host)
        soup = BeautifulSoup(resp.text, 'lxml')
        url_categories = [self.host + item.select_one('a')['href'] for item in
                          soup.select('.c-catalog-body__item')]
        max_pages = self.get_max_pages(url_categories)
        count_categories = len(url_categories)
        url_categories_with_pages = []
        for category_index in range(count_categories):
            category_with_page = [url_categories[category_index]]
            for page in range(2, max_pages[category_index] + 1):
                url_page = url_categories[category_index] + f'?q=%3AavailableInStoresOrStock%3Atrue&page={page}'
                category_with_page.append(url_page)
            url_categories_with_pages.append(category_with_page)
        return url_categories_with_pages

    def update_catalog(self):
        print('[INFO] Обновление каталога...')
        csv_writer.create_csv_file(self.csv_catalog)
        url_categories_with_pages = self.get_url_categories_with_pages()
        for category_with_page in url_categories_with_pages:
            meds = self.get_meds(category_with_page)
            csv_writer.add_data_in_catalog(self.csv_catalog, meds)
        print('[INFO] Обновление каталога завершено')

    def update_prices(self):
        print('[INFO] Обновление цен...')
        self.update_apteks()
        url_categories_with_pages = self.get_url_categories_with_pages()
        for category_with_page in url_categories_with_pages:
            meds = self.get_meds(category_with_page)
            splited_meds = self.split_list(meds, 100)
            for splited_med in splited_meds:
                count_meds = len(splited_med)
                med_urls = [med.url for med in splited_med]
                resps = self.requests.get(med_urls)
                aptek_urls = [f"https://gorzdrav.org/stockdb/ajax/product/{med.host_id}/stores/all/?sortName=recommend&sortType=ASC" for med in splited_med]
                resps_apteks = self.requests.get(aptek_urls)
                for med_index in range(count_meds):
                    soup = BeautifulSoup(resps[med_index], 'lxml')
                    price_soup = soup.find('meta', itemprop="price")
                    rub = float(price_soup['content'])
                    apteks_indexes = [int(aptek['name']) for aptek in json.loads(resps_apteks[med_index])['data']]
                    for aptek_index in apteks_indexes:
                        for aptek in self.apteks:
                            if aptek_index == aptek.host_id:
                                price = apteka.Price(apteka=aptek, med=splited_med[med_index], rub=rub)
                                print(price)
                                db.add_price(price)

    def get_meds(self, urls):
        resps = self.requests.get(urls)
        meds = []
        for resp in resps:
            soup = BeautifulSoup(resp, 'lxml')
            product_blocks = soup.select('.c-prod-item.c-prod-item--grid')
            for product_block in product_blocks:
                index = product_block.select_one('a')['data-gtm-id']
                url = self.host + product_block.select_one('a')['href']
                title = product_block.select_one('a')['data-gtm-name']
                meds.append(apteka.Med(name=title, url=url, host_id=index))
        return meds

    def update_apteks(self):
        print('[INFO] Получение аптек...')
        resp = self.request.get(self.host + '/apteki/list/')
        max_page = self.get_max_page(resp.text)
        urls = [self.host + '/apteki/list/']
        extend_list = [self.host + f'/apteki/list/?page={page}' for page in range(1, max_page)]
        urls.extend(extend_list)
        resps = self.requests.get(urls)
        self.apteks = []
        for resp in resps:
            soup = BeautifulSoup(resp, 'lxml')
            rows_table_apteks = soup.select('.b-table__row')
            for row in rows_table_apteks:
                if 'b-table__head' not in row['class']:
                    id = int(row.select_one('.b-store-favorite__btn.js-favorites-store.js-text-hint')['data-store'])
                    adress = row.select_one('.c-pharm__descr').text.replace('\n', '').lstrip()
                    print(id, adress)
                    self.apteks.append(apteka.Apteka(host_id=id,
                                                     name='ГОРЗДРАВ',
                                                     address=adress,
                                                     host=self.host,
                                                     url= f"{self.host}/apteka/{id}"))
        print('[INFO] Аптеки получены')

    def get_max_page(self, resp_text):
        soup = BeautifulSoup(resp_text, 'lxml')
        return int(soup.select('.b-pagination__item')[-2].text)

    def get_max_pages(self, urls):
        resps = self.requests.get(urls)
        max_pages = []
        for resp in resps:
            max_pages.append(self.get_max_page(resp))
        return max_pages


if __name__ == '__main__':
    parser = GorZdrafParser()
    parser.update_prices()





