import os
import argparse
from urllib import request

class MyAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs is not None:
            raise ValueError('nargs not allowed')
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        print('{} {} {}'.format(namespace, values, option_string))
        setattr(namespace, self.dest, values)


parser = argparse.ArgumentParser(
    prog='downloader',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    description='Command-line HTTP download utility'
)

parser.add_argument(
    '-n',
    '--number',
    action=MyAction,
    nargs='?',
    type=int,
    default=1,
    help='number of %(prog)s program threads'
)

parser.add_argument(
    '-l',
    '--limit',
    action=MyAction,
    nargs='?',
    help='download speed limit'
)

parser.add_argument(
    '-f',
    '--file',
    action=MyAction,
    nargs='?',
    type=argparse.FileType(mode='r', encoding='UTF-8'),
    required=True,
    help='a path to file with URLs'
)

parser.add_argument(
    '-o',
    '--output',
    action=MyAction,
    nargs='?',
    default=os.path.dirname(os.path.abspath(__file__)),
    help='output directory'
)

args = parser.parse_args()

if args.file is None:
    raise ValueError('input file is not specified')

for line in args.file:
    url, filename = line.split(' ')
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    with open(os.path.join(args.output, filename), 'wb') as output_file:
        try:
            response = request.urlopen(url)
            if response is not None:
                html = response.read()
        except request.URLError as e:
            pass
        else:
            output_file.write(html)
