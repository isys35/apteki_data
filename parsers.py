from parsing_base import Parser
from bs4 import BeautifulSoup
from apteka import Apteka, Med, Price, NAMES_APTEK
from aiohttp.client_exceptions import ClientConnectorError
import json
import db


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


class AptekamosParser(Parser):
    def __init__(self):
        super().__init__()
        self.file_init_data = "aptekamos_init_data.txt"
        self.host = 'https://aptekamos.ru'
        self.apteks = []
        self.meds = []

    def load_initial_data(self):
        with open(self.file_init_data, 'r', encoding='utf8') as file:
            initial_data = file.read()
        apteks_urls = initial_data.split('\n')
        return apteks_urls

    @border_method_info(f'Обновление аптек...', 'Обновление аптек завершено.')
    def update_apteks(self):
        self.apteks = []
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
        self.update_prices()
        count_position = len(self.apteks) * len(self.meds)
        print(f"[INFO {self.host}] Всего {count_position} позиций для проверки")
        post_url = self.host + '/Services/WOrgs/getOrgPrice4?compressOutput=1'
        for aptek in self.apteks:
            splited_meds = self.split_list(self.meds, 100)
            for med_list in splited_meds:
                post_urls = [post_url for _ in range(len(med_list))]
                post_data = [{"orgId": int(aptek.host_id), "wuserId": 0, "searchPhrase": med.name} for med in med_list]
                responses = self.post_responses(post_urls, post_data)
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
                    print(f"[INFO {self.host}] Осталось {count_position} позиций для проверки")
            db.aptek_update_updtime(aptek)

    def get_responses(self, urls):
        try:
            resps = self.requests.get(urls)
        except ClientConnectorError:
            resps = [self.request.get(url).text for url in urls]
        return resps

    def post_responses(self, post_urls, post_data):
        try:
            responses = self.requests.post(post_urls, json_data=post_data)
        except ClientConnectorError:
            responses = []
            for id in range(len(post_urls)):
                response = self.request.post(post_urls[id], json_data=post_data[id])
                responses.append(response.text)
        return responses


if __name__ == '__main__':
    parser = AptekamosParser()
    parser.update_prices()