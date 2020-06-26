import sqlite3
import time

DB_NAME = 'apteki.db'


def create_db():
    file = open(DB_NAME, 'wb')
    file.close()




# noinspection SqlNoDataSourceInspection
def create_tables():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE apteka 
        (url TEXT PRIMARY KEY, 
        name TEXT,
        address TEXT,
        host TEXT,
        upd_data INTEGER,
        host_id INTEGER)""")
    cursor.execute("""CREATE TABLE med 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT UNIQUE)""")
    cursor.execute("""CREATE TABLE price 
            ('id' INTEGER PRIMARY KEY AUTOINCREMENT, 
            'rub' REAL,
            'upd_time' INTEGER,
            'med_id' INTEGER NOT NULL,
            'aptek_url' TEXT NOT NULL,
            FOREIGN KEY ('med_id') REFERENCES 'med'('id'),
            FOREIGN KEY ('aptek_url') REFERENCES 'apteka'('url'))""")


def get_aptek_url(price):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    apteka_url = price.apteka.url
    query = f"""SELECT url FROM apteka WHERE url='{apteka_url}'"""
    cursor.execute(query)
    data_aptek = cursor.fetchone()
    if not data_aptek:
        add_apteka(price.apteka)
    cursor.close()
    conn.close()
    return apteka_url


def aptek_update_updtime(apteka):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data = [int(time.time()), apteka.url]
    query = f"""UPDATE apteka
                SET upd_time=?
                WHERE aptek_url=?"""
    cursor.execute(query, data)
    conn.commit()
    cursor.close()
    conn.close()


def get_med_id(price):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    med_name = price.med.name
    query = f"""SELECT id FROM med WHERE name='{med_name}'"""
    cursor.execute(query)
    data_meds = cursor.fetchone()
    if not data_meds:
        med_id = add_med(price.med)
    else:
        med_id = data_meds[0]
    cursor.close()
    conn.close()
    return med_id


def add_price(price):
    aptek_url = get_aptek_url(price)
    med_id = get_med_id(price)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    query = f"""SELECT id from price WHERE aptek_url='{aptek_url}' AND med_id={med_id}"""
    cursor.execute(query)
    data_price = cursor.fetchone()
    if not data_price:
        upd_data = [price.rub, aptek_url, med_id, int(time.time())]
        cursor.execute(f"""INSERT INTO price (rub, aptek_url, med_id, upd_time)
                            VALUES (?, ?, ?, ?)""", upd_data)
    else:
        upd_data = [price.rub, int(time.time()), aptek_url, med_id]
        query = f"""UPDATE price
                    SET rub=?, upd_time=?
                    WHERE aptek_url=? AND med_id=?"""
        cursor.execute(query, upd_data)
    conn.commit()
    cursor.close()
    conn.close()


def add_apteka(apteka):
    """Добавляем аптеку в базу"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data = [apteka.url, apteka.name, apteka.address, apteka.host, int(apteka.host_id)]
    query = f"""INSERT INTO apteka (url, name, address, host, host_id) 
                VALUES (?,?,?,?,?)"""
    cursor.execute(query, data)
    conn.commit()
    cursor.close()
    conn.close()


def add_med(med):
    """Добавляем лекарство в базу и возращаем её id """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    query = f"""INSERT INTO med (name) 
                VALUES ('{med.name}')"""
    cursor.execute(query)
    conn.commit()
    query = f"""SELECT id FROM med WHERE name='{med.name}'"""
    cursor.execute(query)
    id = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return id


def get_data_meds(host=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if not host:
        query = "SELECT * FROM med"
        cursor.execute(query)
    else:
        query = """SELECT m.id, m.name
                   FROM 'price' p
                   JOIN 'med' m ON m.id = p.med_id
                   JOIN 'apteka' a ON a.url = p.aptek_url
                   WHERE a.host = ?"""
        cursor.execute(query, [host])
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return data


def get_prices_meds(host):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    query = """SELECT url, name, address, upd_data, host_id 
                FROM 'apteka' WHERE host = ?"""
    cursor.execute(query, [host])
    apteks_data = [{"url": aptek[0],
                    "name": aptek[1],
                    "address": aptek[2],
                    'upd_time': aptek[3],
                    'host_id':aptek[4]} for aptek in cursor.fetchall()]
    for aptek in apteks_data:
        query = """SELECT med_id, rub
                   FROM 'price' WHERE aptek_url = ?"""
        cursor.execute(query, [aptek['url']])
        aptek['prices'] = (cursor.fetchall())
    return apteks_data

if __name__ == '__main__':
    print(get_prices_meds('https://gorzdrav.org'))