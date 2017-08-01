import os
import time
import threading
import requests

from queue import Queue

from .reporter import reporter


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
                        start_time = time.time()
                        data_length = 0
                        total_length = int(total_length)
                        for chunk in response.iter_content(chunk_size=4096):
                            if not chunk:
                                break
                            data_length += len(chunk)
                            output_file.write(chunk)
                            done = int(50 * data_length / total_length)
                            self.output_query.put(('update', self.filename, total_length, done))
                            if limit > 0.0:
                                elapsed_time = time.time() - start_time
                                expected_time = data_length / limit
                                sleep_time = expected_time - elapsed_time

                                if sleep_time > 0:

                                    time.sleep(sleep_time)

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
            self.task_queue.put(
                DownloadableEntry(url, filename, self.output, self.output_queue, self.url_tries)
            )

    def run_workers(self):
        if self.limit and self.limit > 0:
            thread_limit = self.limit // self.thread_number
        else:
            thread_limit = 0

        report = threading.Thread(target=reporter, args=(self.output_queue,))
        report.start()

        for i in range(self.thread_number):
            thread = DownloaderThread(
                self.task_queue, self.output_queue, self.report, thread_limit, self.total_length
            )
            thread.start()
            self.threads.append(thread)

        if self.task_queue.qsize() > 0:
            self.task_queue.join()
