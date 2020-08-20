import requests
import random
from requests.exceptions import ProxyError, ConnectTimeout, SSLError, ConnectionError


class Proxy:
    def __init__(self):
        self.proxies_list = []

    def get_proxies(self) -> dict:
        if not self.proxies_list:
            with open('proxies.txt', 'r') as proxy_file:
                self.proxies_list = proxy_file.read().split('\n')
        random.shuffle(self.proxies_list)
        while True:
            try:
                proxies = {'https': self.proxies_list.pop()}
                resp = requests.get('https://www.google.com/', proxies=proxies, timeout=3)
                print(f'{resp.status_code} {proxies} работает')
                return proxies
            except (ProxyError, ConnectTimeout, SSLError, ConnectionError):
                print(f'{proxies} ProxyError')



if __name__ == '__main__':
    Proxy().get_proxies()