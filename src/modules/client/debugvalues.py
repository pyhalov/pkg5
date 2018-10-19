#!/usr/bin/python2.7
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

import six

class Singleton(type):
        """Set __metaclass__ to Singleton to create a singleton.
        See http://en.wikipedia.org/wiki/Singleton_pattern """

        def __init__(self, name, bases, dictionary):
                super(Singleton, self).__init__(name, bases, dictionary)
                self.instance = None

        def __call__(self, *args, **kw):
                if self.instance is None:
                        self.instance = super(Singleton, self).__call__(*args,
                            **kw)

                return self.instance


class DebugValues(six.with_metaclass(Singleton, dict)):
        """Singleton dict that returns None if unknown value
        is referenced"""

        def __getitem__(self, item):
                """ returns None if not set """
                return self.get(item, None)

        def get_value(self, key):
                return self[key]

        def set_value(self, key, value):
                self[key] = value


DebugValues=DebugValues()
