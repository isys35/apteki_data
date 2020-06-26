from aptekazhivika import ZhivikaParser
from stolichniki import StolichnikiParser


def main():
    parsers = [ZhivikaParser(), StolichnikiParser()]
    for parser in parsers:
        parser.update_prices()


if __name__ == '__main__':
    main()
