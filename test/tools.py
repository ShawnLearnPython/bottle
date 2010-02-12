# -*- coding: utf-8 -*-
import bottle
import threading
import urllib
import urllib2
import sys
import time
import unittest
import wsgiref
import wsgiref.simple_server
import wsgiref.util
from StringIO import StringIO
try:
    from io import BytesIO
except:
    pass
import mimetypes
import uuid

def tob(data):
    return data.encode('utf8') if isinstance(data, unicode) else data

class MethodRequest(urllib2.Request):
    ''' Used to create HEAD/PUT/DELETE/... requests with urllib2 '''
    def set_method(self, method):
        self.method = method.upper()
    def get_method(self):
        return getattr(self, 'method', urllib2.Request.get_method(self))

class NonLoggingRequestHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *args):
        pass
    def get_stderr(self):
        return StringIO()

class TestServer(bottle.ServerAdapter):
    ''' Bottle compatible testing ServerAdapter '''
    def __init__(self, *a, **k):
        bottle.ServerAdapter.__init__(self, *a, **k)
        self.event_running = threading.Event()

    def run(self, handler):
        from wsgiref.simple_server import make_server
        try:
            srv = make_server(self.host, self.port, handler,
                              handler_class=NonLoggingRequestHandler)
            self.alive = True
        except:
            pass
        self.event_running.set()
        while self.alive:
            srv.handle_request()

    def urlopen(self, path, post=None, method=None):
        ''' Open a path using urllip2.urlopen and the test domain and port '''
        url = 'http://%s:%d/%s' % (self.host, self.port, path.lstrip('/'))
        r = MethodRequest(url, post)
        if method:
            r.set_method(method)
        try:
            return urllib2.urlopen(r)
        except urllib2.HTTPError, e:
            return e

    def shutdown(self):
      self.alive = False
      self.urlopen('/shutdown/now', method='SHUTDOWN')



class ServerTestBase(unittest.TestCase):
    def setUp(self):
        ''' Create a new Bottle app set it as default_app and register it to urllib2 '''
        self.port = 61382
        self.host = 'localhost'
        self.app = bottle.app.push()
        self.server = TestServer(host=self.host, port=self.port)
        self.urlopen = self.server.urlopen
        self.thread = threading.Thread(target=bottle.run, args=(),
                      kwargs=dict(app=self.app, server=self.server, quiet=True))
        self.thread.start()
        self.server.event_running.wait()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        bottle.app.pop()

    def assertStatus(self, code, route, **kargs):
        self.assertEqual(code, self.urlopen(route, **kargs).code)

    def assertBody(self, body, route, **kargs):
        self.assertEqual(tob(body), self.urlopen(route, **kargs).read())

    def assertInBody(self, body, route, **kargs):
        self.assertTrue(tob(body) in self.urlopen(route, **kargs).read())

    def assertHeader(self, name, value, route, **kargs):
        self.assertEqual(value, self.urlopen(route, **kargs).info().get(name))

    def assertHeaderAny(self, name, route, **kargs):
        self.assertTrue(self.urlopen(route, **kargs).info().get(name, None))



def multipart_environ(fields, files):
    boundary = str(uuid.uuid1())
    parts = []
    e = dict()
    wsgiref.util.setup_testing_defaults(e)
    e['CONTENT_TYPE'] = 'multipart/form-data; boundary='+boundary
    e['REQUEST_METHOD'] = 'POST'
    boundary = '--' + boundary
    for name, value in fields:
        parts.append(boundary)
        parts.append('Content-Disposition: form-data; name="%s"' % name)
        parts.append('')
        parts.append(value)
    for name, filename, body in files:
        mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        parts.append(boundary)
        parts.append('Content-Disposition: file; name="%s"; filename="%s"' % \
             (name, filename))
        parts.append('Content-Type: %s' % mimetype)
        parts.append('')
        parts.append(body)
    parts.append(boundary + '--')
    parts.append('')
    body = '\n'.join(parts)
    e['CONTENT_LENGTH'] = str(len(body))
    if hasattr(body, 'encode'):
        body = body.encode('utf8')
    e['wsgi.input'].write(body)
    e['wsgi.input'].seek(0)
    return e


