from parsing_base import Parser
from bs4 import BeautifulSoup
from apteka import Apteka, Med, NAMES_APTEK


def border_method_info(pre_info, post_info):
    def decorator(func):
        def wrapper(*args, **kwargs):
            print(f'[INFO] {pre_info}')
            func(*args, **kwargs)
            print(f'[INFO] {post_info}')
        return wrapper
    return decorator


class Parse:
    def __init__(self, response_text):
        self.response_text = response_text

    def parse_header_aptek(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        main_header_block = soup.select_one('#main-header')
        if not main_header_block:
            return
        header_aptek_block = main_header_block.select_one('h1')
        if header_aptek_block:
            header_aptek = header_aptek_block.text
            return header_aptek

    def parse_adress_aptek(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        aptek_address = soup.select_one('#org-addr').text.replace('\n', '').strip()
        return aptek_address

    def parse_max_page_in_catalog(self):
        soup = BeautifulSoup(self.response_text, 'lxml')
        pager_text = soup.select_one('#d-table-pager-text').text
        meds = int(pager_text.split(' ')[-1])
        pages = (meds // 100) + 1
        return pages

    def parse_names_urls_ids_meds(self):
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

    @border_method_info('Обновление аптек...', 'Обновление аптек завершено.')
    def update_apteks(self):
        self.apteks = []
        apteks_urls = self.load_initial_data()
        apteks_responses = self.requests.get(apteks_urls)
        count_apteks = len(apteks_urls)
        print(f'[INFO] Всего {count_apteks} аптек')
        for aptek_response_index in range(count_apteks):
            apteka = self.get_aptek(apteks_urls, apteks_responses, aptek_response_index)
            if not apteka:
                continue
            self.apteks.append(apteka)
            print(f'[INFO] Осталось {count_apteks-aptek_response_index} аптек')

    def get_aptek(self, apteks_urls, apteks_responses, aptek_response_index):
        header_aptek = Parse(apteks_responses[aptek_response_index]).parse_header_aptek()
        if not header_aptek:
            return
        aptek_name = str()
        for name in NAMES_APTEK:
            if name in header_aptek:
                aptek_name = name
                break
        aptek_address = Parse(apteks_responses[aptek_response_index]).parse_adress_aptek()
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
        max_page_in_catalog = Parse(response.text).parse_max_page_in_catalog()
        print(f"[INFO] Всего {max_page_in_catalog} страниц в каталоге")
        page_urls = [self.host + '/tovary']
        page_urls.extend([f'https://aptekamos.ru/tovary?page={i}' for i in range(2, max_page_in_catalog + 1)])
        splited_urls = self.split_list(page_urls, 100)
        count_pages = max_page_in_catalog
        for url_list in splited_urls:
            responses = self.requests.get(url_list)
            for url in url_list:
                response = responses[url_list.index(url)]
                names_urls_ids_meds = Parse(response).parse_names_urls_ids_meds()
                for name_url_id_med in names_urls_ids_meds:
                    med = Med(name=name_url_id_med['name'], url=name_url_id_med['url'], host_id=name_url_id_med['id'])
                    self.meds.append(med)
                count_pages -= 1
                print(f"[INFO] Осталось {count_pages} страниц в каталоге")



if __name__ == '__main__':
    parser = AptekamosParser()
    parser.update_meds()