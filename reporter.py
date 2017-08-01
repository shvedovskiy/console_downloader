import sys


def reporter(q):
    """
    Функция потока, получащая сообщения очереди графического вывода.
    :param q: Очередь сообщений. Поддерживаются сообщения двух типов:
    1. "update", генерируемое скачивающим потоком при загрузке очередного блока файла. В ответ на
    это событие нужно обновить консольный индикатор заргузки.
    2. "done", сигнализирующее об окончании процесса загрузки файлов: больше нет процессов, которые
    нужно выводить на консоль, данный поток может завершать свою работу.
    :return: None
    """
    status = {}  # словарь текущих загрузок, содержит обновляемую информацию о ходе скачивания
    while True:
        message = q.get()
        if message[0] == 'update':
            # Получить данные потока, который сгенерировал событие:
            filename, total_length, downloaded = message[1:]
            status[filename] = total_length, downloaded
            show_progress(status)
        elif message[0] == 'done':
            break
    print('')


def show_progress(status):
    """
    Отрисовывает на консоли группу индикаторов загрузок.
    :param status: Словарь текущих загрузок
    :return: None
    """
    line = ''
    for filename in status:
        total_length, downloaded = status[filename]
        line += '{}, {} bytes: [{}/100]  '.format(filename, total_length, downloaded * 2)

    sys.stdout.write('\r' + line)
    sys.stdout.flush()
