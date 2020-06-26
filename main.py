from aptekazhivika import ZhivikaParser
from stolichniki import StolichnikiParser
from aptekamos import AptekamosParser3
import db
import csv_writer


def main():
    parsers = [ZhivikaParser(), StolichnikiParser(), AptekamosParser3()]
    for parser in parsers:
        parser.update_prices()
        create_catalog_csv(parser)
    create_full_catalog_csv()


def create_full_catalog_csv():
    data = db.get_data_meds()
    csv_writer.create_csv_file('каталоги/полный каталог.csv')
    csv_writer.add_data_in_catalog('каталоги/полный каталог.csv', data)


def create_catalog_csv(parser):
    data = db.get_data_meds(parser.host)
    csv_writer.create_csv_file(f'каталоги/{parser.name}.csv')
    csv_writer.add_data_in_catalog(f'каталоги/{parser.name}', data)


if __name__ == '__main__':
    create_full_catalog_csv()
