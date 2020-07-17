import json
import os
import time
from urllib.parse import quote

from concurrent.futures._base import TimeoutError
from aiohttp.client_exceptions import ClientConnectorError
from bs4 import BeautifulSoup
import requests

import db
from apteka import Apteka, Med, Price, NAMES_APTEK
from parsing_base import Parser


def border_method_info(pre_info, post_info):
    def decorator(func):
        def wrapper(*args, **kwargs):
            print(f'[INFO {args[0].host}] {pre_info}')
            func(*args, **kwargs)
            print(f'[INFO {args[0].host}] {post_info}')
        return wrapper
    return decorator


class Parse:
    def __init__(self, response_text):
        self.response_text = response_text

    def parse_header_aptek_in_aptekamos(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        main_header_block = soup.select_one('#main-header')
        if not main_header_block:
            return
        header_aptek_block = main_header_block.select_one('h1')
        if header_aptek_block:
            header_aptek = header_aptek_block.text
            return header_aptek

    def parse_adress_aptek_in_aptekamos(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        aptek_address = soup.select_one('#org-addr').text.replace('\n', '').strip()
        return aptek_address

    def parse_max_page_in_catalog_in_aptekamos(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        pager_text = soup.select_one('#d-table-pager-text').text
        meds = int(pager_text.split(' ')[-1])
        pages = (meds // 100) + 1
        return pages

    def parse_names_urls_ids_meds_in_aptekamos(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        meds_in_page = soup.select('.ret-med-name')
        meds = []
        for med in meds_in_page:
            a = med.select_one('a')
            if a:
                name = a['title'].replace('цена', '').strip()
                id = int(a['href'].split('-')[-1].replace('/ceni', ''))
                url = a['href']
                meds.append({'name': name, 'id': id, 'url': url})
        return meds

    def parse_ids_titles_prices_meds_in_aptekamos(self):
        resp_json = json.loads(self.response_text)
        data_meds = []
        for price_json in resp_json['price']:
            drug_id = str(price_json['drugId'])
            if drug_id == '0':
                drug_id = str(price_json['itemId'].split('\t')[0])
            if len(resp_json['price']) == 1:
                med_name = price_json['medName']
            else:
                med_name = price_json['medName'] + f" № {price_json['pack']}"
                if not price_json['pack']:
                    med_name = price_json['medName']
            if not med_name:
                med_name = price_json['itemName']
            price = price_json['price']
            data_meds.append({'title': med_name, 'id': drug_id, 'price': price})
        return data_meds

    def parse_desriptionurl_in_aptekamos(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        table = soup.select_one('#data')
        url_block = table.select_one('.med-info-img')
        if url_block:
            return url_block['href']

    def parse_description_imageurl_in_aptekamos(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        descriptions = soup.find_all('meta', attrs={'name': 'description'})
        descriptions = '\n'.join([description['content'] for description in descriptions])
        image_url = soup.select_one('#med-img')
        if image_url:
            image_url = image_url['src']
        return descriptions, image_url

    def parse_csrf_token_in_stolichniki(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        csrf_token = soup.find('meta', attrs={'name': "csrf-token"})['content']
        return csrf_token

    def parse_meds_data_in_stolichniki(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        table = soup.select_one('.table.products-list-in-store')
        meds = []
        if not table:
            return meds
        meds_soup = table.select_one('tbody').select('tr')
        for med_soup in meds_soup:
            title = med_soup.select_one('.store-info').select_one('a').text
            id = med_soup.select_one('.store-info').select_one('a')['href'].split('/')[-1]
            url = 'https://aptekamos.ru' + med_soup.select_one('.store-info').select_one('a')['href']
            product_prices = med_soup.select_one('.product-price').select('.price-block')
            product_prices_num = []
            for product_price in product_prices:
                price_txt = product_price.text.replace('\n', '').replace(u'\xa0', ' ')
                if 'Цена по карте' in price_txt:
                    continue
                if not 'Цена' in price_txt:
                    continue
                price = price_txt.split(' ')[1]
                product_prices_num.append(float(price))
            price_aptek_med = product_prices_num[-1]
            meds.append({'title': title, 'id': int(id), 'price': price_aptek_med, 'url': url})
        return meds

    def parse_med_names_and_urls_in_stolichniki(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        meds_blocks = soup.select(
            '.col-12-class.col-md-4-class.col-lg-4-class.d-flex-class.flex-wrap-class.product-item.mb-4-5-class')
        meds_names_and_urls = []
        for med_block in meds_blocks:
            name_block = med_block.select_one('a.text-black-class.text-success-hover-class')
            name = name_block.text
            block_url = name_block['href']
            meds_names_and_urls.append({'name': name, 'url': block_url})
        return meds_names_and_urls


class AptekamosParser(Parser):
    def __init__(self):
        super().__init__()
        self.file_init_data = "aptekamos_init_data.txt"
        self.host = 'https://aptekamos.ru'
        self.data_catalog_name = 'aptekamos_data'
        self.apteks = []
        self.meds = []

    def load_initial_data(self):
        with open(self.file_init_data, 'r', encoding='utf8') as file:
            initial_data = file.read()
        apteks_urls = initial_data.split('\n')
        return apteks_urls

    @border_method_info(f'Обновление аптек...', 'Обновление аптек завершено.')
    def update_apteks(self):
        apteks_urls = self.load_initial_data()
        apteks_responses = self.get_responses(apteks_urls)
        count_apteks = len(apteks_urls)
        print(f'[INFO {self.host}] Всего {count_apteks} аптек')
        for aptek_response_index in range(count_apteks):
            apteka = self.get_aptek(apteks_urls, apteks_responses, aptek_response_index)
            if not apteka:
                continue
            self.apteks.append(apteka)
            print(f'[INFO {self.host}] Осталось {count_apteks-aptek_response_index} аптек')

    def get_aptek(self, apteks_urls, apteks_responses, aptek_response_index):
        header_aptek = Parse(apteks_responses[aptek_response_index]).parse_header_aptek_in_aptekamos()
        if not header_aptek:
            return
        aptek_name = str()
        for name in NAMES_APTEK:
            if name in header_aptek:
                aptek_name = name
                break
        aptek_address = Parse(apteks_responses[aptek_response_index]).parse_adress_aptek_in_aptekamos()
        aptek_url = apteks_urls[aptek_response_index]
        aptek_id = aptek_url.replace('/ob-apteke', '').split('-')[-1]
        return Apteka(name=aptek_name,
                      url=aptek_url,
                      address=aptek_address,
                      host=self.host,
                      host_id=int(aptek_id))

    @border_method_info('Обновление лекарств...', 'Обновление лекарств завершено.')
    def update_meds(self):
        response = self.request.get(self.host + '/tovary')
        max_page_in_catalog = Parse(response.text).parse_max_page_in_catalog_in_aptekamos()
        print(f"[INFO {self.host}] Всего {max_page_in_catalog} страниц в каталоге")
        page_urls = [self.host + '/tovary']
        page_urls.extend([f'https://aptekamos.ru/tovary?page={i}' for i in range(2, max_page_in_catalog + 1)])
        splited_urls = self.split_list(page_urls, 100)
        count_pages = max_page_in_catalog
        for url_list in splited_urls:
            responses = self.get_responses(url_list)
            for response in responses:
                names_urls_ids_meds = Parse(response).parse_names_urls_ids_meds_in_aptekamos()
                for name_url_id_med in names_urls_ids_meds:
                    med = Med(name=name_url_id_med['name'], url=name_url_id_med['url'], host_id=name_url_id_med['id'])
                    self.meds.append(med)
                count_pages -= 1
                print(f"[INFO {self.host}] Осталось {count_pages} страниц в каталоге")

    @border_method_info('Обновление цен...', 'Обновление цен завершено.')
    def update_prices(self):
        self.update_apteks()
        self.update_meds()
        count_position = len(self.apteks) * len(self.meds)
        print(f"[INFO {self.host}] Всего {count_position} позиций для проверки")
        post_url = self.host + '/Services/WOrgs/getOrgPrice4?compressOutput=1'
        for aptek in self.apteks:
            splited_meds = self.split_list(self.meds, 100)
            for med_list in splited_meds:
                start_time = time.time()
                post_urls = [post_url for _ in range(len(med_list))]
                post_data = [{"orgId": int(aptek.host_id), "wuserId": 0, "searchPhrase": med.name} for med in med_list]
                responses = self.post_responses(post_urls, post_data)
                time_per_cicle = time.time() - start_time
                time_left = time_per_cicle * (len(splited_meds) - splited_meds.index(med_list)) \
                            * (len(self.apteks) - self.apteks.index(aptek))
                teme_left_in_minute = int(time_left/60)
                for response in responses:
                    index = responses.index(response)
                    ids_titles_prices_meds = Parse(response).parse_ids_titles_prices_meds_in_aptekamos()
                    for id_title_price_med in ids_titles_prices_meds:
                        med = Med(name=id_title_price_med['title'],
                                  url=med_list[index].url,
                                  host_id=id_title_price_med['id'])
                        price = Price(med=med,
                                      apteka=aptek,
                                      rub=float(id_title_price_med['price']))
                        db.add_price(price)
                    count_position -= 1
                    print(f"[INFO {self.host}] Осталось {count_position} позиций для проверки и примерно {teme_left_in_minute} минут")
            db.aptek_update_updtime(aptek)

    @border_method_info('Скачивание картинок и описания...', 'Скачивание картинок и описания завершено.')
    def download_image_and_description(self, meds_info_objects):
        print(f'[INFO {self.host}] Проверка наличия препаратов на сайте')
        if 'descriptions' not in os.listdir():
            os.mkdir('descriptions')
        meds = [med for med in meds_info_objects if not med.description_url]
        count_meds = len(meds)
        print(f'[INFO {self.host}] Всего {count_meds} препаратов')
        splited_meds = self.split_list(meds, 50)
        for med_list in splited_meds:
            start_time = time.time()
            urls = self.get_search_meds_urls(med_list)
            responses = self.get_responses(urls)
            time_per_cicle = time.time() - start_time
            time_left_in_minute = int((time_per_cicle * (len(splited_meds) - splited_meds.index(med_list))) / 60)
            for med in med_list:
                index = med_list.index(med)
                description_url = Parse(responses[index]).parse_desriptionurl_in_aptekamos()
                if description_url:
                    med.set_description_url(description_url)
                count_meds -= 1
                print(f'[INFO {self.host}] Осталось {count_meds} препаратов и примерно {time_left_in_minute} минут')
        self.save_object(meds, 'meds_info') # ДЛЯ ДЕБАГА !! УДАЛИТЬ
        print(f'[INFO {self.host}] Все препараты проверены')
        self.get_image_and_description(meds)

    @border_method_info('Получение картинок и описания...', 'Получение картинок и описания завершено.')
    def get_image_and_description(self, meds):
        meds = [med for med in meds if med.description_url]
        count_meds = len(meds)
        print(f'[INFO {self.host}] Всего {count_meds} препаратов')
        splited_meds = self.split_list(meds, 50)
        for med_list in splited_meds:
            start_time = time.time()
            urls = [med.description_url for med in med_list]
            resps = self.get_responses(urls)
            for med in med_list:
                index = med_list.index(med)
                description, image_url = Parse(resps[index]).parse_description_imageurl_in_aptekamos()
                print(description)
                print(image_url)
                self.save_image_and_description(med.id, image_url, description)
                count_meds -= 1
                print(f'[INFO {self.host}] Осталось {count_meds} препаратов')
            time_per_cicle = time.time() - start_time
            time_left = time_per_cicle * (len(splited_meds) - splited_meds.index(med_list))
            time_left_in_minute = int(time_left / 60)
            print(f'[INFO {self.host}] Осталось примерно {time_left_in_minute} минут')

    def save_image_and_description(self, med_id, image_url, description):
        if str(med_id) not in os.listdir('descriptions'):
            os.mkdir(f'descriptions/{med_id}')
        if image_url:
            self.save_image(image_url, f'descriptions/{med_id}/image.jpg')
        with open(f'descriptions/{med_id}/description.txt', 'w') as file:
            file.write(description)

    def get_search_meds_urls(self, med_list):
        urls = []
        for med in med_list:
            if '№' in med.name:
                url = self.host + '/tovary/poisk?q=' + quote(med.name.split('№')[0])
            else:
                url = self.host + '/tovary/poisk?q=' + quote(med.name)
            urls.append(url)
        return urls

    def get_responses(self, urls):
        try:
            resps = self.requests.get(urls)
        except (ClientConnectorError, TimeoutError):
            resps = [self.request.get(url).text for url in urls]
        return resps

    def post_responses(self, post_urls, post_data):
        try:
            responses = self.requests.post(post_urls, json_data=post_data)
        except (ClientConnectorError, TimeoutError):
            responses = []
            for id in range(len(post_urls)):
                response = self.request.post(post_urls[id], json_data=post_data[id])
                responses.append(response.text)
        return responses


class StolichnikiParser(AptekamosParser):
    HEADERS = {
        'Host': 'stolichki.ru',
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'TE': 'Trailers'
    }
    HEADERS_JSON = {
        'Host': 'stolichki.ru',
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'TE': 'Trailers',
        'Referer': 'https://stolichki.ru/apteki',
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest'
    }
    KEYS_FOR_SEARCHING = [quote(key) for key in
                          list('qwertyuiopasdfghjklzxcvbnm1234567890йцукенгшщзхъфывапролджэячсмитьбю')]

    def __init__(self):
        super().__init__()
        self.file_init_data = "stolichki_init_data.txt"
        self.host = 'https://stolichki.ru'
        self.data_catalog_name = 'stolichniki_data'
        self.apteks = []
        self.meds = []
        self.prices = []

    @border_method_info(f'Обновление аптек...', 'Обновление аптек завершено.')
    def update_apteks(self):
        response = requests.get('https://stolichki.ru/apteki', headers=self.HEADERS)
        csrf_token = Parse(response.text).parse_csrf_token_in_stolichniki()
        self.HEADERS_JSON['X-CSRF-TOKEN'] = csrf_token
        response = requests.get('https://stolichki.ru/stores/all?cityId=1', headers=self.HEADERS_JSON)
        json_response = response.json()
        stores = json_response['stores']
        self.apteks = []
        initial_data = self.load_initial_data()
        for store in stores:
            url = self.host + f"/apteki/{store['id']}"
            if url not in initial_data:
                continue
            host_id = store['id']
            address = store['full_address']
            name = 'Столички'
            host = self.host
            apteka = Apteka(url=url,
                            host_id=host_id,
                            address=address,
                            name=name,
                            host=host)
            self.apteks.append(apteka)

    @border_method_info('Обновление цен...', 'Обновление цен завершено.')
    def update_prices(self):
        self.update_apteks()
        count_cicles = len(self.KEYS_FOR_SEARCHING) * len(self.apteks)
        print(f'[INFO {self.host}] Всего {count_cicles} циклов')
        for aptek in self.apteks:
            start_time = time.time()
            urls_with_keys = [aptek.url + '?q=' + key for key in self.KEYS_FOR_SEARCHING]
            count_urls = len(urls_with_keys)
            responses = self.get_responses(urls_with_keys)
            for response_index in range(count_urls):
                meds_data = Parse(responses[response_index]).parse_meds_data_in_stolichniki()
                for med_data in meds_data:
                    med = Med(name=med_data['title'], url=med_data['url'], host_id=med_data['id'])
                    price = Price(apteka=aptek, med=med, rub=med_data['price'])
                    db.add_price(price)
                    count_cicles -= 1
                    print(f'[INFO {self.host}] Осталось {count_cicles} циклов')
            time_per_cicle = time.time() - start_time
            time_left = time_per_cicle * (len(self.apteks) - self.apteks.index(aptek))
            time_left_in_minute = int(time_left / 60)
            print(f'[INFO {self.host}] Осталось примерно {time_left_in_minute} минут')
            db.aptek_update_updtime(aptek)

    @border_method_info('Скачивание картинок и описания...', 'Скачивание картинок и описания завершено.')
    def download_image_and_description(self, meds_info_objects):
        print(f'[INFO {self.host}] Проверка наличия препаратов на сайте')
        meds = [med for med in meds_info_objects if not med.description_url]
        count_meds = len(meds)
        print(f'[INFO {self.host}] Всего {count_meds} препаратов')
        for med in meds:
            start_time = time.time()
            url = f'{self.host}/search?name={quote(med.name)}'
            response = self.request.get(url)
            meds_names_and_urls = Parse(response.text).parse_med_names_and_urls_in_stolichniki()




if __name__ == '__main__':
    parser = AptekamosParser()
    parser.update_prices()