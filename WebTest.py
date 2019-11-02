import sys, time, socket
from WebGetter import WebGetter

class WebTest:
    def __init__(self, options):
        self.options = options
        self.results = []

    def GET(self, url, progress_callback=None):
        self.results = []
        self.min_t, self.max_t, self.tot_t = 99, 0, 0
        for i in range(self.options.repeat):
            one = self.runOneTest(url)
            # url, start, first, end, status
            total = one[-1][3] - one[0][1]
            self.tot_t += total
            self.min_t = min(total, self.min_t)
            self.max_t = max(total, self.max_t)
            self.results.append(one)
            self.n = i + 1
            if progress_callback is not None:
                progress_callback(one, self)

    def runOneTest(self, url):
        t = time.time()
        fetcher = WebGetter(self.options,url)
        try:
            fetcher.GET(url)
        except socket.error, message:
            print 'Problem loading page: %s'%message
            sys.exit(0)
        l = {}
        for url, timing, event in fetcher.timing:
            if not l.has_key(url):
                evt = l.setdefault(url, [url, timing, None, None, None])
            elif event == 'first byte':
                l[url][2] = timing
            else:
                l[url][3] = timing
                l[url][4] = event[6:]
        l = l.values()
        l.sort(lambda x, y: cmp(x[1], y[1]))
        return l

