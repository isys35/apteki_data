from parsing_base import Parser
from bs4 import BeautifulSoup
import apteka
import db
from aiohttp.client_exceptions import ClientPayloadError
import requests
import time
from requests.exceptions import ConnectionError


class GorZdrafParser(Parser):
    def __init__(self):
        super().__init__()
        self.host = 'https://gorzdrav.org'
        self.apteks = []
        self.name = 'gorzdrav'

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

    def load_initial_data(self):
        with open("gorzdraf_init_data.txt", 'r', encoding='utf8') as file:
            initial_data = file.read()
        apteks_urls = initial_data.split('\n')
        return apteks_urls

    def update_prices(self):
        print('[INFO] Обновление цен...')
        self.update_apteks()
        url_categories_with_pages = self.get_url_categories_with_pages()
        count_cicle = sum([len(lst) for lst in url_categories_with_pages]) * len(self.apteks)
        print(f"[INFO] Всего {count_cicle} циклов")
        for aptek in self.apteks:
            print(aptek)
            for category in url_categories_with_pages:
                for page_url in category:
                    start_time = time.time()
                    while True:
                        try:
                            self.get_meds_and_price(page_url, aptek)
                            break
                        except ConnectionError:
                            print(ConnectionError)
                            time.sleep(60)
                    count_cicle -= 1
                    time_per_cicle = time.time()-start_time
                    print(f"[INFO] Осталось {count_cicle} циклов примерно {int(time_per_cicle * count_cicle/60)} минут")
        print('[INFO] Обновление цен завершено')


    def get_meds_and_price(self, url, aptek):
        cookies = {'FAVORITESTORE': f'{aptek.host_id}'}
        resp = requests.get(url, cookies=cookies)
        soup = BeautifulSoup(resp.text, 'lxml')
        product_blocks = soup.select('.c-prod-item.c-prod-item--grid')
        csrf_token = soup.find('input', attrs={'name': 'CSRFToken'})['value']
        indexes = ','.join([product_block.select_one('a')['data-gtm-id'] for product_block in product_blocks])
        json_data = {'CSRFToken': csrf_token, 'products': indexes}
        while True:
            post_resp = requests.post('https://gorzdrav.org/stockdb/ajax/posCount', headers=self.request.headers, data=json_data, cookies=cookies)
            if post_resp.status_code == 200:
                json_info = post_resp.json()
                break
            else:
                time.sleep(1)
                print(post_resp)
        check_favorite = [el['product'] for el in json_info if el['favouriteStoreCountReservation']]
        for product_block in product_blocks:
            index = product_block.select_one('a')['data-gtm-id']
            if index not in check_favorite:
                continue
            url = self.host + product_block.select_one('a')['href']
            title = product_block.select_one('a')['data-gtm-name']
            rub = product_block.find('meta', attrs={'itemprop': 'price'})['content']
            med = apteka.Med(name=title, url=url, host_id=index)
            price = apteka.Price(apteka=aptek, med=med, rub=rub)
            # print(price)
            db.add_price(price)

    def update_apteks(self):
        print('[INFO] Получение аптек...')
        resp = self.request.get(self.host + '/apteki/list/')
        apteks_url = self.load_initial_data()
        max_page = self.get_max_page(resp.text)
        urls = [self.host + '/apteki/list/']
        extend_list = [self.host + f'/apteki/list/?page={page}' for page in range(1, max_page)]
        urls.extend(extend_list)
        resps = self.get_resps(urls)
        self.apteks = []
        for resp in resps:
            soup = BeautifulSoup(resp, 'lxml')
            rows_table_apteks = soup.select('.b-table__row')
            for row in rows_table_apteks:
                if 'b-table__head' not in row['class']:
                    id = int(row.select_one('.b-store-favorite__btn.js-favorites-store.js-text-hint')['data-store'])
                    adress = row.select_one('.c-pharm__descr').text.replace('\n', '').lstrip()
                    url = f"{self.host}/apteki/{id}/"
                    if url in apteks_url:
                        aptek = apteka.Apteka(host_id=id,
                                                name='ГОРЗДРАВ',
                                                address=adress,
                                                host=self.host,
                                                url= f"{self.host}/apteki/{id}")
                        self.apteks.append(aptek)
        print('[INFO] Аптеки получены')

    def get_resps(self, urls):
        try:
            resps = self.requests.get(urls)
        except ClientPayloadError:
            resps = [self.request.get(url).text for url in urls]
        return resps

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
    #cookies = {'FAVORITESTORE': '74227'}
    #resp = requests.get(parser.host, cookies=cookies)
    #parser.save_html(resp.text, 'test.html')
    parser.update_prices()





