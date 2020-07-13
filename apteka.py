from typing import NamedTuple

NAMES = ['НЕОФАРМ',
         'ГОРЗДРАВ',
         'Планета Здоровья',
         'ВИТА Экспресс',
         'Самсон-Фарма',
         'Будь Здоров!',
         'Калина Фарм',
         'Живика',
         'Столички',
         'еАптека',
         'Ригла',
         'МАГНИТ АПТЕКА',
         'Аптека 77',
         'А5 Аптека',
         'Аптечество',
         'Аптека-Эконом',
         'ЗДОРОВ.ру',
         'Эвалар',
         'Добрая аптека',
         'МАЯК',
         'ТРИКА']


class Apteka(NamedTuple):
    host_id: int
    name: str
    url: str
    address: str
    host: str


class Med(NamedTuple):
    name: str
    url: str
    host_id: int


class MedInfo:
    def __init__(self, id,  name):
        self.name = name
        self.id = id
        self.description = str()
        self.url_image = str()
        self.description_url = str()

    def set_description(self, description):
        self.description = description

    def set_url_image(self, url_image):
        self.url_image = url_image

    def set_description_url(self, description_url):
        self.description_url = description_url


class Price(NamedTuple):
    apteka: Apteka
    med: Med
    rub: float