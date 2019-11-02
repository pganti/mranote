__version__ = '0.1'

import sys, os
from optparse import OptionParser

import WebTest

def run():
    usage = "usage: %prog [options] [url to GET]"
    parser = OptionParser(usage=usage, version="%%prog %s"%__version__)
    parser.add_option("-r", "--repeat",
        action="store", type="int", dest="repeat", default=1,
        help="number of times to repeat the get [1]")
    parser.add_option("-t", "--threads",
        action="store", type="int", dest="threads", default=4,
        help="number of threads to use in the get [4]")
    parser.add_option("-u", "--username",
        action="store", type="string", dest="username", default='',
        help="HTTP Basic authentication username")
    parser.add_option("-p", "--password",
        action="store", type="string", dest="password", default='',
        help="HTTP Basic authentication password")
    parser.add_option("-v", "--verbose",
        action="store_true", dest="verbose",
        help="output progress (noisy)")
    parser.add_option("-q", "--quiet",
        action="store_false", dest="verbose", default=0,
        help="be quiet [default]")

    (options, args) = parser.parse_args()
    test = WebTest.WebTest(options)
    if len(args) < 1:
        parser.error('need a url')

    url = args[0]

    if options.verbose:
        test.GET(url, disiplay_running_result)
    else:
        test.GET(url)
    display_summary_result(test)

    if options.verbose:
        display_verbose_result(url, test)

def disiplay_running_result(one, test):
    print 'n=%d, min=%.2f, max=%.2f, ave=%.2f    \r'%(test.n, test.min_t,
        test.max_t, test.tot_t/test.n),

def display_summary_result(test):
    print 'n=%d min=%.2f, max=%.2f, ave=%.2f    '%(test.n, test.min_t,
        test.max_t, test.tot_t/test.n)

def display_verbose_result(url, test):
    ave_t = test.tot_t/test.n
    print "For <%s>"%url
    vres = []
    initial = 1
    for run in test.results:
        absstart = run[0][1]
        i = 0
        for url, start, first, end, status in run:
            if initial:
                this = [0, 0, 0, 0, url]
                vres.append(this)
            else:
                this = vres[i]
            if end is not None and first is not None:
                this[1] += start-absstart
                this[2] += first-start
                this[3] += end-start
            else:
                this[0] += 1
            i += 1
        initial = 0
    rlen = len(test.results)
    for res in vres:
        ok = rlen-res[0]
        if ok:
            res[1] /= ok
            res[2] /= ok
            res[3] /= ok

    print "status start first   end url"
    print '-'*79
    for ok, start, first, end, url in vres:
        if len(url) > 55:
            url = url[:10] + ' ... ' + url[-40:]
        print '%3d %5.2f %5.2f %5.2f %-55s'%(ok, start, first, end, url)

if __name__ == '__main__':
	run();
#	import cProfile
#	cProfile.run('run()', 'runprof')

