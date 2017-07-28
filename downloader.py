import os
import argparse
import shutil
import threading

from urllib import request
from queue import Queue


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
    def __init__(self, url, filename, output_dir, url_tries=1):
        self.url = url
        self.filename = filename
        self.output_dir = output_dir
        self.url_tries = url_tries
        self.url_tried = 0
        self.isSuccess = False
        self.error = None

    def download(self):
        self.url_tried += 1
        output_file_path = os.path.join(self.output_dir, self.filename)

        if os.path.exists(output_file_path):
            self.isSuccess = True
        else:
            with open(output_file_path, 'wb') as output_file:
                try:
                    response = request.urlopen(self.url)
                except request.URLError as e:
                    self.error = e
                else:
                    if response is not None:
                        shutil.copyfileobj(response, output_file)
                        self.isSuccess = True

        return self.isSuccess

    def __str__(self):
        return 'DownloadableEntry ({url}, {success}, {error})'.format(
            url=self.url, success=self.isSuccess, error=self.error
        )


class DownloaderThread(threading.Thread):
    def __init__(self, queue, report):
        super().__init__(self)
        self.queue = queue
        self.report = report

    def run(self):
        while not self.queue.empty():
            entry = self.queue.get()
            response = entry.download()

            if not response:
                if entry.url_tried < entry.url_tries:
                    self.queue.put(entry)
                else:
                    self.report['failure'].append(entry)
            else:
                self.report['success'].append(entry)

            self.queue.task_done()


class Downloader:
    def __init__(self, urls_and_filenames, output, number, limit=None):
        self.thread_number = number
        self.queue = Queue(0)
        self.report = {'success': [], 'failure': []}
        self.threads = []
        self.output = output
        self.url_tries = 3
        self.limit = limit

        for url, filename in urls_and_filenames:
            self.queue.put(DownloadableEntry(url, filename, self.url_tries))

    def run(self):
        for i in range(self.thread_number):
            thread = DownloaderThread(self.queue, self.report)
            thread.start()
            self.threads.append(thread)
        if self.queue.qsize() > 0:
            self.queue.join()


def main():
    args = parse_args()

    if args.file is None:
        raise ValueError('input file is not specified')

    if not os.path.exists(args.file):
        raise FileExistsError('input file not found')

    urls_and_filenames = [tuple(line.split(' ')) for line in args.file]

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    limit = args.limit
    if limit:
        suffix = limit[-1]
        if suffix.isalpha():
            if suffix == 'k':
                limit *= 1024
            elif suffix == 'm':
                limit *= 1048576
            else:
                raise ValueError('wrong speed limit value')

    downloader = Downloader(urls_and_filenames, args.output, args.number, limit)

    print('Downloading {} files'.format(len(urls_and_filenames)))
    downloader.run()
    print('Downloaded {} of {}'.format(len(downloader.report['success']), len(urls_and_filenames)))

    if len(downloader.report['failure']) > 0:
        print('\nFailed urls:')
        for url in downloader.report['failure']:
            print(url)


if __name__ == '__main__':
    main()
