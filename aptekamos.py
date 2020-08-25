import grequests
import json
import os
import time
from urllib.parse import quote
from typing import Union
from dataclasses import dataclass
import unicodedata
from concurrent.futures._base import TimeoutError
from aiohttp.client_exceptions import ClientConnectorError
from bs4 import BeautifulSoup
import requests
from json.decoder import JSONDecodeError
import sys
import db
from apteka import Apteka, Med, Price, NAMES_APTEK
from parsing_base import Parser, border_method_info
from typing import Iterator
from requests import Response
import traceback
from proxy import Proxy
from requests.exceptions import ProxyError, ConnectTimeout, SSLError
import re
import math

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:74.0) Gecko/20100101 Firefox/74.0'
}


@dataclass
class SearchPhrase:
    med: Med
    apteka: Apteka
    post_data: dict


class Parse:
    def __init__(self, response_text):
        self.response_text = response_text
        self.soup = BeautifulSoup(self.response_text, 'lxml')

    def parse_header_aptek(self) -> Union[str, None]:
        soup = BeautifulSoup(self.response_text, 'lxml')
        main_header_block = soup.select_one('#main-header')
        if not main_header_block:
            return
        header_aptek_block = main_header_block.select_one('h1')
        if header_aptek_block:
            header_aptek = header_aptek_block.text
            return header_aptek

    def parse_adress_aptek(self) -> str:
        soup = BeautifulSoup(self.response_text, 'lxml')
        aptek_address = soup.select_one('#org-addr').text.replace('\n', '').strip()
        return aptek_address

    def parse_max_page_in_catalogs(self) -> int:
        soup = BeautifulSoup(self.response_text, 'lxml')
        pager_text = soup.select_one('#d-table-pager-text').text
        meds = int(pager_text.split(' ')[-1])
        pages = (meds // 100) + 1
        return pages

    def parse_names_urls_ids_meds(self) -> list:
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

    def _parse_ids_title_prices_in_meds_from_html(self) -> list:
        soup = BeautifulSoup(self.response_text, 'lxml')
        product_blocks = soup.select('.product-c')
        if product_blocks:
            for product_block in product_blocks:
                med_name = product_block.select_one('.org-product-name.function').text
                med_price = product_block.select_one('.dialog-product-price').text
                if '№' in med_name:
                    splited_med_name = med_name.split(' ')
                    if '№' in splited_med_name:
                        index_number = splited_med_name.index('№')
                        med_name = ' '.join(splited_med_name[:index_number + 2])
                med_price = unicodedata.normalize("NFKD", med_price).replace(' ', '')
                yield {'title': med_name, 'id': 0, 'price': med_price}

    def _parse_ids_title_prices_in_meds_from_json(self) -> list:
        resp_json = json.loads(self.response_text)
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
            yield {'title': med_name, 'id': drug_id, 'price': price}

    def parse_ids_titles_prices_in_meds(self) -> list:
        try:
            resp_json = json.loads(self.response_text)
        except JSONDecodeError:
            return self._parse_ids_title_prices_in_meds_from_html()
        return self._parse_ids_title_prices_in_meds_from_json()

    def parse_desriptionurl(self) -> str:
        soup = BeautifulSoup(self.response_text, 'lxml')
        table = soup.select_one('#data')
        url_block = table.select_one('.med-info-img')
        if url_block:
            return url_block['href']

    def parse_description_imageurl(self) -> tuple:
        soup = BeautifulSoup(self.response_text, 'lxml')
        descriptions = soup.find_all('meta', attrs={'name': 'description'})
        descriptions = '\n'.join([description['content'] for description in descriptions])
        image_url = soup.select_one('#med-img')
        if image_url:
            image_url = image_url['src']
        return descriptions, image_url

    def parse_med_name(self) -> str:
        block_name = self.soup.find('h1', attrs={'itemprop': 'name'})
        med_name = block_name.text.replace('\n', ' ').strip()
        return med_name

    def parse_max_page_aptek(self) -> int:
        paginator = self.soup.select_one('#d-table-page-num')
        if not paginator:
            return 1
        paginator_text = self.soup.select_one('#d-table-pager-text').text
        find_number = re.findall('\d+', paginator_text)
        return math.ceil(max([int(el) for el in find_number])/250)


    def parse_aptek_urls_and_prices(self) -> list:
        apteka_data_blocks = self.soup.select('.org-data')
        aptek_urls_and_prices = []
        for apteka_data_block in apteka_data_blocks:
            tds = apteka_data_block.select('td')
            url_aptek = tds[2].select('a')[0]['href']
            price = tds[6].select_one('.ret-drug-price').text.replace('\n', '').strip().replace(u'\xa0', u'')
            if price == 'показать цену':
                price = tds[6].select_one('.ret-drug-price')['data-err-price'].replace(u'\xa0', u'').replace('руб.', '').strip()
            if '...' in price:
                price = price.split('...')[0]
            price = float(price)
            aptek_urls_and_prices.append([url_aptek, price])
        return aptek_urls_and_prices


class AptekamosParser(Parser):
    POST_URL = 'https://aptekamos.ru/Services/WOrgs/getOrgPrice4?compressOutput=1'

    def __init__(self, name_parser: str, file_init_data: str) -> None:
        super().__init__()
        self.file_init_data = file_init_data
        self.name_parser = name_parser
        self.host = 'https://aptekamos.ru'
        self.data_catalog_name = 'aptekamos_data'
        self.proxies = None
        self.generator_proxies = Proxy()
        self.apteks = []
        self.meds = []
        self.parsed_post_data = []

    def load_initial_data(self) -> list:
        with open(self.file_init_data, 'r', encoding='utf8') as file:
            initial_data = file.read()
        apteks_urls = initial_data.split('\n')
        return apteks_urls

    @border_method_info(f'Обновление аптек...', 'Обновление аптек завершено.')
    def update_apteks(self) -> None:
        self.apteks = []
        init_apteks_urls = self.load_initial_data()
        loaded_apteks_urls = [aptek.url for aptek in self.apteks]
        apteks_urls = [url for url in init_apteks_urls if url not in loaded_apteks_urls]
        apteks_responses = self.get_responses(apteks_urls)
        print(apteks_responses)
        for apteka_response_index in range(len(apteks_responses)):
            apteka_response = apteks_responses[apteka_response_index]
            if apteka_response is None:
                while True:
                    try:
                        apteka_response = requests.get(apteks_urls[apteka_response_index],
                                                       headers=HEADERS,
                                                       proxies=self.proxies,
                                                       timeout=3)
                        break
                    except (ProxyError, ConnectTimeout, SSLError):
                        print('ProxyError')
                        self.proxies = self.generator_proxies.get_proxies()
            if apteka_response.status_code == 200:
                apteka = self._get_aptek(apteka_response.url, apteka_response.text)
                if not apteka:
                    continue
                self.apteks.append(apteka)
            elif apteka_response.status_code == 404:
                print(apteka_response.url, 'нерабочая ссылка')
            elif apteka_response.status_code == 403:
                self.proxies = self.generator_proxies.get_proxies()
                self.update_apteks()
                return
        self.save_object(self, f'parsers/{self.name_parser}')

    def _get_aptek(self, aptek_url: str, apteks_response: str) -> Union[Apteka, None]:
        """Получение аптек из запроса"""
        header_aptek = Parse(apteks_response).parse_header_aptek()
        if not header_aptek:
            return None
        aptek_name = str()
        for name in NAMES_APTEK:
            if name in header_aptek:
                aptek_name = name
                break
        aptek_address = Parse(apteks_response).parse_adress_aptek()
        aptek_url = aptek_url
        aptek_id = aptek_url.replace('/ob-apteke', '').split('-')[-1]
        return Apteka(name=aptek_name,
                      url=aptek_url,
                      address=aptek_address,
                      host=self.host,
                      host_id=int(aptek_id))

    @border_method_info('Обновление лекарств...', 'Обновление лекарств завершено.')
    def update_meds(self) -> None:
        self.meds = []
        try:
            response = requests.get(self.host + '/tovary', headers=HEADERS, proxies=self.proxies)
        except (ProxyError, ConnectTimeout):
            self.proxies = self.generator_proxies.get_proxies()
            self.update_meds()
            return
        if response.status_code == 403:
            self.proxies = self.generator_proxies.get_proxies()
            self.update_meds()
            return
        max_page_in_catalog = Parse(response.text).parse_max_page_in_catalogs()
        page_urls = [self.host + '/tovary']
        page_urls.extend([f'https://aptekamos.ru/tovary?page={i}' for i in range(2, max_page_in_catalog + 1)])
        splited_urls = self.split_list(page_urls, 100)
        for url_list in splited_urls:
            responses = self.get_responses(url_list)
            for response in responses:
                meds = self._get_meds_from_response(response)
                self.meds.extend(meds)
                print(f'Кол-во лекарств {len(self.meds)}')

    def _get_meds_from_response(self, response: Response) -> list:
        meds = []
        if response.status_code == 200:
            names_urls_ids_meds = Parse(response.text).parse_names_urls_ids_meds()
            for name_url_id_med in names_urls_ids_meds:
                med = Med(name=name_url_id_med['name'], url=name_url_id_med['url'], host_id=name_url_id_med['id'])
                meds.append(med)
            return meds
        if response.status_code == 403:
            self.proxies = self.generator_proxies.get_proxies()
            response = requests.get(response.url, headers=HEADERS, proxies=self.proxies)
            return self._get_meds_from_response(response)

    @border_method_info('Обновление цен...', 'Обновление цен завершено.')
    def update_prices(self):
        if not self.apteks:
            self.update_apteks()
        if not self.meds:
            self.update_meds()
        all_search_phrases = self._get_all_post_data()
        for search_phrase in all_search_phrases:
            INFO = f'[INFO {self.host}] apteka {self.apteks.index(search_phrase.apteka)}/{len(self.apteks)}' \
                   f' med {self.meds.index(search_phrase.med)}/{len(self.meds)}'
            print(INFO)
            response = self._get_response(search_phrase)
            prices = self._get_prices_from_response(response, search_phrase)
            for price in prices:  # почему не интерируется цена?
                print(price)
                db.add_price(price)
            self.parsed_post_data.append(search_phrase.post_data)
            self.save_object(self, f'parsers/{self.name_parser}')
            db.aptek_update_updtime(search_phrase.apteka)  # Обновление времении внести в модуль db

    @border_method_info('Обновление цен...', 'Обновление цен завершено.')
    def async_update_prices(self):
        if not self.apteks:
            self.update_apteks()
        if not self.meds:
            self.update_meds()
        all_search_phrases = self._get_all_post_data()
        splited_search_phrases = self._split_generator(all_search_phrases, 100)
        for list_search_phrases in splited_search_phrases:
            prices = self._get_prices_from_list_search_phrases(list_search_phrases)
            for price in prices:
                db.add_price(price)
            for search_phrase in list_search_phrases:
                self.parsed_post_data.append(search_phrase.post_data)
                db.aptek_update_updtime(search_phrase.apteka)
            INFO = f'[INFO {self.host}] apteka {self.apteks.index(list_search_phrases[-1].apteka)}/{len(self.apteks)}' \
                   f' med {self.meds.index(list_search_phrases[-1].med)}/{len(self.meds)}'
            print(INFO)
            self.save_object(self, f'parsers/{self.name_parser}')

    def _get_prices_from_list_search_phrases(self, list_search_phrases: list) -> Iterator[Price]:
        json_prices = self._get_prices_from_json(list_search_phrases)
        html_prices = self._get_prices_from_html(list_search_phrases)
        json_prices.extend(html_prices)
        for prices_generator in json_prices:
            for price in prices_generator:
                yield price

    def _get_prices_from_json(self, list_search_phrases: list) -> list:
        post_urls = [self.POST_URL for _ in range(len(list_search_phrases))]
        post_data = [search_phrase.post_data for search_phrase in list_search_phrases]
        json_responses = self.post_responses(post_urls, post_data)
        all_json_prices = []
        for json_response in json_responses:
            if json_response.status_code == 200:
                json_prices = self._get_prices_from_response(json_response.text,
                                                             list_search_phrases[json_responses.index(json_response)])
                all_json_prices.append(json_prices)
        return all_json_prices

    def _get_prices_from_html(self, list_search_phrases: list) -> list:
        post_urls = [self.POST_URL for _ in range(len(list_search_phrases))]
        post_data = [search_phrase.post_data for search_phrase in list_search_phrases]
        json_responses = self.post_responses(post_urls, post_data)
        list_search_phrases_for_get_request = []
        for json_response in json_responses:
            if json_response.status_code != 200:
                list_search_phrases_for_get_request.append(list_search_phrases[json_responses.index(json_response)])
        get_urls = self._get_urls_for_get_requests(list_search_phrases_for_get_request)
        html_responses = self.get_responses(get_urls)
        all_html_prices = []
        for html_response in html_responses:
            html_prices = self._get_prices_from_response(html_response.text,
                                                         list_search_phrases_for_get_request[
                                                             html_responses.index(html_response)])
            all_html_prices.append(html_prices)
        return all_html_prices

    @staticmethod
    def _get_urls_for_get_requests(search_phrases: list) -> list:
        urls = []
        for search_phrase in search_phrases:
            aptek_url = search_phrase.apteka.url.replace('ob-apteke', '')
            url = f"{aptek_url}price-list?q={search_phrase.post_data['searchPhrase']}&i=&deliv=0&rsrv=0&sale=0&_={int(time.time() * 1000)}"
            urls.append(url)
        return urls

    @staticmethod
    def _is_json_response(response: str) -> bool:
        try:
            json.loads(response)
            return True
        except JSONDecodeError:
            return False

    @staticmethod
    def _split_generator(lst: Iterator[SearchPhrase], size_lst: int) -> Iterator[list]:
        count = 0
        splited_list = []
        for el in lst:
            count += 1
            splited_list.append(el)
            if count == size_lst:
                yield splited_list
                count = 0
                splited_list = []
        yield splited_list

    def _get_response(self, search_phrase: SearchPhrase) -> str:
        response = self.request.post(self.POST_URL, json_data=search_phrase.post_data)
        if response.status_code == 403:
            aptek_url = search_phrase.apteka.url.replace('ob-apteke', '')
            url = f"{aptek_url}price-list?q={search_phrase.post_data['searchPhrase']}&i=&deliv=0&rsrv=0&sale=0&_={int(time.time() * 1000)}"
            response = self.request.get(url)
            if response.status_code != 200:
                print(response)
                sys.exit()
        return response.text

    @staticmethod
    def _get_prices_from_response(response: str, search_phrase: SearchPhrase) -> list:
        ids_titles_prices_in_meds = Parse(response).parse_ids_titles_prices_in_meds()
        for id_title_price_in_med in ids_titles_prices_in_meds:
            med = Med(name=id_title_price_in_med['title'],
                      url=search_phrase.med.url,
                      host_id=id_title_price_in_med['id'])
            price = Price(med=med,
                          apteka=search_phrase.apteka,
                          rub=float(id_title_price_in_med['price']))
            yield price

    def _get_all_post_data(self) -> Iterator[SearchPhrase]:
        for aptek in self.apteks:
            for med in self.meds:
                post_data = {"orgId": int(aptek.host_id), "wuserId": 0, "searchPhrase": med.name}
                if post_data not in self.parsed_post_data:
                    search_phrase = SearchPhrase(med=med,
                                                 apteka=aptek,
                                                 post_data={"orgId": int(aptek.host_id), "wuserId": 0,
                                                            "searchPhrase": med.name})
                    yield search_phrase

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
        self.save_object(meds, 'meds_info')  # ДЛЯ ДЕБАГА !! УДАЛИТЬ
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

    def get_responses(self, urls: list) -> list:
        responses = (grequests.get(u,
                                   headers=HEADERS,
                                   proxies=self.proxies) for u in urls)
        return grequests.map(responses)

    def post_responses(self, post_urls: list, post_data: list) -> list:
        responses = (grequests.post(post_urls[i],
                                    json=post_data[i],
                                    headers=HEADERS,
                                    proxies=self.proxies) for i in range(len(post_urls)))
        return grequests.map(responses)


class AptekamosParserRemake(AptekamosParser):
    def __init__(self, name_parser: str, file_init_data: str) -> None:
        super().__init__(name_parser, file_init_data)
        self.progress = str()
        self.parsed_pages = []

    def update_data(self):
        if not self.apteks:
            self.update_apteks()
        response = self._get_response(self.host + '/tovary')
        max_page_in_catalog = Parse(response.text).parse_max_page_in_catalogs()
        pages_urls = [self.host + '/tovary']
        pages_urls.extend([f'https://aptekamos.ru/tovary?page={i}' for i in range(2, max_page_in_catalog + 1)])
        for url_catalog_page in pages_urls:
            if url_catalog_page in self.parsed_pages:
                continue
            self.progress = f'{pages_urls.index(url_catalog_page)} / {len(pages_urls)}'
            response_page_catalog = self._get_response(url_catalog_page)
            meds = self._get_meds_from_response(response_page_catalog)
            for med in meds:
                response_med = self._get_response(med.url)
                time.sleep(5)
                if self._is_different_packaging(response_med):
                    packs = self._get_packs(med.host_id)
                    for pack in packs:
                        url_filter_pack = med.url + f'?llat=0.0&llng=0.0&on=&so=0&p={pack}&f=&c=&page=1&min=0&max=0&deliv=0&rsrv=0&sale=0&st=0&r=&me=0&duty=0&mn=0'
                        response_med_pack = self._get_response(url_filter_pack)
                        self._update_prices(response_med_pack, med)
                else:
                    self._update_prices(response_med, med)
            self.parsed_pages.append(url_catalog_page)

    def update_apteks(self):
        self.apteks = {}
        init_apteks_urls = self.load_initial_data()
        for aptek_url in init_apteks_urls:
            response = self._get_response(aptek_url)
            if not response:
                continue
            self.apteks[aptek_url] = self._get_aptek(response)

    def _get_aptek(self, response: Response):
        """Получение аптек из запроса"""
        header_aptek = Parse(response.text).parse_header_aptek()
        if not header_aptek:
            return None
        aptek_name = str()
        for name in NAMES_APTEK:
            if name in header_aptek:
                aptek_name = name
                break
        aptek_address = Parse(response.text).parse_adress_aptek()
        aptek_url = response.url
        aptek_id = aptek_url.replace('/ob-apteke', '').split('-')[-1]
        apteka = Apteka(name=aptek_name,
                        url=aptek_url,
                        address=aptek_address,
                        host=self.host,
                        host_id=int(aptek_id))
        print(apteka)
        return apteka

    def _update_prices(self, response: Response, med: Med):
        print(response.url)
        parser = Parse(response.text)
        med_name = parser.parse_med_name()
        med = Med(name=med_name, url=med.url, host_id=med.host_id)
        max_page_aptek = parser.parse_max_page_aptek()
        parsers = [parser]
        if max_page_aptek > 1:
            for page in range(2, max_page_aptek + 1):
                if re.search('&page=', response.url):
                    page_url = re.sub('&page=\d+&', f'&page={page}&', response.url)
                else:
                    page_url = response.url + f'?llat=0.0&llng=0.0&on=&so=0&p=0&f=0&c=0&page={page}&min=0&max=0&deliv=0&rsrv=0&sale=0&st=0&r=&me=0&duty=0&mn=0'
                print(page_url)
                time.sleep(5)
                response_page = self._get_response(page_url)
                if not response_page:
                    continue
                parsers.append(Parse(response_page.text))
        for parser in parsers:
            aptek_urls_and_prices = parser.parse_aptek_urls_and_prices()
            for aptek_url, price in aptek_urls_and_prices:
                if aptek_url in self.apteks:
                    apteka = self.apteks[aptek_url]
                    price = Price(apteka=apteka, med=med, rub=price)
                    db.add_price(price)
                    db.aptek_update_updtime(apteka)
                    print(self.progress)

    def _get_packs(self, med_host_id: int) -> list:
        filter_url = f'https://aptekamos.ru/Services/WProducts/getMedFilters?medId={med_host_id}&regionId=1&compressOutput=1&_={time.time() * 1000}'
        response_filter = self._get_response(filter_url)
        response_filter_json = response_filter.json()
        packs = [pack['pack'] for pack in response_filter_json['packs']]
        return packs

    @staticmethod
    def _is_different_packaging(response: Response) -> bool:
        soup = BeautifulSoup(response.content, 'lxml')
        block_packaging = soup.select_one('.pack-num.ret-flt-function.function')
        if block_packaging:
            return True

    def _get_meds_from_response(self, response: Response):
        meds = []
        if not response:
            return []
        names_urls_ids_meds = Parse(response.text).parse_names_urls_ids_meds()
        for name_url_id_med in names_urls_ids_meds:
            med = Med(name=name_url_id_med['name'], url=name_url_id_med['url'], host_id=name_url_id_med['id'])
            meds.append(med)
        return meds

    def _get_response(self, url: str) -> Response:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response
        elif response.status_code == 403:
            return


if __name__ == '__main__':
    NAME_PARSER = 'aptekamos'
    if NAME_PARSER in os.listdir('parsers'):
        parser = Parser().load_object(f'parsers/{NAME_PARSER}')
    else:
        parser = AptekamosParserRemake(NAME_PARSER, 'init_data/aptekamos_init_data.txt')
    try:
        parser.update_data()
    except Exception as ex:
        print(traceback.format_exc())
        parser.save_object(parser, f'parsers/{parser.name_parser}')
