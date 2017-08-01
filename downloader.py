import os
import time
import threading
import requests

from queue import Queue

from reporter import reporter


class DownloadableEntry:
    """
    Единица "процесса" загрузки конкретного файла.
    """
    def __init__(self, url, filename, output_dir, output_query, url_tries=1):
        """
        :param url: Ссылка на загружаемый файл в виде строки.
        :param filename: Название, под которым сохраняется скачиваемый файл.
        :param output_dir: Директория для скачиваемых файлов.
        :param output_query: Очередь графического вывода
        :param url_tries: Количество попыток загрузки файла.
        """
        self.url = url
        self.filename = filename
        self.output_dir = output_dir
        self.url_tries = url_tries
        self.url_tried = 0  # количество совершенных попыток загрузки файла
        self.isSuccess = False  # флаг успешной загрузки файла
        self.error = None  # ошибка, повлекшая неудачу загрузки файла
        self.output_query = output_query

    def download(self, limit) -> tuple:
        """
        Непосредственная загрузка файла.
        :param limit: Ограничение на скорость загрузки.
        :return: Флаг успешной загрузки файла и длина файла.
        """
        self.url_tried += 1
        output_file_path = os.path.join(self.output_dir, self.filename)
        total_length = 0

        if os.path.exists(output_file_path):  # файл под таким именем уже загружен
            self.isSuccess = True
        else:
            try:
                response = requests.get(self.url, stream=True)
            except requests.RequestException as e:
                self.error = e
            else:
                with open(output_file_path, 'wb') as output_file:
                    total_length = response.headers.get('content-length')

                    if total_length is None:  # длина файла недоступна, скачивать целиком
                        output_file.write(response.content)
                    else:
                        start_time = time.time()
                        data_length = 0  # размер уже скачанных данных
                        total_length = int(total_length)

                        for chunk in response.iter_content(chunk_size=4096):  # разбить файл на блоки
                            if not chunk:
                                break

                            data_length += len(chunk)
                            output_file.write(chunk)
                            done = int(50 * data_length / total_length)  # процент загруженных данных

                            # Обновить индикатор загрузки:
                            self.output_query.put(('update', self.filename, total_length, done))

                            if limit > 0.0:  # применить ограничение скорости загрузки
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
    """
    Поток загрузки отдельного файла. Запускает на скачивание отдельную задачу -- объект
    класса DownloadableEntry, получает результат работы.
    """
    def __init__(self, task_queue, output_queue, report: dict, limit, total_length: list):
        """

        :param task_queue: Очередь объектов DownloadableEntry -- доступные ссылки на скачивание.
        :param output_queue: Очередь графического вывода.
        :param report: Словарь результатов работы. Поддерживает ключи "success" и "failure", по
        которым размещаются объекты DownloadableEntry, соответственно успешно скачавшие файл и
        завершившиеся с неудачей.
        :param limit: Ограничение скорости загрузки.
        :param total_length: Список размеров скачиваемых файлов.
        """
        super().__init__()
        self.task_queue = task_queue
        self.output_queue = output_queue
        self.report = report
        self.limit = limit
        self.total_length = total_length

    def run(self):
        while not self.task_queue.empty():
            entry = self.task_queue.get()
            response, length = entry.download(self.limit)  # скачать файл

            if not response:  # неудача загрузки
                if entry.url_tried < entry.url_tries:  # попытаться снова
                    self.task_queue.put(entry)
                else:  # превышено количество повторных загрузок
                    self.report['failure'].append(entry)
            else:
                self.total_length.append(length)
                self.report['success'].append(entry)

            self.task_queue.task_done()


class Downloader:
    """
    Координатор запуска потоков скачивания и графического вывода,
    содержит разделяемые процессами данные.
    """
    def __init__(self, urls_and_filenames, output, number, limit=None):
        """
        :param urls_and_filenames: Список пар "URL/имя файла" для скачивания.
        :param output: Директория, в которую производится скачивание.
        :param number: Количество скачивающих потоков.
        :param limit: Общее ограничение на скорость скачивания.
        """
        self.thread_number = number
        self.task_queue = Queue(0)  # очередь объектов DownloadableEntry,
        # ассоциированных с загрузками каждого файла
        self.output_queue = Queue(0)  # очередь графического вывода для потока reporter
        self.report = {
            'success': [],
            'failure': []
        }  # данные итогового отчета: успешные и неуспешные загрузки
        self.total_length = []  # список размеров скачиваемых файлов
        self.output = output
        self.url_tries = 3  # количество попыток загрузки файла
        self.limit = limit

        for url, filename in urls_and_filenames:
            self.task_queue.put(
                DownloadableEntry(url, filename, self.output, self.output_queue, self.url_tries)
            )

    def run_workers(self):
        """
        Запуск потоков загрузки и графического вывода.
        :return: None
        """
        if self.limit and self.limit > 0:  # был передан аргумент -l/--limit
            thread_limit = self.limit // self.thread_number  # распределить общее ограничение скорости
        else:
            thread_limit = 0

        report = threading.Thread(target=reporter, args=(self.output_queue,))
        report.start()

        for i in range(self.thread_number):
            thread = DownloaderThread(
                self.task_queue, self.output_queue, self.report, thread_limit, self.total_length
            )
            thread.start()

        if self.task_queue.qsize() > 0:
            self.task_queue.join()
