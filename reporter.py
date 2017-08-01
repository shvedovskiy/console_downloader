import sys


def reporter(q):
    status = {}
    while True:
        message = q.get()
        if message[0] == 'update':
            filename, total_length, done = message[1:]
            status[filename] = total_length, done
            show_progress(status)
        elif message[0] == 'done':
            break
    print('')


def show_progress(status):
    line = ''
    for filename in status:
        total_length, done = status[filename]
        line += '{}, {} bytes: [{}/100]  '.format(filename, total_length, done * 2)
    sys.stdout.write('\r' + line)
    sys.stdout.flush()
