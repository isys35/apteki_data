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


@dataclass
class SearchPhrase:
    med: Med
    apteka: Apteka
    post_data: dict


class Parse:
    def __init__(self, response_text):
        self.response_text = response_text

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


class AptekamosParser(Parser):
    POST_URL = 'https://aptekamos.ru/Services/WOrgs/getOrgPrice4?compressOutput=1'

    def __init__(self, name_parser: str, file_init_data: str) -> None:
        super().__init__()
        self.file_init_data = file_init_data
        self.name_parser = name_parser
        self.host = 'https://aptekamos.ru'
        self.data_catalog_name = 'aptekamos_data'
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
        if self.apteks:
            return
        apteks_urls = self.load_initial_data()
        apteks_responses = self.get_responses(apteks_urls)
        for aptek_response_index in range(len(apteks_responses)):
            apteka = self._get_aptek(apteks_urls[aptek_response_index], apteks_responses[aptek_response_index])
            if not apteka:
                continue
            self.apteks.append(apteka)

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
        if self.meds:
            return
        response = self.request.get(self.host + '/tovary')
        max_page_in_catalog = Parse(response.text).parse_max_page_in_catalogs()
        page_urls = [self.host + '/tovary']
        page_urls.extend([f'https://aptekamos.ru/tovary?page={i}' for i in range(2, max_page_in_catalog + 1)])
        splited_urls = self.split_list(page_urls, 100)
        self.meds = []
        for url_list in splited_urls:
            responses = self.get_responses(url_list)
            for response in responses:
                names_urls_ids_meds = Parse(response).parse_names_urls_ids_meds()
                for name_url_id_med in names_urls_ids_meds:
                    med = Med(name=name_url_id_med['name'], url=name_url_id_med['url'], host_id=name_url_id_med['id'])
                    self.meds.append(med)
                    print(f'Кол-во лекарств {len(self.meds)}')

    @border_method_info('Обновление цен...', 'Обновление цен завершено.')
    def update_prices(self):
        self.update_apteks()
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
        self.update_apteks()
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
        for index_search_phrase in range(len(list_search_phrases)):
            if self._is_json_response(json_responses[index_search_phrase]):
                json_prices = self._get_prices_from_response(json_responses[index_search_phrase],
                                                             list_search_phrases[index_search_phrase])
                all_json_prices.append(json_prices)
        return all_json_prices

    def _get_prices_from_html(self, list_search_phrases: list) -> list:
        post_urls = [self.POST_URL for _ in range(len(list_search_phrases))]
        post_data = [search_phrase.post_data for search_phrase in list_search_phrases]
        json_responses = self.post_responses(post_urls, post_data)
        list_search_phrases_for_get_request = []
        for index_search_phrase in range(len(list_search_phrases)):
            if not self._is_json_response(json_responses[index_search_phrase]):
                list_search_phrases_for_get_request.append(list_search_phrases[index_search_phrase])
        get_urls = self._get_urls_for_get_requests(list_search_phrases_for_get_request)
        html_responses = self.get_responses(get_urls)
        all_html_prices = []
        for index_search_phrase in range(len(list_search_phrases_for_get_request)):
            html_prices = self._get_prices_from_response(html_responses[index_search_phrase],
                                                         list_search_phrases_for_get_request[index_search_phrase])
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
        try:
            responses = self.requests.get(urls)
        except (ClientConnectorError, TimeoutError):
            responses = [self.request.get(url).text for url in urls]
        return responses

    def post_responses(self, post_urls: list, post_data: list) -> list:
        try:
            responses = self.requests.post(post_urls, json_data=post_data)
        except (ClientConnectorError, TimeoutError):
            responses = [self.request.post(post_urls[i], json_data=post_data[i]) for i in range(len(post_urls))]
        return responses


if __name__ == '__main__':
    NAME_PARSER = 'aptekamos'
    if NAME_PARSER in os.listdir('parsers'):
        parser = Parser().load_object(f'parsers/{NAME_PARSER}')
    else:
        parser = AptekamosParser(NAME_PARSER, 'init_data/aptekamos_init_data.txt')
    try:
        parser.async_update_prices()
    except Exception as ex:
        print(traceback.format_exc())
        parser.save_object(parser, f'parsers/{parser.name_parser}')

