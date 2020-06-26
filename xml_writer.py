import os
from lxml import etree


def createXML(filename, id, name, date):
    root = etree.Element("BODY")
    root.set('KONKID', id)
    root.set('KONKNAME', name)
    root.set('FILEDATE', date)
    root.set('DCID', '1')
    tree = etree.ElementTree(root)
    handle = etree.tostring(tree, pretty_print=True, encoding='utf-8', xml_declaration=False)
    with open(filename, "wb") as fh:
        fh.write(handle)


def remove_xml(path):
    for el in os.listdir(path):
        if '.xml' == el[-4:]:
            os.remove(f'{path}/{el}')


def add_price(filename, id, price):
    ids = get_meds_id(filename)
    if id in ids:
        return
    tree = etree.ElementTree(file=filename)
    root = tree.getroot()
    item = etree.Element("ITEM")
    item.set('medid', id)
    item.set('medprice', str(price).replace('.',','))
    root.append(item)
    etree.indent(root, space="\t")
    handle = etree.tostring(root, encoding='utf-8')
    with open(filename, "wb") as fh:
        fh.write(handle)


def get_meds_id(filename):
    tree = etree.ElementTree(file=filename)
    root = tree.getroot()
    ids = []
    for item in root.getchildren():
        ids.append(item.values()[0])
    return ids


if __name__ == '__main__':
    createXML('assa.xml', '1', 'вфывфывыф', '3213-32')
    for i in range(10):
        add_price('assa.xml', '123123','321313')
    get_meds_id('assa.xml')

