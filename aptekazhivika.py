from parsing_base import Parser
import json
from json.decoder import JSONDecodeError
import apteka
import db


class ZhivikaParser(Parser):
    QUERY = "query categoryProducts($pageSize: Int!, $currentPage: Int!) {\n  products: productsElastic(pageSize: $pageSize, sort: {is_in_stock:DESC,search_weight:ASC,product_qty:DESC}, currentPage: $currentPage, filter: {category_id: {eq: \"%s\"}}, applyFilter: {}) {\n    total_count\n    page_info {\n      page_size\n      current_page\n    }\n    filters {\n      request_var\n      additional_data\n      name\n      filter_items_count\n      filter_items {\n        items_count\n        value_string\n        label\n      }\n    }\n    apply_filters {\n      attribute_label\n      request_var\n      value_label\n      value_string\n    }\n    items {\n      id\n      sku\n      name\n      rec_need\n      delivery\n      delivery_status\n      thermolabile\n      termolabil_preparat\n      url_key\n      promo_label\n      orig_preparat {\n        label\n      }\n      thumbnail {\n        url\n        label\n      }\n      price {\n        oldPrice {\n            amount {\n              value\n            }\n          }\n        regularPrice {\n          amount {\n            value\n          }\n        }\n      }\n      manufacturer_id {\n        label\n      }\n      is_in_stock\n      is_isg\n      manufactures_url\n      brands_url\n      manufactures_url\n    }\n  }\n}"
    QUERY_APTEKS = "\n query getPvzProducts($sku: String, $day: Int){\n pvzProducts(productSku: $sku, day: $day, pageSize: 1000){\n items{\n address,\n latitude,\n longitude,\n name,\n phone,\n schedule,\n quantity,\n group_name,\n schedule_prepared,\n station,\n entity_id,\n },\n total_count\n }\n }\n "
    IDS_CATEGORY = [1755, 1756, 1020, 1027, 1033, 1617, 1035, 1036, 1780]
    PAGE_SIZE = 80

    def __init__(self):
        super().__init__()
        self.host = 'https://www.aptekazhivika.ru'
        self.name = 'aptekazhivika'

    def get_max_pages(self):
        json_post_data_all_category = []
        for id_category in self.IDS_CATEGORY:
            query = self.QUERY % id_category
            current_page = 1
            variables = {"pageSize": self.PAGE_SIZE, "currentPage": current_page}
            json_post_data = {"query": query, "variables": variables}
            json_post_data_all_category.append(json_post_data)
        urls = [self.host + '/graphql' for _ in range(len(json_post_data_all_category))]
        resps = self.requests.post(urls, json_post_data_all_category)
        max_pages = []
        for resp in resps:
            data = json.loads(resp)
            max_page = 1 + data['data']['products']['total_count'] // self.PAGE_SIZE
            max_pages.append(max_page)
        return max_pages

    def get_all_pages_data(self, id_category, max_page):
        json_post_data_all_pages = []
        for page in range(1, max_page + 1):
            query = self.QUERY % id_category
            variables = {"pageSize": self.PAGE_SIZE, "currentPage": page}
            json_post_data = {"query": query, "variables": variables}
            json_post_data_all_pages.append(json_post_data)
        urls = [self.host + '/graphql' for _ in range(len(json_post_data_all_pages))]
        resps = self.requests.post(urls, json_post_data_all_pages)
        data_all_pages = []
        for resp in resps:
            data_all_pages.append(json.loads(resp))
        return data_all_pages

    def get_meds(self, data_page):
        count_meds = len(data_page['data']['products']['items'])
        meds_json_data = data_page['data']['products']['items']
        med_ids = []
        med_names = []
        prices = []
        post_data_apteks_all_in_med = []
        for med_index in range(count_meds):
            sku = meds_json_data[med_index]['sku']
            med_id = int(meds_json_data[med_index]['id'])
            med_name = str(meds_json_data[med_index]['name'])
            price = float(meds_json_data[med_index]['price']['regularPrice']['amount']['value'])
            med_ids.append(med_id)
            prices.append(price)
            med_names.append(med_name)
            variables_apteks = {'day': 0, 'sku': sku}
            json_post_data_apteks = {"query": self.QUERY_APTEKS, "variables": variables_apteks}
            post_data_apteks_all_in_med.append(json_post_data_apteks)
        urls = [self.host + '/graphql' for _ in range(len(post_data_apteks_all_in_med))]
        resps = self.requests.post(urls, post_data_apteks_all_in_med)
        meds = []
        for med_index in range(count_meds):
            meds.append({'med_name': med_names[med_index],
                         'med_id': med_ids[med_index],
                         'price': prices[med_index],
                         'apteks': []})
            try:
                data_apteks = json.loads(resps[med_index])
            except JSONDecodeError:
                continue
            for aptek in data_apteks['data']['pvzProducts']['items']:
                aptek_id = aptek['entity_id']
                address = aptek['address']
                print(address, med_ids[med_index])
                meds[med_index]['apteks'].append(apteka.Apteka(name='Живика',
                                                               url=f"{self.host}/store/views/{aptek_id}",
                                                               address=address,
                                                               host_id=aptek_id,
                                                               host=self.host))
        return meds

    def update_prices(self):
        print('[INFO] Обновление цен...')
        max_pages = self.get_max_pages()
        count_categories = len(self.IDS_CATEGORY)
        for category_index in range(count_categories):
            all_pages_data = self.get_all_pages_data(self.IDS_CATEGORY[category_index], max_pages[category_index])
            for data_page in all_pages_data:
                meds = self.get_meds(data_page)
                for med_data in meds:
                    for aptek in med_data['apteks']:
                        med = apteka.Med(name=med_data['med_name'],
                                         url=f"{self.host}'/product/{med_data['med_id']}",
                                         host_id=med_data['med_id'])
                        price = apteka.Price(med=med, apteka=aptek, rub=med_data['price'])
                        print(price)
                        db.add_price(price)
                        db.aptek_update_updtime(aptek)
        print('[INFO] Обновление цен завершено')


if __name__ == '__main__':
    parser = ZhivikaParser()
    parser.update_prices()
