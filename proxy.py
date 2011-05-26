# $Id: proxy.py,v 1.20 2011/05/26 20:19:17 edwlan Exp $

#  
#  Copyright (c) 2011 Edward Langley
#  All rights reserved.
#  
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions
#  are met:
#  
#  Redistributions of source code must retain the above copyright notice,
#  this list of conditions and the following disclaimer.
#  
#  Redistributions in binary form must reproduce the above copyright
#  notice, this list of conditions and the following disclaimer in the
#  documentation and/or other materials provided with the distribution.
#  
#  Neither the name of the project's author nor the names of its
#  contributors may be used to endorse or promote products derived from
#  this software without specific prior written permission.
#  
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
#  FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
#  TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
#  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#  
#
import copy
import urllib
import urlparse
import itertools
import traceback
import random
import time
import UserDict, collections
collections.Mapping.register(UserDict.DictMixin)

from hashlib import sha1
import jsonrpc.jsonutil

__all__ = ['JSONRPCProxy', 'ProxyEvents']

class NewStyleBaseException(Exception):
    def _get_message(self):
        return self._message
    def _set_message(self, message):
        self._message = message

    message = property(_get_message, _set_message)


class JSONRPCException(NewStyleBaseException):
	def __init__(self, rpcError):
		Exception.__init__(self, rpcError.get('message'))
		self.data = rpcError.get('data')
		self.message = rpcError.get('message')
		self.code = rpcError.get('code')

class IDGen(object):
	def __init__(self):
		self._hasher = sha1()
		self._id = 0
	def __get__(self, *_, **__):
		self._id += 1
		self._hasher.update(str(self._id))
		self._hasher.update(time.ctime())
		self._hasher.update(str(random.random))
		return self._hasher.hexdigest()



class ProxyEvents(object):
	'''An event handler for JSONRPCProxy'''

	#: an instance of a class which defines a __get__ method, used to generate a request id
	IDGen = IDGen()


	def __init__(self, proxy):
		'''Allow a subclass to do its own initialization, gets any arguments leftover from __init__'''
		self.proxy = proxy

	def get_postdata(self, args, kwargs):
		'''allow a subclass to modify the method's arguments

		e.g. if an authentication token is necessary, the subclass can automatically insert it into every call'''
		return args, kwargs

	def proc_response(self, data):
		'''allow a subclass to access the response data before it is returned to the user'''
		return data




inst = lambda x:x()
class JSONRPCProxy(object):
	'''A class implementing a JSON-RPC Proxy.

	:param str host: The HTTP server hosting the JSON-RPC server
	:param str path: The path where the JSON-RPC server can be found

	There are two ways of instantiating this class:
	- JSONRPCProxy.from_url(url) -- give the absolute url to the JSON-RPC server
	- JSONRPC(host, path) -- break up the url into smaller parts

	'''

	#: Override this attribute to customize proxy behavior
	_eventhandler = ProxyEvents
	def customize(self, eventhandler):
		self._eventhandler = eventhandler(self)

	def _transformURL(self, serviceURL, path):
		if serviceURL[-1] == '/':
			serviceURL = serviceURL[:-1]
		if path[0] != '/':
			path = '/%s'%path
		if path[-1] != '/' and '?' not in path:
			path = '%s/'%path
		return serviceURL, path


	def _get_postdata(self, args, kwargs):
		args,kwargs = self._eventhandler.get_postdata(args, kwargs)

		if kwargs.has_key('__args'):
			raise ValueError, 'invalid argument name: __args'
		kwargs['__args'] = args or ()
		postdata = jsonrpc.jsonutil.encode({
			"method": self._serviceName,
			'params': kwargs,
			'id': self._eventhandler.IDGen,
			'jsonrpc': '2.0'
		})
		return postdata

	## Public interface
	@classmethod
	def from_url(cls, url, ctxid=None, serviceName=None):
		'''Create a JSONRPCProxy from a URL'''
		urlsp = urlparse.urlsplit(url)
		url = '%s://%s' % (urlsp.scheme, urlsp.netloc)
		path = urlsp.path
		if urlsp.query: path = '%s?%s' % (path, urlsp.query)
		if urlsp.fragment: path = '%s#%s' % (path, urlsp.fragment)
		return cls(url, path, serviceName, ctxid)


	def __init__(self, host, path='/jsonrpc', serviceName=None, *args, **kwargs):
		self.serviceURL = host
		self._serviceName = serviceName
		self._path = path
		self.serviceURL, self._path = self._transformURL(host, path)
		self.customize(self._eventhandler)



	def __getattr__(self, name):
		if self._serviceName != None:
			name = "%s.%s" % (self._serviceName, name)
		return self.__class__(self.serviceURL, path=self._path, serviceName=name)




	def __call__(self, *args, **kwargs):

		url = '%(host)s%(path)s' % dict(host = self.serviceURL, path = self._path)
		postdata = self._get_postdata(args, kwargs)
		respdata = urllib.urlopen(url, postdata).read()
		resp = jsonrpc.jsonutil.decode(respdata)

		if resp.get('error') != None:
			raise JSONRPCException(resp['error'])
		else:
			resp = self._eventhandler.proc_response(resp)
			result = resp['result']
			return result


	def call(self, method, *args, **kwargs):
		'''call a JSON-RPC method

		It's better to use instance.<methodname>(\\*args, \\*\\*kwargs),
		but this version might be useful occasionally
		'''
		p = self.__class__(self.serviceURL, path=self._path, serviceName=method)
		return p(*args, **kwargs)


	def batch_call(self, names, *params):
		'''call several methods at once, return a list of (result, error) pairs

		:param names: a list of method names
		:param \\*params: a list of (arg,kwarg) pairs corresponding to each method name
		'''
		methods = ( (getattr(self, name),param) for name,param in itertools.izip(names, params) )
		data = (method._get_postdata(*params) for method, params in methods)
		postdata = '[%s]' % ','.join(data)
		respdata = urllib.urlopen(self.serviceURL, postdata).read()
		resp = jsonrpc.jsonutil.decode(respdata)
		return [(res.get('result'), res.get('error')) for res in resp]