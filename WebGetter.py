import os, base64, urllib, urlparse, cStringIO, time, re, sys
import httplib, thread, threading, socket

try:
    from M2Crypto import httpslib
except ImportError:
    httpslib = None

from SimpleDOM import SimpleDOMParser
from IMGHandler import IMGHandler
from utility import mimeEncode, boundary
import cookie

Firefox = 'Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.0.4) Gecko/2008111217 Fedora/3.0.4-1.fc9 Firefox/3.0.4'
Chrome = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/525.19 (KHTML, like Gecko)'

class HTTPError:
    '''Wraps a HTTP response that is not 200.

    url - the URL that generated the error
    code, message, headers - the information returned by httplib.HTTP.getreply()
    '''
    def __init__(self, response):
        self.response = response

    def __str__(self):
        return 'ERROR: %s'%str(self.response)

class WebGetter:
    '''Provide a "web client" class that handles fetching web pages.

       Handles basic authentication, HTTPS, detection of error content, ...
       Creates a HTTPResponse object on a valid response.
       Stores cookies received from the server.
    '''
    HTTPError = HTTPError
    def __init__(self, options,url):
        '''Initialise the server, port, authinfo, images and error_content
        attributes.
        '''
	self.protocol, self.server,self.baseurl, a, b, c = urlparse.urlparse(url)
	if self.protocol == 'https':
		self.port = 443
	else:
        	self.port = 80
        self.authinfo = ''

        # cookie storage and access lock
        self.accept_cookies = 1
        self.cookies = {}
        self.cookies_lock = threading.Lock()

        # stuff for recording timings
        self.timing = []
        self.timing_list_lock = threading.Lock()

        # options
        self.options = options
        if options.username:
            self.setBasicAuth(options.username, options.password)

    def setServer(self, server, port):
        '''Set the server and port number to perform the HTTP requests to.
        '''
        self.server = server
        self.port = int(port)

    #
    # Authentication
    #
    def clearBasicAuth(self):
        '''Clear the current Basic authentication information
        '''
        self.authinfo = ''

    def setBasicAuth(self, username, password):
        '''Set the Basic authentication information to the given username
        and password.
        '''
        self.authinfo = base64.encodestring('%s:%s'%(username,
            password)).strip()

    #
    # cookie handling
    #
    def clearCookies(self):
        '''Clear all currently received cookies
        '''
        self.cookies = {}

    def setAcceptCookies(self, accept=1):
        '''Indicate whether to accept cookies or not
        '''
        self.accept_cookies = accept

    #
    # POST and GET
    #
    def POST(self, url, params, **kw):
        '''Perform a HTTP POST using the specified URL and form parameters
           and then retrieve all image and linked stylesheet components for the
           resulting HTML page.
        '''
        try:
            response = self.fetch(url, params, **kw)
        except socket.error, message:
            self.appendTiming((url, time.time(), 'end - "%s"'%message))
            return None

        # Check return code for redirect
        while response.code in (301, 302):
            # Figure the location - which may be relative
            newurl = response.headers['Location']
            try:
                response = self.fetch(urlparse.urljoin(url, newurl))
            except socket.error, message:
                self.appendTiming((url, time.time(), 'end - "%s"'%message))

        return response

    def GET(self, url, **kw):
        '''Perform a HTTP GET using the specified URL and then retrieve all
           image and linked stylesheet components for the resulting HTML page.
        '''
        return self.POST(url, None, **kw)

    def appendTiming(self, timing):
        self.timing_list_lock.acquire()
        self.timing.append(timing)
        self.timing_list_lock.release()

    #
    # The function that does it all
    #
    def fetch(self, url, postdata=None, server=None, port=None, protocol=None):
        '''Run a single test request to the indicated url. Use the POST data
        if supplied.

        Raises failureException if the returned data contains any of the
        strings indicated to be Error Content.
        Returns a HTTPReponse object wrapping the response from the server.
        '''
        # see if the url is fully-qualified (not just a path)
	#print len(urlparse.urlparse(url)),urlparse.urlparse(url)
       	t_protocol, t_server, t_url, x, t_args, x = urlparse.urlparse(url)
        if t_server:
            protocol = t_protocol
            if ':' in t_server:
                server, port = t_server.split(':')
            else:
                server = t_server
                if protocol == 'https':
                    port = '443'
		else:
		    port = '80'
            url = t_url
            if t_args:
                url = url + '?' + t_args
            # ignore the machine name if the redirect is to localhost
            #if t_server == 'localhost':
            #    server = None

        # TODO: allow override of the server and port from the URL!
        if server is None: server = self.server
        if port is None: port = self.port
        if protocol is None: protocol = self.protocol

        # timing start mark
        self.appendTiming((url, time.time(), 'start'))

        # do the protocolly stuff
        if protocol == 'http':
            h = httplib.HTTP(server, int(port))
            if int(port) == 80:
               host_header = server
            else: 
               host_header = '%s:%s'%(server, port)
        elif protocol == 'https':
            if httpslib is None:
                raise ValueError, "Can't fetch HTTPS: M2Crypto not installed"
            h = httpslib.HTTPS(server, int(port))
            if int(port) == 443:
               host_header = server
            else: 
               host_header = '%s:%s'%(server, port)
        else:
	    print "\n",protocol,server,port,"\n"
            self.appendTiming((url, time.time(), 'invalid protocol'))
            raise ValueError, protocol

	h._http_vsn = 11
	h._http_vsn_str = 'HTTP/1.1'

        params = None
        if postdata:
            # Do a post with the data file
            params = mimeEncode(postdata)
            h.putrequest('POST', url)
            h.putheader('Content-type', 'multipart/form-data; boundary=%s'%
                boundary)
            h.putheader('Content-length', str(len(params)))
        else:
            # Normal GET
            h.putrequest('GET', url)

        # Other Full Request headers
        if self.authinfo:
            h.putheader('Authorization', "Basic %s"%self.authinfo)
        h.putheader('Host', host_header)
        h.putheader('User-Agent',Chrome)
        # Send cookies
        #  - check the domain, max-age (seconds), path and secure
        #    (http://www.ietf.org/rfc/rfc2109.txt)
        cookies_used = []
        for domain, cookies in self.cookies.items():
            # check cookie domain
            if not server.endswith(domain):
                continue
            for path, cookies in cookies.items():
                # check that the path matches
                urlpath = urlparse.urlparse(url)[2]
                if not urlpath.startswith(path):
                    continue
                for sendcookie in cookies.values():
                    # and that the cookie is or isn't secure
                    if sendcookie['secure'] and protocol != 'https':
                        continue
                    # TODO: check max-age
                    h.putheader('Cookie', sendcookie.OutputString())
                    cookies_used.append(sendcookie.key)

        # finish the headers
        h.endheaders()

        if params is not None:
            h.send(params)

        # handle the reply
        errcode, errmsg, headers = h.getreply()
        self.appendTiming((url, time.time(), 'first byte'))

        # if the response is HTML, parse it for images
        sucker = None
	#print errcode,headers['Content-Type'];
        if errcode == 200 and 'html' in headers['Content-Type']:
            sucker = IMGHandler(url, self, self.options.threads)
#        if errcode == 200 and 'css' in headers['Content-Type']:
#            sucker = CSSHandler(url, self, self.options.threads)

        # get the body and save it
        f = h.getfile()
        g = cStringIO.StringIO()
        data = f.read(128)
        while data:
            if sucker is not None:
                sucker.feed(data)
            g.write(data)
            data = f.read(128)
        if sucker is not None:
            sucker.close()
        response = HTTPResponse(self.options, self.cookies, protocol,
            server, port, url, errcode, errmsg, headers, g.getvalue())
        f.close()
        self.appendTiming((url, time.time(), 'end - %s'%errcode))

        if errcode not in (200, 301, 302):
            raise HTTPError(response)

        # decode the cookies
        if self.accept_cookies:
            try:
                # decode the cookies and update the cookies store
                self.cookies_lock.acquire()
                cookie.decodeCookies(url, server, headers, self.cookies)
                self.cookies_lock.release()
            except:
                raise

        if sucker is not None:
            sucker.finished.wait()

        return response

class HTTPResponse(WebGetter):
    '''Wraps a HTTP response.

    protocol, server, port, url - the request server and URL
    code, message, headers - the information returned by httplib.HTTP.getreply()
    body - the response body returned by httplib.HTTP.getfile()
    '''
    def __init__(self, options, cookies, protocol, server, port, url,
            code, message, headers, body):
        WebGetter.__init__(self, options,url)
        # single cookie store per test
        self.cookies = cookies

        # this is the request that generated this response
        self.protocol = protocol
        self.server = server
        self.port = port
        self.url = url

        # info about the response
        self.code = code
        self.message = message
        self.headers = headers
        self.body = body
        self.dom = None

    def __str__(self):
        return '%s\nHTTP Response %s: %s'%(self.url, self.code, self.message)

    def getDOM(self):
        '''Get a DOM for this page
        '''
        if self.dom is None:
            parser = SimpleDOMParser()
            parser.parseString(self.body)
            self.dom = parser.getDOM()
        return self.dom

    def extractForm(self, path=[], include_submit=0, include_button=0):
        '''Extract a form (as a dictionary) from this page.

        The "path" is a list of 2-tuples ('element name', index) to follow
        to find the form. So:
         <html><head>..</head><body>
          <p><form>...</form></p>
          <p><form>...</form></p>
         </body></html>

        To extract the second form, any of these could be used:
         [('html',0), ('body',0), ('p',1), ('form',0)]
         [('form',1)]
         [('p',1)]
        '''
        return self.getDOM().extractElements(path, include_submit,
            include_button)

    def getForm(self, formnum, getmethod, postargs, *args):
        '''Given this page, extract the "formnum"th form from it, fill the
           form with the "postargs" and post back to the server using the
           "postmethod" with additional "args".

           NOTE: the form submission will include any "default" values from
           the form extracted from this page. To "remove" a value from the
           form, just pass a value None for the elementn and it will be
           removed from the form submission.

           example WebTestCase:
             page = self.get('/foo')
             page.postForm(0, self.post, {'name': 'blahblah',
                     'password': 'foo'})

           or the slightly more complex:
             page = self.get('/foo')
             page.postForm(0, self.postAssertContent, {'name': 'blahblah',
                     'password': None}, 'password incorrect')
        '''
        dom = self.getDOM()
        form = dom.getByName('form')[formnum]
        formData = form.extractElements()
        formData.update(postargs)
        for k,v in postargs.items():
            if v is None:
                del formData[k]

        # figure the server/url info
        if form.hasattr('action'): url = form.action
        else: url = self.url

        # whack on the url params
        l = []
        for k, v in formData.items():
            l.append('%s=%s'%(urllib.quote(k), urllib.quote(v)))
        if l:
            url = url + '?' + '&'.join(l)

        # make the post
        return getmethod(url, *args)

    def postForm(self, formnum, postmethod, postargs, *args):
        '''Given this page, extract the "formnum"th form from it, fill the
           form with the "postargs" and post back to the server using the
           "postmethod" with additional "args".

           NOTE: the form submission will include any "default" values from
           the form extracted from this page. To "remove" a value from the
           form, just pass a value None for the elementn and it will be
           removed from the form submission.

           example WebTestCase:
             page = self.get('/foo')
             page.postForm(0, self.post, {'name': 'blahblah',
                     'password': 'foo'})

           or the slightly more complex:
             page = self.get('/foo')
             page.postForm(0, self.postAssertContent, {'name': 'blahblah',
                     'password': None}, 'password incorrect')
        '''
        dom = self.getDOM()
        form = dom.getByName('form')[formnum]
        formData = form.extractElements()
        formData.update(postargs)
        for k,v in postargs.items():
            if v is None:
                del formData[k]

        # figure the server/url info
        if form.hasattr('action'): url = form.action
        else: url = self.url

        # make the post
        return postmethod(url, formData, *args)
