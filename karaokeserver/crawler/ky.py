# coding:utf-8
from contextlib import closing
from six.moves import urllib, queue
from lxml import html
from .types import TSong
import datetime
import threading

__all__ = 'crawl'

VENDOR_NAME = 'KY'


def crawl_new(year, month, page, crawling_pipe, parsing_pipe):
    s_date = '{0:04d}{1:02d}'.format(year, month)
    args = urllib.parse.urlencode({
        's_date': s_date,
        'page': page,
    })
    req = urllib.request.Request(
        'http://ikaraoke.kr/isong/search_newsong.asp?' + args)
    print(u'Crawling {0}, {1}'.format(s_date, page))

    try:
        with closing(urllib.request.urlopen(req)) as fp:
            tree = html.fromstring(fp.read())
            trs = tree.xpath('//*[@class="tbl_board"]//table[1]//tr')[1:]
            empty = tree.find('.//*[@class="tbl_board"]//td[@colspan="8"]')

            if trs and empty is None:
                parsing_pipe.put(trs)
                crawling_pipe.put((year, month, page+1))
    except urllib.error.HTTPError as e:
        if e.code == 500:
            crawling_pipe.put((year, month, page+1))


def parse_trs(trs):
    for tr in trs:
        if not len(tr.find('td')):
            continue
        for br in tr.xpath("*//br"):
            br.tail = '\n' + br.tail if br.tail else '\n'

        try:
            number = tr.find('td[2]').text_content().strip()
            title = tr.find('td[3]').text_content().strip()
            singer = tr.find('td[4]').text_content().strip()
        except:
            continue

        _title = list(map(lambda x: x.strip(), title.split('\n')))
        _singer = list(map(lambda x: x.strip(), singer.split('\n')))

        # If japanese song
        if len(_title) > 1:
            title = _title[0] + _singer[-1]
            singer = _singer[0] + _title[-1]
        # Or malformed Korean singer
        elif len(_singer) > 1:
            singer = _singer[0]

        yield (number, title, singer)


def parse_worker(parsing_pipe, results):
    while 1:
        trs = parsing_pipe.get()
        running = True
        while running:
            try:
                results += parse_trs(trs)
                running = False
            except Exception as e:
                print(e)
        parsing_pipe.task_done()


def crawl_worker(crawling_pipe, parsing_pipe):
    while 1:
        year, month, page = crawling_pipe.get()
        running = True
        while running:
            try:
                crawl_new(year, month, page, crawling_pipe, parsing_pipe)
                running = False
            except Exception as e:
                print(e)
        crawling_pipe.task_done()


def crawl(target_month=None, new=False):
    parsing_pipe = queue.Queue()
    crawling_pipe = queue.Queue()
    results = []

    for _ in range(10):
        crawling_thread = threading.Thread(
            target=crawl_worker, args=(crawling_pipe, parsing_pipe))
        crawling_thread.setDaemon(True)
        crawling_thread.start()

    for _ in range(2):
        parsing_thread = threading.Thread(
            target=parse_worker, args=(parsing_pipe, results))
        parsing_thread.setDaemon(True)
        parsing_thread.start()

    today = datetime.date.today()

    if target_month:
        crawling_pipe.put((target_month.year, target_month.month, 1))
    elif new:
        crawling_pipe.put((today.year, today.month, 1))
    else:
        for year in range(2004, today.year+1):
            for month in range(1, 12+1):
                crawling_pipe.put((year, month, 1))

    crawling_pipe.join()
    parsing_pipe.join()

    return (TSong(number, title, singer)
            for (number, title, singer) in results)
