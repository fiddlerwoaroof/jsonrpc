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

# Beta-code to be tested, etc.
# Thanks to SunilMohanAdapa https://github.com/SunilMohanAdapa
# Re: https://github.com/NCMI/jsonrpc/issues/13
import jsonrpc.proxy
import logging
from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed
from twisted.internet.protocol import Protocol
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from zope.interface import implements


LOGGER = logging.getLogger(__name__)


class StringProducer(object):
    """Feed a consumer from a string"""

    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


class ResponseConsumer(Protocol):
    """Read the request body and return a string"""

    body = ""

    def __init__(self, deferred):
        self.deferred = deferred

    def dataReceived(self, bytes):
        self.body += bytes

    def connectionLost(self, reason):
        self.deferred.callback(self.body)


class JSONRPCProxy(jsonrpc.proxy.JSONRPCProxy):
    def __call__(self, *args, **kwargs):
        """Process the arguments and return a resonse deferred"""
        url = self._get_url()
        postdata = self._get_postdata(args, kwargs)

        LOGGER.debug("Calling - %s - %s", url, postdata)
        agent = Agent(reactor)
        d = agent.request(
            "POST",
            url,
            Headers({"Content-Type": ["application/json"]}),
            StringProducer(postdata),
        )
        d.addCallback(self._get_response)
        d.addCallback(self._process_response)
        return d

    def _get_response(self, response):
        LOGGER.debug("Got response")
        d = Deferred()
        response.deliverBody(ResponseConsumer(d))
        return d

    def _process_response(self, body):
        LOGGER.debug("Processing response - %s", body)
        resp = jsonrpc.common.Response.from_dict(jsonrpc.jsonutil.decode(body))
        resp = self._eventhandler.proc_response(resp)

        return resp.get_result()
