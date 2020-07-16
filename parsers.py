from parsing_base import Parser
from bs4 import BeautifulSoup
from apteka import Apteka, NAMES_APTEK


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


class AptekamosParser(Parser):
    def __init__(self):
        super().__init__()
        self.file_init_data = "aptekamos_init_data.txt"
        self.host = 'https://aptekamos.ru'
        self.apteks = []

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


if __name__ == '__main__':
    parser = AptekamosParser()
    parser.update_apteks()