from parsing_base import Parser
from bs4 import BeautifulSoup
from dataclasses import dataclass
import re
import base64


class FreeProxyCZ(Parser):
    HOST = 'http://free-proxy.cz/ru/'

    def __init__(self) -> None:
        super().__init__()
        self.proxies_list = []

    def update_proxie_list(self) -> None:
        resp = self.request.get(self.HOST)
        soup = BeautifulSoup(resp.text, 'lxml')
        self.proxies_list = self._get_proxies_from_soup(soup)
        print(self.proxies_list)

    @staticmethod
    def _get_proxies_from_soup(soup: BeautifulSoup) -> list:
        trs = soup.select('tr')
        proxies = []
        for tr in trs:
            tds = tr.select('td')
            if tds and tds[0].select('script') and 'class' in tds[0].attrs:
                script = tds[0].select_one('script').text
                coded_ip = re.search("""document.write\(Base64.decode\("(.*)"\)\)""", script).group(1)
                ip = base64.b64decode(coded_ip).decode('utf-8')
                port = int(tds[1].text)
                protocol = tds[2].text
                proxy = Proxy(ip, port, protocol)
                proxies.append(proxy)
        return proxies


@dataclass
class Proxy:
    ip: str
    port: int
    protocol: str


if __name__ == '__main__':
    proxy = FreeProxyCZ()
    proxy.update_proxie_list()