from parsing_base import Parser
from bs4 import BeautifulSoup
from dataclasses import dataclass
import re
import base64


class AdvancedProxy(Parser):
    HOST = 'https://advanced.name/'

    def __init__(self) -> None:
        super().__init__()
        self.proxies_list = []

    def update_proxie_list(self) -> None:
        resp = self.request.get(self.HOST + 'ru/freeproxy?type=https')
        self.save_html(resp.text, 'test.html')
        soup = BeautifulSoup(resp.text, 'lxml')
        self.proxies_list = self._get_proxies_from_soup(soup)
        print(self.proxies_list)

    @staticmethod
    def _get_proxies_from_soup(soup: BeautifulSoup) -> list:
        print(soup)


@dataclass
class Proxy:
    ip: str
    port: int
    protocol: str


if __name__ == '__main__':
    proxy = AdvancedProxy()
    proxy.update_proxie_list()