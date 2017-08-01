import os
import sys
import re
import time
import argparse
import shutil
import threading
import requests

from queue import Queue
from functools import reduce


def parse_args():
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
        default='0',
        help='download speed limit'
    )

    parser.add_argument(
        '-f',
        '--file',
        nargs='?',
        type=argparse.FileType(mode='r', encoding='UTF-8'),
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

    return parser.parse_args()


class DownloadableEntry:
    def __init__(self, url, filename, output_dir, output_query, url_tries=1):
        self.url = url
        self.filename = filename
        self.output_dir = output_dir
        self.url_tries = url_tries
        self.url_tried = 0
        self.isSuccess = False
        self.error = None
        self.output_query = output_query

    def download(self, limit):
        self.url_tried += 1
        output_file_path = os.path.join(self.output_dir, self.filename)
        total_length = 0

        if os.path.exists(output_file_path):
            self.isSuccess = True
        else:
            try:
                response = requests.get(self.url, stream=True)
            except requests.RequestException as e:
                self.error = e
            else:
                with open(output_file_path, 'wb') as output_file:
                    total_length = response.headers.get('content-length')
                    if total_length is None:
                        output_file.write(response.content)
                    else:
                        data_length = 0
                        total_length = int(total_length)
                        # for chunk in progress.bar(response.iter_content(chunk_size=1024),
                        #                           expected_size=(total_length / 1024) + 1):
                        #     if chunk:
                        #         output_file.write(chunk)
                        for chunk in response.iter_content(chunk_size=4096):
                            if not chunk:
                                break
                            data_length += len(chunk)
                            output_file.write(chunk)
                            done = int(50 * data_length / total_length)
                            self.output_query.put(('update', self.filename, total_length, done))
                            # sys.stdout.write('\r[{}{}]'.format('=' * done, ' ' * (50 - done)))
                            # sys.stdout.flush()
                self.isSuccess = True

        return self.isSuccess, total_length

    def __str__(self):
        return 'DownloadableEntry ({url}, {isSuccess}, {error})'.format(
            url=self.url, isSuccess=self.isSuccess, error=self.error
        )


class DownloaderThread(threading.Thread):
    def __init__(self, task_queue, output_queue, report, limit, total_length):
        super().__init__()
        self.task_queue = task_queue
        self.output_queue = output_queue
        self.report = report
        self.limit = limit
        self.total_length = total_length

    def run(self):
        while not self.task_queue.empty():
            entry = self.task_queue.get()
            response, length = entry.download(self.limit)

            if not response:
                if entry.url_tried < entry.url_tries:
                    self.task_queue.put(entry)
                else:
                    self.report['failure'].append(entry)
            else:
                self.total_length.append(length)
                self.report['success'].append(entry)

            self.task_queue.task_done()


def reporter(q, number_of_threads):
    status = {}

    while number_of_threads > 0:
        message = q.get()
        if message[0] == 'update':
            filename, total_length, done = message[1:]
            status[filename] = total_length, done
            show_progress(status)
    print('')


def show_progress(status):
    line = ''
    for filename in status:
        total_length, done = status[filename]
        line += '{}, {} bytes: [{}/100]  '.format(filename, total_length, done * 2)
    sys.stdout.write('\r' + line)
    sys.stdout.flush()


class Downloader:
    def __init__(self, urls_and_filenames, output, number, limit=None):
        self.thread_number = number
        self.task_queue = Queue(0)
        self.output_queue = Queue(0)
        self.report = {'success': [], 'failure': []}
        self.threads = []
        self.total_length = []
        self.output = output
        self.url_tries = 3
        self.limit = limit

        for url, filename in urls_and_filenames:
            self.task_queue.put(DownloadableEntry(url, filename, self.output, self.output_queue, self.url_tries))

    def run(self):
        if self.limit and self.limit > 0:
            thread_limit = self.limit // self.thread_number
        else:
            thread_limit = 0

        report = threading.Thread(target=reporter, args=(self.output_queue, self.thread_number))
        for i in range(self.thread_number):
            thread = DownloaderThread(
                self.task_queue, self.output_queue, self.report, thread_limit, self.total_length
            )
            thread.start()
            self.threads.append(thread)
        report.start()
        if self.task_queue.qsize() > 0:
            self.task_queue.join()


def main():
    args = parse_args()

    if args.file is None:
        raise ValueError('input file is not specified')

    urls_and_filenames = [tuple(line.split('\n')[0].split(' ')) for line in args.file]

    number_of_threads = args.number if args.number else 1

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    if args.limit:
        if args.limit.isdigit():
            limit = int(args.limit)
        elif re.match(r'^\d+\w$', args.limit):
            suffix = args.limit[-1]
            if suffix == 'k':
                limit = int(args.limit[:-1]) * 1024
            elif suffix == 'm':
                limit = int(args.limit[:-1]) * 1048576
            else:
                raise ValueError('unrecognized speed limit suffix')
        else:
            raise ValueError('wrong speed limit value')
    else:
        limit = 0

    downloader = Downloader(urls_and_filenames, args.output, number_of_threads, limit)

    print('Downloading {} files'.format(len(urls_and_filenames)))
    start_time = time.time()
    downloader.run()

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
