# -*- coding: utf-8 -*-
import urlparse
from restkit import ConnectionPool
from restkit import request
from restkit import ResourceNotFound
from restkit.sock import CHUNK_SIZE

ALLOWED_METHODS = ['GET', 'HEAD']

class Proxy(object):
    """A proxy wich redirect the request to SERVER_NAME:SERVER_PORT and send HTTP_HOST header"""

    def __init__(self, pool=None, allowed_methods=ALLOWED_METHODS, strip_script_name=True, **kwargs):
        self.pool = pool or ConnectionPool(**kwargs)
        self.allowed_methods = allowed_methods
        self.strip_script_name = strip_script_name

    def extract_uri(self, environ):
        port = None
        scheme = environ['wsgi.url_scheme']
        if 'SERVER_NAME' in environ:
            host = environ['SERVER_NAME']
        else:
            host = environ['HTTP_HOST']
        if ':' in host:
            host, port = host.split(':')

        if not port:
            if 'SERVER_PORT' in environ:
                port = environ['SERVER_PORT']
            else:
                port = scheme == 'https' and '443' or '80'

        uri = '%s://%s:%s' % (scheme, host, port)
        return uri

    def __call__(self, environ, start_response):
        method = environ['REQUEST_METHOD']
        if method not in self.allowed_methods:
            start_response('403 Forbidden', ())
            return ['']

        if method in ('POST', 'PUT'):
            if 'CONTENT_LENGTH' in environ:
                content_length = int(environ['CONTENT_LENGTH'])
                body = environ['wsgi.input'].read(content_length)
            else:
                body = environ['wsgi.input'].read()
        else:
            body=None

        if self.strip_script_name:
            path_info = ''
        else:
            path_info = environ['SCRIPT_NAME']
        path_info += environ['PATH_INFO']

        query_string = environ['QUERY_STRING']
        if query_string:
            path_info += '?' + query_string

        uri = self.extract_uri(environ)+path_info

        new_headers = {}
        for k, v in environ.items():
            if k.startswith('HTTP_'):
                k = k[5:].replace('_', '-').title()
                new_headers[k] = v

        for k, v in (('CONTENT_TYPE', None), ('CONTENT_LENGTH', '0')):
            v = environ.get(k, None)
            if v is not None:
                new_headers[k.replace('_', '-').title()] = v

        response = request(uri, method,
                           body=body, headers=new_headers,
                           pool_instance=self.pool)

        start_response(response.status, response.http_client.parser.headers)

        if 'content-length' in response:
            return response.body_file
        else:
            return [response.body]

class TransparentProxy(Proxy):
    """A proxy based on HTTP_HOST environ variable"""

    def extract_uri(self, environ):
        port = None
        scheme = environ['wsgi.url_scheme']
        host = environ['HTTP_HOST']
        if ':' in host:
            host, port = host.split(':')

        if not port:
            port = scheme == 'https' and '443' or '80'

        uri = '%s://%s:%s' % (scheme, host, port)
        return uri


class HostProxy(Proxy):
    """A proxy to redirect all request to a specific uri"""

    def __init__(self, uri, **kwargs):
        super(HostProxy, self).__init__(**kwargs)
        self.uri = uri.rstrip('/')
        self.scheme, self.net_loc = urlparse.urlparse(self.uri)[0:2]

    def extract_uri(self, environ):
        environ['HTTP_HOST'] = self.net_loc
        return self.uri


class CouchdbProxy(HostProxy):
    """A proxy to redirect all request to CouchDB database"""
    def __init__(self, db_name='', uri='http://127.0.0.1:5984', allowed_methods=['GET'], **kwargs):
        uri = uri.rstrip('/')
        if db_name:
            uri += '/' + db_name.strip('/')
        super(CouchdbProxy, self).__init__(uri, allowed_methods=allowed_methods, **kwargs)

def get_config(local_config):
    """parse paste config"""
    config = {}
    allowed_methods = local_config.get('allowed_methods', None)
    if allowed_methods:
        config['allowed_methods'] = [m.upper() for m in allowed_methods.split()]
    strip_script_name = local_config.get('strip_script_name', 'true')
    if strip_script_name.lower() in ('false', '0'):
        config['strip_script_name'] = False
    config['max_connections'] = int(local_config.get('max_connections', '5'))
    return config

def make_proxy(global_config, **local_config):
    """TransparentProxy entry_point"""
    config = get_config(local_config)
    print 'Running TransparentProxy with %s' % config
    return TransparentProxy(**config)

def make_host_proxy(global_config, uri=None, **local_config):
    """HostProxy entry_point"""
    uri = uri.rstrip('/')
    config = get_config(local_config)
    print 'Running HostProxy on %s with %s' % (uri, config)
    return HostProxy(uri, **config)

def make_couchdb_proxy(global_config, db_name='', uri='http://127.0.0.1:5984', **local_config):
    """CouchdbProxy entry_point"""
    uri = uri.rstrip('/')
    config = get_config(local_config)
    print 'Running CouchdbProxy on %s/%s with %s' % (uri, db_name, config)
    return CouchdbProxy(db_name=db_name, uri=uri, **config)

