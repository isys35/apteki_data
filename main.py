#!/usr/bin/python3
from aptekazhivika import ZhivikaParser
from stolichniki import StolichnikiParser
from aptekamos import AptekamosParser3
from gorzdraf import GorZdrafParser
import db
import csv_writer
import xml_writer
import time
import os
import sys

# [ZhivikaParser(),
# StolichnikiParser(),
# AptekamosParser3(),
# GorZdrafParser()]


def main():
    parsers = [AptekamosParser3(),
               GorZdrafParser()]
    for parser in parsers:
        try:
            parser.update_prices()
        except Exception as ex:
            print(ex.__class__)
            sys.exit()
        create_catalog_csv(parser)
        create_prices_xls(parser)
    create_full_catalog_csv()


def create_full_catalog_csv():
    data = db.get_data_meds()
    csv_writer.create_csv_file('catalogs/full_catalog.csv')
    csv_writer.add_data_in_catalog('catalogs/full_catalog.csv', data)


def create_catalog_csv(parser):
    data = db.get_data_meds(parser.host)
    csv_writer.create_csv_file(f'catalogs/{parser.name}.csv')
    csv_writer.add_data_in_catalog(f'catalogs/{parser.name}.csv', data)


def create_prices_xls(parser):
    print(f'[INFO] Создание xml для {parser.name}')
    try:
        os.mkdir(f"prices/{parser.name}")
    except FileExistsError:
        pass
    data = db.get_prices_meds(parser.host)
    for aptek in data:
        file_name = f"prices/{parser.name}/{parser.name}_{aptek['host_id']}.xml"
        id = str(aptek['host_id'])
        name = f"{aptek['name']} {aptek['address']}"
        date = time.localtime(aptek['upd_time'])
        date = time.strftime("%Y-%m-%d %H:%M:%S", date)
        xml_writer.createXML(file_name, id, name, date)
        for price in aptek['prices']:
            rub = str(price[1]).replace('.', ',')
            print(file_name, str(price[0]), rub)
            xml_writer.add_price(file_name, str(price[0]), rub)


if __name__ == '__main__':
    main()
