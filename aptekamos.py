import json
import os
import time
from urllib.parse import quote
from typing import Union

from concurrent.futures._base import TimeoutError
from aiohttp.client_exceptions import ClientConnectorError
from bs4 import BeautifulSoup
import requests
from json.decoder import JSONDecodeError
import sys
import db
from apteka import Apteka, Med, Price, NAMES_APTEK
from parsing_base import Parser, border_method_info


class Parse:
    def __init__(self, response_text):
        self.response_text = response_text

    def parse_header_aptek(self) -> str:
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

    def parse_ids_titles_prices_meds(self) -> list:
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

    @border_method_info('Обновление цен...', 'Обновление цен завершено.')
    def update_prices(self):
        self.update_apteks()
        self.update_meds()
        all_post_data = self._get_all_post_data()
        print(all_post_data)

    def _get_all_post_data(self) -> list:
        for aptek in self.apteks:
            for med in self.meds:
                yield {"orgId": int(aptek.host_id), "wuserId": 0, "searchPhrase": med.name}

        #     splited_meds = self.split_list(self.meds, 100)
        #     for med_list_index in range(len(splited_meds)):
        #         med_list = splited_meds[med_list_index]
        #         post_data, post_urls = self.get_post_request_data(aptek, med_list)
        #         if not post_data:
        #             continue
        #         responses = self.post_responses(post_urls, post_data)
        #         for response_index in range(len(responses)):
        #             print(f' aptek {aptek_index}/{len(self.apteks)-1};\n'
        #                   f' med_list {med_list_index}/{len(splited_meds)-1};\n'
        #                   f' response {response_index}/{len(responses)-1}')
        #             try:
        #                 json.loads(responses[response_index])
        #             except JSONDecodeError:
        #                 print('JSONDecodeError')
        #                 self.save_object(self, f'parsers/{self.name_parser}')
        #                 return
        #             ids_titles_prices_meds = Parse(responses[response_index]).parse_ids_titles_prices_meds_in_aptekamos()
        #             for id_title_price_med in ids_titles_prices_meds:
        #                 med = Med(name=id_title_price_med['title'],
        #                           url=med_list[response_index].url,
        #                           host_id=id_title_price_med['id'])
        #                 price = Price(med=med,
        #                               apteka=aptek,
        #                               rub=float(id_title_price_med['price']))
        #                 print(price)
        #                 db.add_price(price)
        #             self.parsed_post_data.append(post_data[response_index])
        #             self.save_object(self, f'parsers/{self.name_parser}')
        #     db.aptek_update_updtime(aptek)
        # self.parsed_post_data = []
        # self.apteks = []
        # self.meds = []

    def get_post_request_data(self, aptek, med_list):
        post_data = [{"orgId": int(aptek.host_id), "wuserId": 0, "searchPhrase": med.name} for med in med_list]
        post_data = [el for el in post_data if el not in self.parsed_post_data]
        post_urls = [self.POST_URL for _ in range(len(post_data))]
        return post_data, post_urls

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
                try:
                    response = self.request.post(post_urls[id], json_data=post_data[id])
                except (ClientConnectorError, TimeoutError):
                    time.sleep(200)
                    return self.post_responses(post_urls, post_data)
                responses.append(response.text)
        return responses


if __name__ == '__main__':
    parser = Parser().load_object('parsers/aptekamos')
    parser.update_prices()

