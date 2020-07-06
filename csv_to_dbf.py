#!/usr/bin/python2
from dbfpy import dbf
import csv
import io
import os


def add_data_in_dbf(file_name, data):
    SCHEMA = (
        ("DRUG_ID", "N", 25, 0),
        ("DRUG_NAME", "C", 120),
    )
    db = dbf.Dbf(file_name, new=True)
    db.addField(*SCHEMA)
    for drug in data:
        rec = db.newRecord()
        rec["DRUG_ID"] = int(drug[0])
        rec["DRUG_NAME"] = drug[1].encode("cp1251")
        rec.store()
    db.close()


def csv_to_dbf(csv_file, dbf_file):
    with io.open(csv_file, "r", encoding='utf8') as file:
        txt = file.read()
    rows = txt.split('\n')
    data = []
    for row in rows:
        cols = row.split(';')
        if cols[0] and cols[1]:
            data.append(cols)
    add_data_in_dbf(dbf_file, data)


def main():
    for file in os.listdir('catalogs'):
        name = file.split('.')[0]
        if file.split('.')[1] == 'csv':
            csv_to_dbf("catalogs/{}".format(file), "catalogs/{}.dbf".format(name))


if __name__ == '__main__':
    main()