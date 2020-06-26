import csv
import os


def add_data_in_catalog(file_name, data):
    with open(file_name, "a", newline="") as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerows(data)


def get_meds_names(file_name):
    with open(file_name, "r", encoding='cp1251') as f_obj:
        return [row[1] for row in csv.reader(f_obj, delimiter=';')]


def get_meds_ids(file_name):
    with open(file_name, "r", encoding='cp1251') as f_obj:
        return [row[0] for row in csv.reader(f_obj, delimiter=';')]


def get_data_from_catalog(file_name):
    with open(file_name, "r", encoding='cp1251') as f_obj:
        return [{'id': row[0], 'title': row[1]} for row in csv.reader(f_obj, delimiter=';')]


def create_csv_file(file_name):
    try:
        with open(file_name, "w", newline="", encoding='cp1251') as file:
            csv.writer(file)
    except FileNotFoundError:
        os.mkdir(file_name)
        with open(file_name, "w", newline="", encoding='cp1251') as file:
            csv.writer(file)
