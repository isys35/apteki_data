import requests
from bs4 import BeautifulSoup as BS
from urllib.parse import quote
from parsing_base import Parser
import apteka
import db


class StolichnikiParser(Parser):
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

    def __init__(self):
        super().__init__()
        self.host = 'https://stolichki.ru'
        self.data_catalog_name = 'stolichniki_data'
        self.name = 'столички'
        self.apteks = []
        self.meds = []
        self.prices = []
        self.keys_for_searching = [quote(key) for key in list('qwertyuiopasdfghjklzxcvbnm1234567890йцукенгшщзхъфывапролджэячсмитьбю')]

    def update_apteks(self):
        print('UPDATE APTEKS')
        resp = requests.get('https://stolichki.ru/apteki', headers=self.HEADERS)
        soup = BS(resp.text, 'lxml')
        csrf_token = soup.find('meta', attrs={'name': "csrf-token"})['content']
        self.HEADERS_JSON['X-CSRF-TOKEN'] = csrf_token
        resp = requests.get('https://stolichki.ru/stores/all?cityId=1', headers=self.HEADERS_JSON)
        json_resp = resp.json()
        stores = json_resp['stores']
        self.apteks = []
        for store in stores:
            url = self.host + f"/apteki/{store['id']}"
            host_id = store['id']
            address = store['full_address']
            name = 'Столички'
            host = self.host
            self.apteks.append(apteka.Apteka(url=url,
                                             host_id=host_id,
                                             address=address,
                                             name=name,
                                             host=host))

    def update_prices(self):
        print('UPDATE PRICES')
        self.update_apteks()
        for aptek in self.apteks:
            print(aptek.url)
            urls_with_keys = [aptek.url + '?q=' + key for key in self.keys_for_searching]
            count_urls = len(urls_with_keys)
            resps = self.requests.get(urls_with_keys)
            for resp_index in range(count_urls):
                print(urls_with_keys[resp_index])
                meds = self.parsing_meds(resps[resp_index])
                for med_data in meds:
                    try:
                        # исправить!!!!! не видит аптеку 1032
                        med = apteka.Med(name=med_data['title'],
                                         url=med_data['url'],
                                         host_id=med_data['id'])
                        price = apteka.Price(apteka=aptek, med=med, rub=med_data['price'])
                        db.add_price(price)
                        self.prices.append(price)
                    except OSError:
                        continue
            db.aptek_update_updtime(aptek)
        print('UPDATE COMPLETE')

    def parsing_meds(self, resp):
        soup = BS(resp, 'lxml')
        table = soup.select_one('.table.products-list-in-store')
        meds = []
        if not table:
            return meds
        meds_soup = table.select_one('tbody').select('tr')
        for med_soup in meds_soup:
            title = med_soup.select_one('.store-info').select_one('a').text
            id = med_soup.select_one('.store-info').select_one('a')['href'].split('/')[-1]
            url = self.host + med_soup.select_one('.store-info').select_one('a')['href']
            print(title, id)
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


if __name__ == '__main__':
    parser = Stolichniki()
    parser.update_prices()
