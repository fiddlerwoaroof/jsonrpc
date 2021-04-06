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
from jsonrpc.utilities import public
import jsonrpc.jsonutil
from typing import (
    Dict,
    Any,
    List,
    Type,
    TypeVar,
    TypedDict,
    Any,
    Iterable,
    Optional,
    Union,
)


class JSONError(TypedDict):
    code: int
    message: str


@public
class RPCError(Exception):
    """Base Exception for JSON-RPC Errors, if this or a subclass of this is raised by a JSON-RPC method,
    The server will convert it into an appropriate error object
    """

    #: Error code
    code: int = 0
    #: Error message
    msg: str = ""

    @classmethod
    def from_dict(cls, err: JSONError):
        self = cls()
        self.code = err["code"]
        self.msg = err["message"]
        return self

    def json_equivalent(self) -> JSONError:
        """return a dictionary which matches an JSON-RPC Response"""
        return JSONError(code=self.code, message=self.msg)

    def __str__(self):
        return jsonrpc.jsonutil.encode(self)


@public
class InvalidRequest(RPCError):
    """Raise this when the Request object does not match the schema"""

    code = -32600
    msg = "Invalid Request."


@public
class MethodNotFound(RPCError):
    """Raise this when the desired method is not found"""

    code = -32601
    msg = "Procedure not found."


@public
class ParseError(RPCError):
    """Raise this when the request contains invalid JSON"""

    code = -32700
    msg = "Parse error."


codemap = {0: RPCError}
codemap.update((e.code, e) for e in RPCError.__subclasses__())


T = TypeVar("T", bound="JsonInstantiate")


class JsonInstantiate:
    @classmethod
    def from_dict(cls, inp: Dict[Any, Any]):
        pass

    @classmethod
    def from_json(cls: Type[T], json) -> Union[T, List[T]]:
        data = json
        if hasattr(json, "upper"):
            data = jsonrpc.jsonutil.decode(json)

        if isinstance(data, list):
            result = cls.from_list(data)
        else:
            result = cls.from_dict(data)
        return result

    @classmethod
    def from_list(cls, responses):
        return [cls.from_dict(r) for r in responses]


class JSONRPCRequest(TypedDict):
    jsonrpc: str
    id: str
    method: str
    params: Optional[Union[Iterable[Any], Dict[Any, Any]]]


class Request(JsonInstantiate):
    def __init__(
        self,
        id: str,
        method: str,
        args: Optional[Iterable[Any]] = None,
        kwargs: Optional[Dict[Any, Any]] = None,
        extra: Union[str, Dict, None] = None,
        version: str = "2.0",
    ):
        self.version = version
        self.id = id
        self.method = method
        self.args = args
        self.kwargs = kwargs
        self.extra = extra or {}

    @classmethod
    def from_dict(cls, content):
        version = content.pop("jsonrpc", None)
        id = content.pop("id", None)

        method = content.pop("method", None)

        kwargs = content.pop("params", {})
        args = ()
        if not isinstance(kwargs, dict):
            args = tuple(kwargs)
            kwargs = {}
        else:
            args = kwargs.pop("__args", args)

        args = args
        kwargs = dict((str(k), v) for k, v in list(kwargs.items()))
        extra = content
        return cls(id, method, args, kwargs, extra, version)

    def check(self):
        if self.version != "2.0":
            raise InvalidRequest
        if not isinstance(self.method, str):
            raise InvalidRequest
        if not isinstance(self.id, (str, int, type(None))):
            self.id = None
            raise InvalidRequest
        return self

    def json_equivalent(self) -> JSONRPCRequest:
        if self.kwargs and "__args" in self.kwargs:
            raise ValueError("invalid argument name: __args")

        params = self.args
        if self.args and self.kwargs:
            self.kwargs["__args"] = self.args
        if self.kwargs:
            params = self.kwargs

        if self.id is None:
            raise InvalidRequest("invalid id: %s" % self.id)

        return JSONRPCRequest(
            jsonrpc=self.version, id=self.id, method=self.method, params=params
        )


class Response(JsonInstantiate):
    def __init__(
        self,
        id: Optional[str] = None,
        result: Optional[Any] = None,
        error: Optional[Any] = None,
        version: str = "2.0",
    ):
        self.version = version
        self.id = id
        self.result = result
        self.error = error

    @classmethod
    def from_dict(cls, response):
        version = response.get("jsonrpc", None)
        id = response["id"]
        result = response.get("result", None)
        error = response.get("error", None)

        return cls(id, result, error, version)

    def json_equivalent(self):
        res = dict(jsonrpc=self.version, id=self.id)
        if self.error is None:
            res["result"] = self.result
        else:
            res["error"] = self.error
        return res

    def get_result(self):
        """get result and raise any errors"""
        if self.error:
            code = self.error["code"]
            raise codemap.get(code, RPCError).from_dict(self.error)
        return self.result

    def get_output(self):
        """get tuple (result, error)"""
        return self.result, self.error
