import requests
import random
from requests.exceptions import ProxyError,ConnectTimeout


def get_proxies() -> dict:
    with open('proxies.txt', 'r') as proxy_file:
        proxies_list = proxy_file.read().split('\n')
    random.shuffle(proxies_list)
    while True:
        try:
            proxies = {'https': proxies_list.pop()}
            resp = requests.get('https://www.google.com/', proxies=proxies, timeout=3)
            print(f'{resp.status_code} {proxies} работает')
            return proxies
        except (ProxyError, ConnectTimeout):
            print(f'{proxies} ProxyError')


if __name__ == '__main__':
    get_proxies()