import os
import re
import argparse
import time
import threading

from functools import reduce

from downloader import Downloader


def parse_args(args: tuple):
    """
    Собирает аргументы программы, контролируя необязательные значения и значения
    по умолчанию. Предоставляет справочную информацию о программе.
    :param args: Аргументы программы, переданные из тестов.
    :return: Объект argparse.Namespace, содержащий разобранные аргументы программы.
    """
    parser = argparse.ArgumentParser(
        prog='downloader',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Command-line HTTP download utility'
    )

    parser.add_argument(
        '-n',
        '--number',
        nargs='?',
        type=int,
        default=1,
        help='number of %(prog)s program threads'
    )

    parser.add_argument(
        '-l',
        '--limit',
        nargs='?',
        default='0',  # limit=0 эквивалентен отсутствию ограничения скорости загрузки
        help='download speed limit ' +
             '(\'<LIMIT>\' for number of bit/s, \'<LIMIT>k\' for number of kbit/s, ' +
             '\'<LIMIT>m\' for number of Mbit/s)'
    )

    parser.add_argument(
        '-f',
        '--file',
        nargs='?',
        type=argparse.FileType(mode='r', encoding='UTF-8'),  # открыть исходный файл сразу
        required=True,
        help='a path to file with URLs'
    )

    parser.add_argument(
        '-o',
        '--output',
        nargs='?',
        default=os.path.dirname(os.path.abspath(__file__)),
        help='output directory'
    )

    return parser.parse_args(list(args)) if args else parser.parse_args()


def main(*predefined_args):
    args = parse_args(predefined_args)

    if args.file is None:  # был передан аргумент -f/--file без значения
        raise ValueError('input file is not specified')

    urls_and_filenames = [
        tuple(line.split('\n')[0].split(' '))  # исходный файл есть набор строк; необходимо
        # вначале отделить строки от символов "\n", а затем разбить их на URL и имена файлов
        for line in args.file
    ]

    number_of_threads = args.number if args.number else 1  # при передаче -n/--number без значения
    # считаем, что передано "1"

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    if args.limit:
        if args.limit.isdigit():  # limit = 4321
            limit = float(args.limit) * 0.125
        elif re.match(r'^\d+\w$', args.limit):
            suffix = args.limit[-1]
            if suffix == 'k':  # limit = 4321k
                limit = float(args.limit[:-1]) * 125
            elif suffix == 'm':  # limit = 4321m
                limit = float(args.limit[:-1]) * 125000
            else:  # limit не является числом с суффиксом "k"/"m"
                raise ValueError('unrecognized rate limit suffix')
        else:
            raise ValueError('wrong rate limit value')
    else:
        limit = 0.0  # при передаче -l/--limit без значения считаем, что передано "0.0"

    downloader = Downloader(urls_and_filenames, args.output, number_of_threads, limit)

    print('Downloading {} files'.format(len(urls_and_filenames)))
    start_time = time.time()
    downloader.run_workers()

    while threading.active_count() > 2:  # скачивающие потоки еще не завершили работу
        time.sleep(1)

    downloader.output_queue.put(('done',))  # завершить поток отображения на консоль

    print('\nDownloaded {} files of {}'.format(
        len(downloader.report['success']), len(urls_and_filenames))
    )
    print('Time Elapsed: {:.2f} seconds'.format(time.time() - start_time))
    print('Summary amount of downloaded files: {} bytes'.format(
        reduce((lambda x, y: x + y), downloader.total_length))
    )

    if len(downloader.report['failure']) > 0:
        print('\nFailed urls:')
        for url in downloader.report['failure']:
            print(url)


if __name__ == '__main__':
    main()
