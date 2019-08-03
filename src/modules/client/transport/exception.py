#!/usr/bin/python3.5
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

#
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.
#

import errno
import pycurl

from functools import total_ordering
from six.moves import http_client

retryable_http_errors = set((http_client.REQUEST_TIMEOUT, http_client.BAD_GATEWAY,
        http_client.GATEWAY_TIMEOUT, http_client.NOT_FOUND))
retryable_file_errors = set((pycurl.E_FILE_COULDNT_READ_FILE, errno.EAGAIN,
    errno.ENOENT))

import pkg.client.api_errors as api_errors

# Errors that stats.py may include in a decay-able error rate
decayable_http_errors = set((http_client.NOT_FOUND,))
decayable_file_errors = set((pycurl.E_FILE_COULDNT_READ_FILE, errno.EAGAIN,
    errno.ENOENT))
decayable_pycurl_errors = set((pycurl.E_OPERATION_TIMEOUTED,
        pycurl.E_COULDNT_CONNECT))

# Different protocols may have different retryable errors.  Map proto
# to set of retryable errors.

retryable_proto_errors = {
    "file": retryable_file_errors,
    "http": retryable_http_errors,
    "https": retryable_http_errors,
}

decayable_proto_errors = {
    "file": decayable_file_errors,
    "http": decayable_http_errors,
    "https": decayable_http_errors,
}

proto_code_map = {
    "http": http_client.responses,
    "https": http_client.responses
}

retryable_pycurl_errors = set((pycurl.E_COULDNT_CONNECT, pycurl.E_PARTIAL_FILE,
    pycurl.E_OPERATION_TIMEOUTED, pycurl.E_GOT_NOTHING, pycurl.E_SEND_ERROR,
    pycurl.E_RECV_ERROR, pycurl.E_COULDNT_RESOLVE_HOST,
    pycurl.E_TOO_MANY_REDIRECTS, pycurl.E_BAD_CONTENT_ENCODING))

class TransportException(api_errors.TransportError):
        """Base class for various exceptions thrown by code in transport
        package."""

        def __init__(self):
                self.count = 1
                self.decayable = False
                self.retryable = False


class TransportOperationError(TransportException):
        """Used when transport operations fail for miscellaneous reasons."""

        def __init__(self, data):
                TransportException.__init__(self)
                self.data = data

        def __str__(self):
                return str(self.data)


class TransportFailures(TransportException):
        """This exception encapsulates multiple transport exceptions."""

        #
        # This class is a subclass of TransportException so that calling
        # code can reasonably 'except TransportException' and get either
        # a single-valued or in this case a multi-valued instance.
        #
        def __init__(self, pfmri=None):
                TransportException.__init__(self)
                self.exceptions = []
                self.pfmri = pfmri

        def append(self, exc):
                found = False

                assert isinstance(exc, TransportException)
                for x in self.exceptions:
                        if x == exc:
                                x.count += 1
                                found = True
                                break

                if not found:
                        self.exceptions.append(exc)

        def extend(self, exc_list):
                for exc in exc_list:
                        self.append(exc)

        def __str__(self):
                if len(self.exceptions) == 0:
                        return "[no errors accumulated]"

                s = ""
                if self.pfmri:
                        s += "{0}\n".format(self.pfmri)

                for i, x in enumerate(self.exceptions):
                        s += "  "
                        if len(self.exceptions) > 1:
                                s += "{0:d}: ".format(i + 1)
                        s += str(x)
                        if x.count > 1:
                                s += _(" (happened {0:d} times)").format(
                                    x.count)
                        s += "\n"
                s += self._str_autofix()
                return s

        def __len__(self):
                return len(self.exceptions)


@total_ordering
class TransportProtoError(TransportException):
        """Raised when errors occur in the transport protocol."""

        def __init__(self, proto, code=None, url=None, reason=None,
            repourl=None, request=None, uuid=None, details=None, proxy=None):
                TransportException.__init__(self)
                self.proto = proto
                self.code = code
                self.url = url
                self.urlstem = repourl
                self.reason = reason
                self.request = request
                self.decayable = self.code in decayable_proto_errors[self.proto]
                self.retryable = self.code in retryable_proto_errors[self.proto]
                self.uuid = uuid
                self.details = details
                self.proxy = proxy
                self.codename = ""
                codenames = [
                        name
                        for name in vars(pycurl)
                        if len(name) > 1 and name[:2] == "E_" and \
                            getattr(pycurl, name) == code
                ]
                if len(codenames) >= 1:
                        self.codename = codenames[0]

        def __str__(self):
                s = "{0} protocol error".format(self.proto)
                if self.code and self.codename:
                        s += ": code: {0} ({1:d})".format(
                            self.codename, self.code)
                elif self.code:
                        s += ": Unknown error code: {0:d}".format(self.code)
                if self.reason:
                        s += " reason: {0}".format(self.reason)
                if self.url:
                        s += "\nURL: '{0}'".format(self.url)
                elif self.urlstem:
                        # If the location of the resource isn't known because
                        # the error was encountered while attempting to find
                        # the location, then at least knowing where it was
                        # looking will be helpful.
                        s += "\nRepository URL: '{0}'.".format(self.urlstem)
                if self.proxy:
                        s += "\nProxy: '{0}'".format(self.proxy)
                if self.details:
                        s +="\nAdditional Details:\n{0}".format(self.details)
                return s

        def key(self):
                return (self.proto, self.code, self.url, self.details,
                    self.reason)

        def __eq__(self, other):
                if not isinstance(other, TransportProtoError):
                        return False
                return self.key() == other.key()

        def __lt__(self, other):
                if not isinstance(other, TransportProtoError):
                        return True
                return self.key() < other.key()

        def __hash__(self):
                return hash(self.key())


@total_ordering
class TransportFrameworkError(TransportException):
        """Raised when errors occur in the transport framework."""

        def __init__(self, code, url=None, reason=None, repourl=None,
            uuid=None, proxy=None):
                TransportException.__init__(self)
                self.code = code
                self.url = url
                self.urlstem = repourl
                self.reason = reason
                self.decayable = self.code in decayable_pycurl_errors
                self.retryable = self.code in retryable_pycurl_errors
                self.uuid = uuid
                self.proxy = proxy
                self.codename = ""
                codenames = [
                        name
                        for name in vars(pycurl)
                        if len(name) > 1 and name[:2] == "E_" and \
                            getattr(pycurl, name) == code
                ]
                if len(codenames) >= 1:
                        self.codename = codenames[0]

        def __str__(self):
                if self.codename:
                        s = "Framework error: code: {0} ({1:d})".format(
                            self.codename, self.code)
                else:
                        s = "Unkown Framework error code: {0:d}".format(
                            self.code)
                if self.reason:
                        s += " reason: {0}".format(self.reason)
                if self.url:
                        s += "\nURL: '{0}'".format(self.url)
                if self.proxy:
                        s += "\nProxy: '{0}'".format(self.proxy)
                s += self._str_autofix()
                return s

        def key(self):
                return (self.code, self.url, self.proxy, self.reason)

        def __eq__(self, other):
                if not isinstance(other, TransportFrameworkError):
                        return False
                return self.key() == other.key()

        def __lt__(self, other):
                if not isinstance(other, TransportFrameworkError):
                        return True
                return self.key() < other.key()

        def __hash__(self):
                return hash(self.key())


@total_ordering
class TransportStallError(TransportException):
        """Raised when stalls occur in the transport framework."""

        def __init__(self, url=None, repourl=None, uuid=None, proxy=None):
                TransportException.__init__(self)
                self.url = url
                self.urlstem = repourl
                self.retryable = True
                self.uuid = uuid
                self.proxy = proxy

        def __str__(self):
                s = "Framework stall"
                if self.url or self.proxy:
                        s += ":"
                if self.url:
                        s += "\nURL: '{0}'".format(self.url)
                if self.proxy:
                        s += "\nProxy: '{0}'".format(self.proxy)
                return s

        def key(self):
                return (self.url, self.proxy)

        def __eq__(self, other):
                if not isinstance(other, TransportStallError):
                        return False
                return self.key() == other.key()

        def __lt__(self, other):
                if not isinstance(other, TransportStallError):
                        return True
                return self.key() < other.key()

        def __hash__(self):
                return hash(self.key())


@total_ordering
class TransferContentException(TransportException):
        """Raised when there are problems downloading the requested content."""

        def __init__(self, url, reason=None, proxy=None):
                TransportException.__init__(self)
                self.url = url
                self.reason = reason
                self.retryable = True
                self.proxy = proxy

        def __str__(self):
                if self.proxy:
                        s = "Transfer from '{0}' via proxy '{1}' failed".format(
                            self.url, self.proxy)
                else:
                        s = "Transfer from '{0}' failed".format(self.url)
                if self.reason:
                        s += ": {0}".format(self.reason)
                s += "."
                return s

        def key(self):
                return (self.url, self.proxy, self.reason)

        def __eq__(self, other):
                if not isinstance(other, TransferContentException):
                        return False
                return self.key() == other.key()

        def __lt__(self, other):
                if not isinstance(other, TransferContentException):
                        return True
                return self.key() < other.key()

        def __hash__(self):
                return hash(self.key())


@total_ordering
class InvalidContentException(TransportException):
        """Raised when the content's hash/chash doesn't verify, or the
        content is received in an unreadable format."""

        def __init__(self, path=None, reason=None, size=0, url=None, proxy=None):
                TransportException.__init__(self)
                self.path = path
                self.reason = reason
                self.size = size
                self.retryable = True
                self.url = url
                self.proxy = proxy

        def __str__(self):
                s = "Invalid content"
                if self.path:
                        s += "path {0}".format(self.path)
                if self.reason:
                        s += ": {0}.".format(self.reason)
                if self.url:
                        s += "\nURL: {0}".format(self.url)
                if self.proxy:
                        s += "\nProxy: {0}".format(self.proxy)
                return s

        def key(self):
                return (self.path, self.reason, self.proxy, self.url)

        def __eq__(self, other):
                if not isinstance(other, InvalidContentException):
                        return False
                return self.key() == other.key()

        def __lt__(self, other):
                if not isinstance(other, InvalidContentException):
                        return True
                return self.key() < other.key()

        def __hash__(self):
                return hash(self.key())


@total_ordering
class PkgProtoError(TransportException):
        """Raised when the pkg protocol doesn't behave according to
        specification.  This is different than TransportProtoError, which
        deals with the L7 protocols that we can use to perform a pkg(5)
        transport operation.  Although it doesn't exist, this is essentially
        a L8 error, since our pkg protocol is built on top of application
        level protocols.  The Framework errors deal with L3-6 errors."""

        def __init__(self, url, operation=None, version=None, reason=None,
            proxy=None):
                TransportException.__init__(self)
                self.url = url
                self.reason = reason
                self.operation = operation
                self.version = version
                self.proxy = proxy

        def __str__(self):
                if self.proxy:
                        s = "Invalid pkg(5) response from {0} (proxy {1})".format(
                            self.url, self.proxy)
                else:
                        s = "Invalid pkg(5) response from {0}".format(self.url)
                if self.operation:
                        s += ": Attempting operation '{0}'".format(self.operation)
                if self.version is not None:
                        s += " version {0}".format(self.version)
                if self.reason:
                        s += ":\n{0}".format(self.reason)
                return s

        def key(self):
                return (self.url, self.operation, self.version,
                    self.proxy, self.reason)

        def __eq__(self, other):
                if not isinstance(other, PkgProtoError):
                        return False
                return self.key() == other.key()

        def __lt__(self, other):
                if not isinstance(other, PkgProtoError):
                        return True
                return self.key() < other.key()

        def __hash__(self):
                return hash(self.key())


@total_ordering
class ExcessiveTransientFailure(TransportException):
        """Raised when the transport encounters too many retryable errors
        at a single endpoint."""

        def __init__(self, url, count, proxy=None):
                TransportException.__init__(self)
                self.url = url
                self.count = count
                self.retryable = True
                self.failures = None
                self.success = None
                self.proxy = proxy

        def __str__(self):
                s = "Too many retryable errors encountered during transfer.\n"
                if self.url:
                        s += "URL: {0} ".format(self.url)
                if self.proxy:
                        s += "Proxy: {0}".format(self.proxy)
                if self.count:
                        s += "Count: {0} ".format(self.count)
                return s

        def key(self):
                return (self.url, self.proxy, self.count)

        def __eq__(self, other):
                if not isinstance(other, ExcessiveTransientFailure):
                        return False
                return self.key() == other.key()

        def __lt__(self, other):
                if not isinstance(other, ExcessiveTransientFailure):
                        return True
                return self.key() < other.key()

        def __hash__(self):
                return hash(self.key())


class mDNSException(TransportException):
        """Used when mDNS operations fail."""

        def __init__(self, errstr):
                TransportException.__init__(self)
                self.err = errstr

        def __str__(self):
                return self.err

# Vim hints
# vim:ts=8:sw=8:et:fdm=marker
