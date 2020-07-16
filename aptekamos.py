from parsing_base import Parser
from bs4 import BeautifulSoup
from threading import Thread
import apteka
import json
import db
import sys
from aiohttp.client_exceptions import ClientConnectorError
from urllib.parse import unquote, quote
import os
import pickle


class AptekamosParser(Parser):
    SIZE_ASYNC_REQUEST = 100

    def __init__(self):
        super().__init__()
        self.host = 'https://aptekamos.ru'
        self.name = 'aptekamos'
        self.data_catalog_name = 'aptekamos_data'
        self.apteks = []
        self.meds = []

    def load_initial_data(self):
        with open(f"aptekamos_init_data.txt", 'r', encoding='utf8') as file:
            initial_data = file.read()
        apteks_urls = initial_data.split('\n')
        return apteks_urls

    def update_apteks(self):
        print('UPDATE APTEKS')
        self.apteks = []
        apteks_url = self.load_initial_data()
        apteks_resp = self.requests.get(apteks_url)
        count_apteks = len(apteks_url)
        for aptek_resp_index in range(count_apteks):
            soup = BeautifulSoup(apteks_resp[aptek_resp_index], 'lxml')
            print(apteks_url[aptek_resp_index])
            header_aptek = soup.select_one('#main-header').select_one('h1').text
            aptek_name = str()
            for name in apteka.NAMES:
                if name in header_aptek:
                    aptek_name = name
                    break
            aptek_address = soup.select_one('#org-addr').text.replace('\n', '').strip()
            aptek_url = apteks_url[aptek_resp_index]
            aptek_id = aptek_url.replace('/ob-apteke', '').split('-')[-1]
            self.apteks.append(apteka.Apteka(name=aptek_name,
                                             url=aptek_url,
                                             address=aptek_address,
                                             host=self.host,
                                             host_id=int(aptek_id)))

    def update_meds(self):
        print('UPDATE MEDS')
        max_page_in_catalog = self.get_max_page_in_catalog()
        print(f"{max_page_in_catalog} максимальное кол-во страниц в каталоге")
        page_urls = [self.host + '/tovary']
        page_urls.extend([f'https://aptekamos.ru/tovary?page={i}' for i in range(2, max_page_in_catalog + 1)])
        splited_urls = self.split_list(page_urls, 100)
        for url_list in splited_urls:
            responses = self.requests.get(url_list)
            for url in url_list:
                print(url)
                response = responses[url_list.index(url)]
                self.pars_page(response)

    def pars_page(self, response):
        soup = BeautifulSoup(response, 'lxml')
        meds_in_page = soup.select('.ret-med-name')
        for med in meds_in_page:
            a = med.select_one('a')
            if a:
                name = a['title'].replace('цена', '').strip()
                id = int(a['href'].split('-')[-1].replace('/ceni', ''))
                self.meds.append(apteka.Med(name=name,
                                            url=a['href'],
                                            host_id=id))

    def get_max_page_in_catalog(self):
        url = self.host + '/tovary'
        resp = self.requests.get([url])
        soup = BeautifulSoup(resp[0], 'lxml')
        pager_text = soup.select_one('#d-table-pager-text').text
        meds = int(pager_text.split(' ')[-1])
        pages = (meds // 100) + 1
        return pages

    def update_prices(self):
        if not self.apteks:
            self.update_apteks()
        if not self.meds:
            self.update_meds()
        print('UPDATE PRICES')
        self.prices = []
        price_updater_threads = [PriceUpdater(self, aptek) for aptek in self.apteks]
        for thr in price_updater_threads:
            thr.start()

    @staticmethod
    def pars_med(response_txt):
        resp_json = json.loads(response_txt)
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


class PriceUpdater(Thread):
    def __init__(self, parser, aptek):
        super().__init__()
        self.parser = parser
        self.aptek = aptek
        self.is_finished = False

    def update_prices(self):
        post_url = self.parser.host + '/Services/WOrgs/getOrgPrice4?compressOutput=1'
        for med in self.parser.meds:
            post_data = {"orgId": int(self.aptek.host_id), "wuserId": 0, "searchPhrase": med.name}
            response = self.parser.request.post(post_url, json_data=post_data)
            if response.status_code != 200:
                with open(f"{self.aptek.host_id}.txt", 'w') as f:
                        f.write(f"{response.status_code}")
                sys.exit()
            download_meds = self.parser.pars_med(response.text)
            for med_data in download_meds:
                med = apteka.Med(name=med_data['title'],
                                 url= med.url,
                                 host_id=med_data['id'])
                price = apteka.Price(med=med,
                                     apteka=self.aptek,
                                     rub=float(med_data['price']))
                print(price.rub, price.apteka.name, price.apteka.address)
                db.add_price(price)

    def run(self):
        try:
            self.update_prices()
            self.is_finished = True
        except Exception as ex:
            with open(f"{self.aptek.host_id}_except.txt", 'w') as f:
                f.write(f"{ex}")
        print('[FINISH] ' + str(self.aptek))


class AptekamosParser2(AptekamosParser):
    def __init__(self):
        super().__init__()

    def update_prices(self):
        if not self.apteks:
            self.update_apteks()
        if not self.meds:
            self.update_meds()
        print('UPDATE PRICES')
        self.prices = []
        post_url = self.host + '/Services/WOrgs/getOrgPrice4?compressOutput=1'
        for aptek in self.apteks:
            for med in self.meds:
                post_data = {"orgId": int(aptek.host_id), "wuserId": 0, "searchPhrase": med.name}
                response = self.request.post(post_url, json_data=post_data)
                download_meds = self.pars_med(response.text)
                for med_data in download_meds:
                    med = apteka.Med(name=med_data['title'],
                                     url=med.url,
                                     host_id=med_data['id'])
                    price = apteka.Price(med=med,
                                         apteka=aptek,
                                         rub=float(med_data['price']))
                    print(price)
                    db.add_price(price)


class AptekamosParser3(AptekamosParser):
    def __init__(self):
        super().__init__()

    def update_prices(self):
        if not self.apteks:
            self.update_apteks()
        if not self.meds:
            self.update_meds()
        print('UPDATE PRICES')
        post_url = self.host + '/Services/WOrgs/getOrgPrice4?compressOutput=1'
        for aptek in self.apteks:
            splited_meds = self.split_list(self.meds, 100)
            for med_list in splited_meds:
                post_urls = [post_url for _ in range(len(med_list))]
                post_data = [{"orgId": int(aptek.host_id), "wuserId": 0, "searchPhrase": med.name} for med in med_list]
                responses = self.post_responses(post_urls, post_data)
                for response in responses:
                    index = responses.index(response)
                    download_meds = self.pars_med(response)
                    for med_data in download_meds:
                        med = apteka.Med(name=med_data['title'],
                                         url=med_list[index].url,
                                         host_id=med_data['id'])
                        price = apteka.Price(med=med,
                                             apteka=aptek,
                                             rub=float(med_data['price']))
                        print(price)
                        db.add_price(price)
            db.aptek_update_updtime(aptek)

    def update_info(self, meds):
        if 'descriptions' not in os.listdir():
            os.mkdir('descriptions')
        meds = [med for med in meds if not med.description]
        count_meds = len(meds)
        print(f'Поиск препаратов на cайте {self.host}')
        print(f'Всего {count_meds} препаратов')
        splited_meds = self.split_list(meds, 50)
        for med_list in splited_meds:
            urls = self.get_search_urls(med_list)
            resps = self.get_responses(urls)
            for med in med_list:
                index = med_list.index(med)
                description_url = self.get_desription_url(resps[index])
                if description_url:
                    med.set_description_url(description_url)
                count_meds -= 1
                print(f'Осталось {count_meds}')
        with open('meds', 'wb') as meds_file:
            pickle.dump(meds, meds_file)
        self.get_description_and_img(meds)

    def get_responses(self, urls):
        try:
            resps = self.requests.get(urls)
        except Exception:
            resps = [self.request.get(url).text for url in urls]
        return resps


    def get_description_and_img(self, meds):
        print(f'Получение описания и картинок для препаратов на {self.host}')
        meds = [med for med in meds if med.description_url]
        count_meds = len(meds)
        print(f'Всего {count_meds} препаратов')
        splited_meds = self.split_list(meds, 50)
        for med_list in splited_meds:
            urls = [med.description_url for med in med_list]
            resps = self.get_responses(urls)
            for med in med_list:
                index = med_list.index(med)
                description, image_url = self.pars_description_page(resps[index])
                self.save_info(med.id, image_url, description)
                count_meds -= 1
                print(f'Осталось {count_meds}')

    @staticmethod
    def pars_description_page(resp):
        soup = BeautifulSoup(resp, 'lxml')
        descriptions = soup.find_all('meta', attrs={'name': 'description'})
        descriptions = '\n'.join([description['content'] for description in descriptions])
        image_url = soup.select_one('#med-img')
        if image_url:
            image_url = image_url['src']
        return descriptions, image_url

    @staticmethod
    def get_desription_url(resp):
        soup = BeautifulSoup(resp, 'lxml')
        table = soup.select_one('#data')
        url_block = table.select_one('.med-info-img')
        if url_block:
            return url_block['href']

    def get_search_urls(self, med_list):
        urls = []
        for med in med_list:
            if '№' in med.name:
                url = self.host + '/tovary/poisk?q=' + quote(med.name.split('№')[0])
            else:
                url = self.host + '/tovary/poisk?q=' + quote(med.name)
            urls.append(url)
        return urls


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
    parser = AptekamosParser3()
    parser.update_prices()

