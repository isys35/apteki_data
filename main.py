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
import parsers

# [ZhivikaParser(),
# StolichnikiParser(),
# AptekamosParser3(),
# GorZdrafParser()]


def main():
    parsers = [GorZdrafParser(),
               AptekamosParser3()]
    for parser in parsers:
        parsing(parser)
    create_full_catalog_csv()


def parsing(parser):
    parser.update_prices()
    create_catalog_csv(parser)
    create_prices_xls(parser)


def update_info(parser):
    meds = db.get_meds_obj()
    parser.update_info(meds)


def load_info():
    parsers = [ZhivikaParser(),
               StolichnikiParser(),
               AptekamosParser3(),
               GorZdrafParser()]
    for parser in parsers:
        create_catalog_csv(parser)
        create_prices_xls(parser)
    create_full_catalog_csv()


def create_catalogs():
    parsers = [ZhivikaParser(),
               StolichnikiParser(),
               AptekamosParser3(),
               GorZdrafParser()]
    for parser in parsers:
        create_catalog_csv(parser)
    create_full_catalog_csv()

def create_full_catalog_csv():
    data = db.get_data_meds()
    csv_writer.create_csv_file('catalogs/full_catalog.csv')
    csv_writer.add_data_in_catalog('catalogs/full_catalog.csv', data)


def create_catalog_csv(parser):
    data = set(db.get_data_meds(parser.host))
    csv_writer.create_csv_file(f'catalogs/{parser.name}.csv')
    csv_writer.add_data_in_catalog(f'catalogs/{parser.name}.csv', data)


def create_apteks_xml():
    data = db.get_apteks()
    xml_writer.createXMLaptek('apteki.xml')
    xml_writer.add_apteks('apteki.xml', data)


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
        xml_writer.add_prices(file_name, aptek['prices'])


if __name__ == '__main__':
    # main()
    parsers = [AptekamosParser3(), StolichnikiParser(), GorZdrafParser()]
    for parser in parsers:
        update_info(parser)
