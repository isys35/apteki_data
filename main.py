from aptekazhivika import ZhivikaParser
from stolichniki import StolichnikiParser
import db
import csv_writer


def main():
    parsers = [ZhivikaParser(), StolichnikiParser()]
    for parser in parsers:
        parser.update_prices()


def create_full_catalog_csv():
    data = db.get_data_meds()
    csv_writer.create_csv_file('каталоги/полный каталог.csv')
    csv_writer.add_data_in_catalog('каталоги/полный каталог.csv', data)


if __name__ == '__main__':
    create_full_catalog_csv()
