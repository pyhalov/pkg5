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
# Copyright (c) 2011, 2013, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import difflib
import os
import re
import shutil
import tempfile
import unittest
import sys

import pkg.actions
import pkg.client.image as image
import pkg.fmri as fmri

from pkg.client.pkgdefs import *


class TestPkgLinked(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        p_all = []
        p_sync1 = []
        p_foo1 = []
        p_vers = [
            "@1.2,5.11-145:19700101T000001Z",
            "@1.2,5.11-145:19700101T000000Z", # old time
            "@1.1,5.11-145:19700101T000000Z", # old ver
            "@1.1,5.11-144:19700101T000000Z", # old build
            "@1.0,5.11-144:19700101T000000Z", # oldest
        ]
        p_files = [
            "tmp/bar",
            "tmp/baz",
        ]

        # generate packages that don't need to be synced
        p_foo1_name_gen = "foo1"
        pkgs = [p_foo1_name_gen + ver for ver in p_vers]
        p_foo1_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_foo1_name:
                p_data = "open %s\n" % p_foo1_name[i]
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=foo_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=foo_baz variant.foo=baz
                    close\n"""
                p_foo1.append(p_data)

        p_foo2_name_gen = "foo2"
        pkgs = [p_foo2_name_gen + ver for ver in p_vers]
        p_foo2_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_foo2_name:
                p_data = "open %s\n" % p_foo2_name[i]
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=foo_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=foo_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        # generate packages that do need to be synced
        p_sync1_name_gen = "sync1"
        pkgs = [p_sync1_name_gen + ver for ver in p_vers]
        p_sync1_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_sync1_name:
                p_data = "open %s\n" % p_sync1_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync1_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync1_baz variant.foo=baz
                    close\n"""
                p_sync1.append(p_data)

        # generate packages that do need to be synced
        p_sync2_name_gen = "sync2"
        pkgs = [p_sync2_name_gen + ver for ver in p_vers]
        p_sync2_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_sync2_name:
                p_data = "open %s\n" % p_sync2_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    add set name=variant.foo value=bar value=baz
                    add file tmp/bar mode=0555 owner=root group=bin path=sync2_bar variant.foo=bar
                    add file tmp/baz mode=0555 owner=root group=bin path=sync2_baz variant.foo=baz
                    close\n"""
                p_all.append(p_data)

        def setUp(self):
                self.i_count = 5
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
                    image_count=self.i_count)

                # create files that go in packages
                self.make_misc_files(self.p_files)

                # get repo url
                self.rurl1 = self.dcs[1].get_repo_url()

                # populate repository
                self.pkgsend_bulk(self.rurl1, self.p_all)
                self.s1_list = self.pkgsend_bulk(self.rurl1, self.p_sync1)
                self.foo1_list = self.pkgsend_bulk(self.rurl1, self.p_foo1)

                # setup image names and paths
                self.i_name = []
                self.i_path = []
                self.i_api = []
                self.i_api_reset = []
                for i in range(self.i_count):
                        name = "system:img%d" % i
                        self.i_name.insert(i, name)
                        self.i_path.insert(i, self.img_path(i))

        def __img_api_reset(self, i):
                """__img_api_reset() - reset the api object associated with an
                image if that object has been updated via a pkg(1) cli
                invocation."""

                if self.i_api_reset[i]:
                        self.i_api[i].reset()
                        self.i_api_reset[i] = False

        def __img_children_names(self, i):
                """__img_children_names() - find the children of an image and
                return their names"""

                self.__img_api_reset(i)
                return set([
                        str(name)
                        for name, rel, path in self.i_api[i].list_linked()
                        if rel == "child"
                ])

        def __img_has_parent(self, i):
                """__img_has_parent() - check if an image has a parent"""

                self.__img_api_reset(i)
                return self.i_api[i].ischild()

        # public verification functions for use by test cases.
        def _v_has_children(self, i, cl):
                assert i not in cl

                cl_found = self.__img_children_names(i)
                cl_expected = set([self.i_name[j] for j in cl])
                self.assertEqual(cl_found, cl_expected,
                    "error: image has unexpected children\n"
                    "image: %d, %s, %s\n"
                    "expected children: %s\n"
                    "found children: %s\n" %
                    (i, self.i_name[i], self.i_path[i],
                    str(cl_expected),
                    str(cl_found)))

        def _v_no_children(self, il):
                for i in il:
                        # make sure the we don't have any children
                        cl_found = self.__img_children_names(i)
                        self.assertEqual(set(), cl_found,
                           "error: image has children\n"
                           "image: %d, %s, %s\n"
                           "found children: %s\n" %
                           (i, self.i_name[i], self.i_path[i],
                           str(cl_found)))

        def _v_has_parent(self, il):
                # make sure a child has a parent
                for i in il:
                        self.assertEqual(True, self.__img_has_parent(i),
                           "error: image has no parent\n"
                           "image: %d, %s, %s\n" %
                           (i, self.i_name[i], self.i_path[i]))

        def _v_no_parent(self, il):
                for i in il:
                        self.assertEqual(False, self.__img_has_parent(i),
                           "error: image has a parent\n"
                           "image: %d, %s, %s\n" %
                           (i, self.i_name[i], self.i_path[i]))

        def _v_not_linked(self, il):
                self._v_no_parent(il)
                self._v_no_children(il)

        # utility functions for use by test cases
        def _imgs_create(self, limit):
                variants = {
                    "variant.foo": "bar",
                    "variant.opensolaris.zone": "nonglobal",
                }

                for i in range(0, limit):
                        self.set_image(i)
                        self.i_api.insert(i, self.image_create(self.rurl1,
                            variants=variants, destroy=True))
                        self.i_api_reset.insert(i, False)

                del self.i_api[limit:]
                del self.i_api_reset[limit:]
                for i in range(limit, self.i_count):
                        self.set_image(i)
                        self.image_destroy()

                self.set_image(0)

        def _ccmd(self, args, rv=0):
                """Run a 'C' (or other non-python) command."""
                assert type(args) == str
                # Ensure 'coverage' is turned off-- it won't work.
                self.cmdline_run("%s" % args, exit=rv, coverage=False)

        def _pkg(self, il, cmd, args=None, rv=None, rvdict=None,
            output_cb=None, env_arg=None):
                assert type(il) == list
                assert type(cmd) == str
                assert args == None or type(args) == str
                assert rv == None or type(rv) == int
                assert rvdict == None or type(rvdict) == dict
                assert rv == None or rvdict == None

                if rv == None:
                        rv = EXIT_OK
                if rvdict == None:
                        rvdict = {}
                        for i in il:
                                rvdict[i] = rv
                assert (set(rvdict) | set(il)) == set(il)

                if args == None:
                        args = ""

                # we're updating one or more images, so make sure to reset all
                # our api instances before using them.
                self.i_api_reset[:] = [True] * len(self.i_api_reset)

                for i in il:
                        rv = rvdict.get(i, EXIT_OK)
                        self.pkg("-R %s %s %s" % (self.i_path[i], cmd, args),
                            exit=rv, env_arg=env_arg)
                        if output_cb:
                                output_cb(self.output)

        def _pkg_child(self, i, cl, cmd, args=None, rv=None, rvdict=None):
                assert type(i) == int
                assert type(cl) == list
                assert i not in cl
                assert type(cmd) == str
                assert args == None or type(args) == str
                assert rv == None or type(rv) == int
                assert rvdict == None or type(rvdict) == dict
                assert rv == None or rvdict == None

                if rv == None:
                        rv = EXIT_OK
                if rvdict == None:
                        rvdict = {}
                        for c in cl:
                                rvdict[c] = rv
                assert (set(rvdict) | set(cl)) == set(cl)

                if args == None:
                        args = ""

                # sync each child from parent
                for c in cl:
                        rv = rvdict.get(c, EXIT_OK)
                        self._pkg([i], "%s -l %s" % (cmd, self.i_name[c]),
                            args=args, rv=rv)

        def _pkg_child_all(self, i, cmd, args=None, rv=EXIT_OK):
                assert type(i) == int
                assert type(cmd) == str
                assert args == None or type(args) == str
                assert type(rv) == int

                if args == None:
                        args = ""
                self._pkg([i], "%s -a %s" % (cmd, args), rv=rv)

        def _attach_parent(self, il, p, args=None, rv=EXIT_OK):
                assert type(il) == list
                assert type(p) == int
                assert p not in il
                assert args == None or type(args) == str
                assert type(rv) == int

                if args == None:
                        args = ""

                for i in il:
                        self._pkg([i], "attach-linked -p %s %s %s" %
                            (args, self.i_name[i], self.i_path[p]), rv=rv)

        def _attach_child(self, i, cl, args=None, rv=None, rvdict=None):
                assert type(i) == int
                assert type(cl) == list
                assert i not in cl
                assert args == None or type(args) == str
                assert rvdict == None or type(rvdict) == dict
                assert rv == None or rvdict == None

                if rv == None:
                        rv = EXIT_OK
                if rvdict == None:
                        rvdict = {}
                        for c in cl:
                                rvdict[c] = rv
                assert (set(rvdict) | set(cl)) == set(cl)

                if args == None:
                        args = ""

                # attach each child to parent
                for c in cl:
                        rv = rvdict.get(c, EXIT_OK)
                        self._pkg([i], "attach-linked -c %s %s %s" %
                            (args, self.i_name[c], self.i_path[c]),
                            rv=rv)

        def _assertEqual_cb(self, output):
                return lambda x: self.assertEqual(output, x)


class TestPkgLinked1(TestPkgLinked):
        def test_not_linked(self):
                self._imgs_create(1)

                self._pkg([0], "list-linked")

                # operations that require a parent
                rv = EXIT_NOPARENT
                self._pkg([0], "detach-linked", rv=rv)
                self._pkg([0], "sync-linked", rv=rv)
                self._pkg([0], "audit-linked", rv=rv)

        def test_opts_1_invalid(self):
                self._imgs_create(3)

                # parent has one child
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # invalid options
                rv = EXIT_BADOPT

                args = "--foobar"
                self._pkg([0], "attach-linked", args=args, rv=rv)
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)
                self._pkg([0], "list-linked", args=args, rv=rv)
                self._pkg([0], "property-linked", args=args, rv=rv)
                self._pkg([0], "set-property-linked", args=args, rv=rv)

                # can't combine -a and -l
                args = "-a -l %s" % self.i_name[1]
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # can't combine -I and -i
                args = "-I -i %s" % self.i_name[1]
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)
                self._pkg([0], "list-linked", args=args, rv=rv)

                # can't combine -i and -a
                args = "-a -i %s" % self.i_name[1]
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # can't combine -I and -a
                args = "-I -a"
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # can't combine -I and -l
                args = "-I -l %s" % self.i_name[1]
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # can't combine -i and -l with same target
                args = "-i %s -l %s" % (self.i_name[1], self.i_name[1])
                self._pkg([0], "detach-linked", args=args, rv=rv)
                self._pkg([0], "sync-linked", args=args, rv=rv)
                self._pkg([0], "audit-linked", args=args, rv=rv)

                # doesn't accept -a
                args = "-a"
                self._pkg([0], "attach-linked", args=args, rv=rv)
                self._pkg([0], "list-linked", args=args, rv=rv)
                self._pkg([0], "property-linked", args=args, rv=rv)
                self._pkg([0], "set-property-linked", args=args, rv=rv)

                # doesn't accept -l
                args = "-l %s" % self.i_name[1]
                self._pkg([0], "attach-linked", args=args, rv=rv)
                self._pkg([0], "list-linked", args=args, rv=rv)

                # can't combine --no-parent-sync and --linked-md-only
                args = "--no-parent-sync --linked-md-only"
                self._pkg([0], "sync-linked -a", args=args, rv=rv)
                self._pkg([2], "sync-linked", args=args, rv=rv)

                # can't use --no-parent-sync when invoking from parent
                args = "--no-parent-sync"
                self._pkg([0], "sync-linked -a", args=args, rv=rv)
                self._pkg_child(0, [1], "sync-linked", args=args, rv=rv)

                # can't use be options when managing children
                for arg in ["--deny-new-be", "--require-new-be",
                    "--be-name=foo"]:
                        args = "-a %s" % arg
                        self._pkg([0], "sync-linked", args=args, rv=rv)

                        args = "-l %s %s" % (self.i_name[1], arg)
                        self._pkg([0], "sync-linked", args=args, rv=rv)
                        self._pkg([0], "set-property-linked", args=args, rv=rv)

        def test_opts_2_invalid_bad_child(self):
                self._imgs_create(2)

                rv = EXIT_OOPS

                # try using an invalid child name
                self._pkg([0], "attach-linked -c foobar %s" % \
                    self.i_path[1], rv=rv)

                for lin in ["foobar", self.i_name[1]]:
                        # try using an invalid and unknown child name
                        args = "-l %s" % lin

                        self._pkg([0], "sync-linked", args=args, rv=rv)
                        self._pkg([0], "audit-linked", args=args, rv=rv)
                        self._pkg([0], "property-linked", args=args, rv=rv)
                        self._pkg([0], "set-property-linked", args=args, rv=rv)
                        self._pkg([0], "detach-linked", args=args, rv=rv)

                        # try to ignore invalid unknown children
                        args = "-i %s" % lin

                        # operations on the parent image
                        self._pkg([0], "sync-linked", args=args, rv=rv)
                        self._pkg([0], "list-linked", args=args, rv=rv)
                        self._pkg([0], "update", args=args, rv=rv)
                        self._pkg([0], "install", args= \
                            "-i %s %s" % (lin, self.p_foo1_name[1]), rv=rv)
                        self._pkg([0], "change-variant", args= \
                            "-i %s -v variant.foo=baz" % lin, rv=rv)
                        # TODO: test change-facet

        def test_opts_3_all(self):
                self._imgs_create(1)

                # the -a option is always valid
                self._pkg([0], "sync-linked -a")
                self._pkg([0], "audit-linked -a")
                self._pkg([0], "detach-linked -a")

        def test_opts_4_noop(self):
                self._imgs_create(4)

                # plan operations
                self._attach_child(0, [1, 2], args="-vn")
                self._attach_child(0, [1, 2], args="-vn")
                self._attach_parent([3], 0, args="-vn")
                self._attach_parent([3], 0, args="-vn")

                # do operations
                self._attach_child(0, [1, 2], args="-v")
                self._attach_parent([3], 0, args="-v")

                # plan operations
                self._pkg_child(0, [1, 2], "detach-linked", args="-vn")
                self._pkg_child(0, [1, 2], "detach-linked", args="-vn")
                self._pkg_child_all(0, "detach-linked", args="-vn")
                self._pkg_child_all(0, "detach-linked", args="-vn")
                self._pkg([3], "detach-linked", args="-vn")
                self._pkg([3], "detach-linked", args="-vn")

                # do operations
                self._pkg_child(0, [1], "detach-linked", args="-v")
                self._pkg_child_all(0, "detach-linked", args="-v")
                self._pkg([3], "detach-linked", args="-v")

        def test_attach_p2c_1(self):
                self._imgs_create(4)
                self._v_not_linked([0, 1, 2, 3])

                # link parents to children as follows:
                #     0 -> 1 -> 2
                #          1 -> 3

                # attach parent (0) to child (1), (0 -> 1)
                self._attach_child(0, [1], args="--parsable=0 -n")
                self.assertEqualParsable(self.output,
                    child_images=[{"image_name": "system:img1"}])
                self._attach_child(0, [1], args="--parsable=0")
                self.assertEqualParsable(self.output,
                    child_images=[{"image_name": "system:img1"}])
                self._v_has_children(0, [1])
                self._v_has_parent([1])
                self._v_not_linked([2, 3])

                # attach parent (1) to child (2), (1 -> 2)
                self._attach_child(1, [2])
                self._v_has_children(0, [1])
                self._v_has_children(1, [2])
                self._v_has_parent([1, 2])
                self._v_no_children([2])
                self._v_not_linked([3])

                # attach parent (1) to child (3), (1 -> 3)
                self._attach_child(1, [3])
                self._v_has_children(0, [1])
                self._v_has_children(1, [2, 3])
                self._v_has_parent([1, 2, 3])
                self._v_no_children([2, 3])

        def test_detach_p2c_1(self):
                self._imgs_create(4)

                # link parents to children as follows:
                #     0 -> 1 -> 2
                #          1 -> 3
                self._attach_child(0, [1])
                self._attach_child(1, [2, 3])

                # detach child (1) from parent (0)
                self._pkg_child(0, [1], "detach-linked")
                self._v_has_children(1, [2, 3])
                self._v_has_parent([2, 3])
                self._v_no_children([2, 3])
                self._v_not_linked([0])

                # detach child (3) from parent (1)
                self._pkg_child(1, [3], "detach-linked")
                self._v_has_children(1, [2])
                self._v_has_parent([2])
                self._v_no_children([2])
                self._v_not_linked([0, 3])

                # detach child (2) from parent (1)
                self._pkg_child(1, [2], "detach-linked")
                self._v_not_linked([0, 1, 2, 3])

        def test_detach_p2c_2(self):
                self._imgs_create(4)

                # link parents to children as follows:
                #     0 -> 1 -> 2
                #          1 -> 3
                self._attach_child(0, [1])
                self._attach_child(1, [2, 3])

                # detach child (1) from parent (0)
                self._pkg_child_all(0, "detach-linked", args="-n")
                self._pkg_child_all(0, "detach-linked")
                self._v_has_children(1, [2, 3])
                self._v_has_parent([2, 3])
                self._v_no_children([2, 3])
                self._v_not_linked([0])

                # detach child (3) and child (2) from parent (1)
                self._pkg_child_all(1, "detach-linked")
                self._v_not_linked([0, 1, 2, 3])

                # detach all children (there are none)
                self._pkg_child_all(0, "detach-linked")

        def test_attach_c2p_1(self):
                self._imgs_create(4)
                self._v_not_linked([0, 1, 2, 3])

                # link children to parents as follows:
                #     2 -> 1 -> 0
                #     3 -> 1

                # attach child (2) to parent (1), (2 -> 1)
                self._attach_parent([2], 1, args="--parsable=0 -n")
                self.assertEqualParsable(self.output)
                self._attach_parent([2], 1, args="--parsable=0")
                self.assertEqualParsable(self.output)
                self._v_has_parent([2])
                self._v_no_children([2])
                self._v_not_linked([0, 1, 3])

                # attach child (3) to parent (1), (3 -> 1)
                self._attach_parent([3], 1)
                self._v_has_parent([2, 3])
                self._v_no_children([2, 3])
                self._v_not_linked([0, 1])

                # attach child (1) to parent (0), (1 -> 0)
                self._attach_parent([1], 0)
                self._v_has_parent([1, 2, 3])
                self._v_no_children([1, 2, 3])
                self._v_not_linked([0])

        def test_detach_c2p_1(self):
                self._imgs_create(4)

                # link children to parents as follows:
                #     2 -> 1 -> 0
                #     3 -> 1
                self._attach_parent([2, 3], 1)
                self._attach_parent([1], 0)

                # detach parent (0) from child (1)
                self._pkg([1], "detach-linked -n")
                self._pkg([1], "detach-linked")
                self._v_has_parent([2, 3])
                self._v_no_children([2, 3])
                self._v_not_linked([0, 1])

                # detach parent (1) from child (3)
                self._pkg([3], "detach-linked")
                self._v_has_parent([2])
                self._v_no_children([2])
                self._v_not_linked([0, 1, 3])

                # detach parent (1) from child (2)
                self._pkg([2], "detach-linked")
                self._v_not_linked([0, 1, 2, 3])

        def test_attach_already_linked_1_err(self):
                self._imgs_create(4)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                rv = EXIT_OOPS

                # try to link the parent image to a new child with a dup name
                self._pkg([0], "attach-linked -c %s %s" %
                    (self.i_name[1], self.i_path[2]), rv=rv)

                # have a new parent try to link to the p2c child
                self._attach_child(3, [1], rv=rv)

                # have the p2c child try to link to a new parent
                self._attach_parent([1], 3, rv=rv)

                # have the c2p child try to link to a new parent
                self._attach_parent([2], 3, rv=rv)

        def test_attach_already_linked_2_relink(self):
                self._imgs_create(4)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # have a new parent try to link to the p2c child
                self._attach_child(3, [1], args="--allow-relink")

                # have the p2c child try to link to a new parent
                self._attach_parent([1], 3, args="--allow-relink")

                # have the c2p child try to link to a new parent
                self._attach_parent([2], 3, args="--allow-relink")

        def test_zone_attach_detach(self):
                self._imgs_create(2)

                rv = EXIT_OOPS

                # by default we can't attach (p2c) zone image
                self._pkg([0], "attach-linked -v -c zone:foo %s" %
                    self.i_path[1], rv=rv)
                self._v_not_linked([0, 1])

                # force attach (p2c) zone image
                self._pkg([0], "attach-linked -v -f -c zone:foo %s" %
                    self.i_path[1])
                self._v_not_linked([0])
                self._v_has_parent([1])

                self._imgs_create(2)

                # by default we can't attach (c2p) zone image
                self._pkg([1], "attach-linked -v -p zone:foo %s" %
                    self.i_path[0], rv=rv)
                self._v_not_linked([0, 1])

                # force attach (c2p) zone image
                self._pkg([1], "attach-linked -v -f -p zone:foo %s" %
                    self.i_path[0])
                self._v_not_linked([0])
                self._v_has_parent([1])

                # by default we can't detach (c2p) zone image
                self._pkg([1], "detach-linked -v", rv=rv)
                self._v_not_linked([0])
                self._v_has_parent([1])

                # force detach (c2p) zone image
                self._pkg([1], "detach-linked -v -f")
                self._v_not_linked([0, 1])

        def test_parent_ops_error(self):
                self._imgs_create(2)

                # attach a child
                self._attach_child(0, [1])

                rv = EXIT_PARENTOP

                # some operations can't be done from a child when linked to
                # from a parent
                self._pkg([1], "detach-linked", rv=EXIT_PARENTOP)

                # TODO: enable this once we support set-property-linked
                #self._pkg([1], "set-property-linked", rv=EXIT_PARENTOP)

        def test_eaccess_1_parent(self):
                self._imgs_create(3)
                self._attach_parent([1], 0)

                rv = EXIT_EACCESS

                for i in [0, 1]:
                        if i == 0:
                                # empty the parent image
                                self.set_image(0)
                                self.image_destroy()
                                self._ccmd("mkdir -p %s" % self.i_path[0])
                        if i == 1:
                                # delete the parent image
                                self.set_image(0)
                                self.image_destroy()

                        # operations that need to access the parent should fail
                        self._pkg([1], "sync-linked", rv=rv)
                        self._pkg([1], "audit-linked", rv=rv)
                        self._pkg([1], "install %s" % self.p_foo1_name[1], \
                            rv=rv)
                        self._pkg([1], "image-update", rv=rv)

                        # operations that need to access the parent should fail
                        self._attach_parent([2], 0, rv=rv)

                # detach should still work
                self._pkg([1], "detach-linked")

        def test_eaccess_1_child(self):
                self._imgs_create(2)
                self._attach_child(0, [1])

                outfile = os.path.join(self.test_root, "res")
                rv = EXIT_EACCESS

                for i in [0, 1, 2]:
                        if i == 0:
                                # corrupt the child image
                                self._ccmd("mkdir -p "
                                    "%s/%s" % (self.i_path[1],
                                    image.img_user_prefix))
                                self._ccmd("mkdir -p "
                                    "%s/%s" % (self.i_path[1],
                                    image.img_root_prefix))
                        if i == 1:
                                # delete the child image
                                self.set_image(1)
                                self.image_destroy()
                                self._ccmd("mkdir -p %s" % self.i_path[1])
                        if i == 2:
                                # delete the child image
                                self.set_image(1)
                                self.image_destroy()


                        # child should still be listed
                        self._pkg([0], "list-linked -H > %s" % outfile)
                        self._ccmd("cat %s" % outfile)
                        self._ccmd("egrep '^%s[ 	]' %s" %
                            (self.i_name[1], outfile))

                        # child should still be listed
                        self._pkg([0], "property-linked -H -l %s > %s" %
                            (self.i_name[1], outfile))
                        self._ccmd("cat %s" % outfile)
                        self._ccmd("egrep '^li-' %s" % outfile)

                        # operations that need to access child should fail
                        self._pkg_child(0, [1], "sync-linked", rv=rv)
                        self._pkg_child_all(0, "sync-linked", rv=rv)

                        self._pkg_child(0, [1], "audit-linked", rv=rv)
                        self._pkg_child_all(0, "audit-linked", rv=rv)

                        self._pkg_child(0, [1], "detach-linked", rv=rv)
                        self._pkg_child_all(0, "detach-linked", rv=rv)

                        # TODO: test more recursive ops here
                        # image-update, install, uninstall, etc

        def test_ignore_1_no_children(self):
                self._imgs_create(1)
                outfile = os.path.join(self.test_root, "res")

                # it's ok to use -I with no children
                self._pkg([0], "list-linked -H -I > %s" % outfile)
                self._ccmd("cat %s" % outfile)
                self._ccmd("egrep '^$|.' %s" % outfile, rv=EXIT_OOPS)

        def test_ignore_2_ok(self):
                self._imgs_create(3)
                self._attach_child(0, [1, 2])
                outfile = os.path.join(self.test_root, "res")

                # ignore one child
                self._pkg([0], "list-linked -H -i %s > %s" %
                    (self.i_name[1], outfile))
                self._ccmd("cat %s" % outfile)
                self._ccmd("egrep '^%s[ 	]' %s" %
                    (self.i_name[1], outfile), rv=EXIT_OOPS)
                self._ccmd("egrep '^%s[ 	]' %s" %
                    (self.i_name[2], outfile))

                # manually ignore all children
                self._pkg([0], "list-linked -H -i %s -i %s > %s" %
                    (self.i_name[1], self.i_name[2], outfile))
                self._ccmd("cat %s" % outfile)
                self._ccmd("egrep '^$|.' %s" % outfile, rv=EXIT_OOPS)

                # automatically ignore all children
                self._pkg([0], "list-linked -H -I > %s" % outfile)
                self._ccmd("cat %s" % outfile)
                self._ccmd("egrep '^$|.' %s" % outfile, rv=EXIT_OOPS)

        def test_no_pkg_updates_1_empty_via_attach(self):
                """test --no-pkg-updates with an empty image."""
                self._imgs_create(3)

                self._attach_child(0, [1], args="--no-pkg-updates")
                self._attach_parent([2], 0, args="--no-pkg-updates")

        def test_no_pkg_updates_1_empty_via_sync(self):
                """test --no-pkg-updates with an empty image."""
                self._imgs_create(4)

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2], args="--linked-md-only")
                self._attach_parent([3], 0, args="--linked-md-only")

                self._pkg_child(0, [1], "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)
                self._pkg_child_all(0, "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)
                self._pkg([3], "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)

        def test_no_pkg_updates_1_empty_via_set_property_linked_TODO(self):
                """test --no-pkg-updates with an empty image."""
                pass

        def test_no_pkg_updates_2_foo_via_attach(self):
                """test --no-pkg-updates with a non-empty image."""
                self._imgs_create(3)

                # install different un-synced packages into each image
                for i in [0, 1, 2]:
                        self._pkg([i], "install -v %s" % self.p_foo1_name[i])

                self._attach_child(0, [1], args="--no-pkg-updates")
                self._attach_parent([2], 0, args="--no-pkg-updates")

                # verify the un-synced packages
                for i in [0, 1, 2]:
                        self._pkg([i], "list -v %s" % self.p_foo1_name[i])

        def test_no_pkg_updates_2_foo_via_sync(self):
                """test --no-pkg-updates with a non-empty image."""
                self._imgs_create(4)

                # install different un-synced packages into each image
                for i in range(4):
                        self._pkg([i], "install -v %s" % self.p_foo1_name[i])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2], args="--linked-md-only")
                self._attach_parent([3], 0, args="--linked-md-only")

                self._pkg_child(0, [1], "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)
                self._pkg_child_all(0, "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)
                self._pkg([3], "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)

                # verify the un-synced packages
                for i in range(4):
                        self._pkg([i], "list -v %s" % self.p_foo1_name[i])

        def test_no_pkg_updates_2_foo_via_set_property_linked_TODO(self):
                """test --no-pkg-updates with a non-empty image."""
                pass

        def test_no_pkg_updates_3_sync_via_attach(self):
                """test --no-pkg-updates with an in sync package"""
                self._imgs_create(3)

                # install the same synced packages into each image
                for i in range(3):
                        self._pkg([i], "install -v %s" % self.p_sync1_name[1])

                self._attach_child(0, [1], args="--no-pkg-updates")
                self._attach_parent([2], 0, args="--no-pkg-updates")

                # verify the synced packages
                for i in range(3):
                        self._pkg([i], "list -v %s" % self.p_sync1_name[1])

        def test_no_pkg_updates_3_sync_via_sync(self):
                """test --no-pkg-updates with an in sync package"""
                self._imgs_create(4)

                # install the same synced packages into each image
                for i in range(4):
                        self._pkg([i], "install -v %s" % self.p_sync1_name[1])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2], args="--linked-md-only")
                self._attach_parent([3], 0, args="--linked-md-only")

                # verify the synced packages
                for i in range(4):
                        self._pkg([i], "list -v %s" % self.p_sync1_name[1])

                self._pkg_child(0, [1], "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)
                self._pkg_child_all(0, "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)
                self._pkg([3], "sync-linked -v --no-pkg-updates",
                    rv=EXIT_NOP)

        def test_no_pkg_updates_3_sync_via_set_property_linked_TODO(self):
                """test --no-pkg-updates with an in sync package"""
                pass

        def test_no_pkg_updates_3_fail_via_attach(self):
                """test --no-pkg-updates with an out of sync package"""
                self._imgs_create(3)

                # install different synced packages into each image
                for i in range(3):
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i+1])

                self._attach_child(0, [1], args="--no-pkg-updates",
                    rv=EXIT_OOPS)
                self._attach_parent([2], 0, args="--no-pkg-updates",
                    rv=EXIT_OOPS)

                # verify packages
                for i in range(3):
                        self._pkg([i], "list -v %s" % self.p_sync1_name[i+1])

        def test_no_pkg_updates_3_fail_via_sync(self):
                """test --no-pkg-updates with an out of sync package"""
                self._imgs_create(4)

                # install different synced packages into each image
                for i in range(4):
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i+1])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2], args="--linked-md-only")
                self._attach_parent([3], 0, args="--linked-md-only")

                self._pkg_child(0, [1], "sync-linked -v --no-pkg-updates",
                    rv=EXIT_OOPS)
                self._pkg_child_all(0, "sync-linked -v --no-pkg-updates",
                    rv=EXIT_OOPS)
                self._pkg([3], "sync-linked -v --no-pkg-updates",
                    rv=EXIT_OOPS)

                # verify packages
                for i in range(3):
                        self._pkg([i], "list -v %s" % self.p_sync1_name[i+1])

        def test_no_pkg_updates_3_fail_via_set_property_linked_TODO(self):
                pass

        def test_audit_synced_1(self):
                self._imgs_create(4)

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2], args="--linked-md-only")
                self._attach_parent([3], 0, args="--linked-md-only")

                # audit with empty parent and child
                self._pkg([1, 2, 3], "audit-linked")
                self._pkg_child(0, [1, 2], "audit-linked")
                self._pkg_child_all(0, "audit-linked")
                self._pkg_child_all(3, "audit-linked")

        def test_audit_synced_2(self):
                self._imgs_create(4)

                # install different un-synced packages into each image
                for i in [0, 1, 2, 3]:
                        self._pkg([i], "install -v %s" % self.p_foo1_name[i])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                self._pkg([1, 2, 3], "audit-linked")
                self._pkg_child(0, [1, 2, 3], "audit-linked")
                self._pkg_child_all(0, "audit-linked")

        def test_audit_synced_3(self):
                self._imgs_create(4)

                # install synced package into parent
                self._pkg([0], "install -v %s" % self.p_sync1_name[0])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                self._pkg([1, 2, 3], "audit-linked")
                self._pkg_child(0, [1, 2, 3], "audit-linked")
                self._pkg_child_all(0, "audit-linked")

        def test_audit_synced_4(self):
                self._imgs_create(4)

                # install same synced packages into parent and some children
                for i in [0, 1, 2, 3]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[0])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                self._pkg([1, 2, 3], "audit-linked")
                self._pkg_child(0, [1, 2, 3], "audit-linked")
                self._pkg_child_all(0, "audit-linked")


        def test_audit_diverged_1(self):
                self._imgs_create(4)

                # install different synced package into some child images
                for i in [1, 3]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                rvdict = {1: EXIT_DIVERGED, 3: EXIT_DIVERGED}
                self._pkg([1, 2, 3], "audit-linked", rvdict=rvdict)
                self._pkg_child(0, [1, 2, 3], "audit-linked", rvdict=rvdict)
                self._pkg_child_all(0, "audit-linked", rv=EXIT_DIVERGED)

        def test_audit_diverged_2(self):
                self._imgs_create(4)

                # install different synced package into each image
                for i in range(4):
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")

                rv = EXIT_DIVERGED
                self._pkg([1, 2, 3], "audit-linked", rv=rv)
                self._pkg_child(0, [1, 2, 3], "audit-linked", rv=rv)
                self._pkg_child_all(0, "audit-linked", rv=rv)

class TestPkgLinked2(TestPkgLinked):
        """Class used solely to split up the test suite for parallelization."""

        def test_sync_fail(self):
                self._imgs_create(3)

                # install newer sync'ed package into child
                self._pkg([0], "install -v %s" % self.p_sync1_name[2])
                self._pkg([1], "install -v %s" % self.p_sync1_name[1])
                self._pkg([2], "install -v %s" % self.p_sync1_name[1])

                # attach should fail
                self._attach_child(0, [1], args="-vn", rv=EXIT_OOPS)
                self._attach_child(0, [1], args="-v", rv=EXIT_OOPS)
                self._attach_parent([2], 0, args="-vn", rv=EXIT_OOPS)
                self._attach_parent([2], 0, args="-v", rv=EXIT_OOPS)

                # use --linked-md-only so we don't install constraints package
                # attach should succeed
                self._attach_child(0, [1], args="-vn --linked-md-only")
                self._attach_child(0, [1], args="-v --linked-md-only")
                self._attach_parent([2], 0, args="-vn --linked-md-only")
                self._attach_parent([2], 0, args="-v --linked-md-only")

                # trying to sync the child should fail
                self._pkg([1, 2], "sync-linked -vn", rv=EXIT_OOPS)
                self._pkg([1, 2], "sync-linked -v", rv=EXIT_OOPS)
                self._pkg_child(0, [1], "sync-linked -vn", rv=EXIT_OOPS)
                self._pkg_child(0, [1], "sync-linked -v", rv=EXIT_OOPS)

                # use --linked-md-only so we don't install constraints package
                # sync should succeed
                rv = EXIT_NOP
                self._pkg([1, 2], "sync-linked -vn --linked-md-only", rv=rv)
                self._pkg([1, 2], "sync-linked -v --linked-md-only", rv=rv)
                self._pkg_child(0, [1], "sync-linked -vn --linked-md-only",
                    rv=rv)
                self._pkg_child(0, [1], "sync-linked -v --linked-md-only",
                    rv=rv)

                # trying to sync via image-update should fail
                self._pkg([1, 2], "image-update -vn", rv=EXIT_OOPS)
                self._pkg([1, 2], "image-update -v", rv=EXIT_OOPS)

                # trying to sync via install should fail
                self._pkg([1, 2], "install -vn %s", self.p_sync1_name[0],
                    rv=EXIT_OOPS)
                self._pkg([1, 2], "install -v %s", self.p_sync1_name[0],
                    rv=EXIT_OOPS)

                # verify the child is still divereged
                rv = EXIT_DIVERGED
                self._pkg([1, 2], "audit-linked", rv=rv)

        def test_sync_1(self):
                self._imgs_create(5)

                # install different synced package into each image
                for i in [0, 1, 2, 3, 4]:
                        self._pkg([i], "install -v %s" % self.p_sync1_name[i])

                # install unsynced packages to make sure they aren't molested
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2, 3, 4], "install -v %s" % self.p_foo1_name[2])

                # use --linked-md-only so we don't install constraints package
                self._attach_child(0, [1, 2, 3], args="--linked-md-only")
                self._attach_parent([4], 0, args="--linked-md-only")

                # everyone should be diverged
                self._pkg([1, 2, 3, 4], "audit-linked", rv=EXIT_DIVERGED)

                # plan sync (direct)
                self._pkg([1, 4], "sync-linked -vn")
                self._pkg([1, 2, 3, 4], "audit-linked", rv=EXIT_DIVERGED)

                # sync child (direct)
                self._pkg([1, 4], "sync-linked", args="--parsable=0 -n")
                self.assertEqualParsable(self.output,
                    change_packages=[[self.s1_list[-1], self.s1_list[0]]])
                self._pkg([1, 4], "sync-linked", args="--parsable=0")
                self.assertEqualParsable(self.output,
                    change_packages=[[self.s1_list[-1], self.s1_list[0]]])
                rvdict = {2: EXIT_DIVERGED, 3: EXIT_DIVERGED}
                self._pkg([1, 2, 3, 4], "audit-linked", rvdict=rvdict)
                self._pkg([1, 4], "sync-linked -v", rv=EXIT_NOP)

                # plan sync (indirectly via -l)
                self._pkg_child(0, [2], "sync-linked -vn")
                self._pkg([1, 2, 3], "audit-linked", rvdict=rvdict)

                # sync child (indirectly via -l)
                self._pkg_child(0, [2], "sync-linked", args="--parsable=0 -n")
                self.assertEqualParsable(self.output,
                    child_images=[{
                        "image_name": "system:img2",
                        "change_packages": [[self.s1_list[2], self.s1_list[0]]]
                    }])
                self._pkg_child(0, [2], "sync-linked", args="--parsable=0")
                self.assertEqualParsable(self.output,
                    child_images=[{
                        "image_name": "system:img2",
                        "change_packages": [[self.s1_list[2], self.s1_list[0]]]
                    }])
                rvdict = {3: EXIT_DIVERGED}
                self._pkg([1, 2, 3], "audit-linked", rvdict=rvdict)
                self._pkg_child(0, [2], "sync-linked -vn", rv=EXIT_NOP)

                # plan sync (indirectly via -a)
                self._pkg_child_all(0, "sync-linked -vn")
                self._pkg([1, 2, 3], "audit-linked", rvdict=rvdict)

                # sync child (indirectly via -a)
                self._pkg_child_all(0, "sync-linked -v")
                self._pkg([1, 2, 3], "audit-linked")
                self._pkg_child_all(0, "sync-linked -v", rv=EXIT_NOP)

                # check unsynced packages
                self._pkg([1, 2, 3, 4], "list -v %s" % self.p_foo1_name[2])

        def test_sync_2_via_attach(self):
                self._imgs_create(3)

                # install different synced package into each image
                self._pkg([0], "install -v %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[2])

                # install unsynced packages to make sure they aren't molested
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_foo1_name[2])

                # attach children
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # check synced and unsynced packages
                self._pkg([1, 2], "list -v %s" % self.p_sync1_name[1])
                self._pkg([1, 2], "list -v %s" % self.p_foo1_name[2])

        def __test_linked_sync_via_child_op(self, op, op_args, **kwargs):
                """Verify that if we do a operation "op" on a child image, it
                automatically brings its packages in sync with its parent.

                We perform operation on three child images.  1 is a push
                child, 2 and 3 are pull children.  1 and 2 have their linked
                image metadata in sync with the parent.  3 has its metadata
                out of sync with the parent and is expected to sync its own
                metadata."""

                # create parent (0), push child (1), and pull child (2, 3)
                self._imgs_create(4)
                self._attach_child(0, [1])
                self._attach_parent([2, 3], 0)

                # install synced package into each image
                self._pkg([0, 1, 2, 3], "install -v %s" % self.p_sync1_name[2])

                # install unsynced packages
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2, 3], "install -v %s" % self.p_foo1_name[2])

                # update the parent image while ignoring the children (there
                # by putting them out of sync)
                self._pkg([0], "install -I -v %s" % self.p_sync1_name[1])

                # explicitly sync metadata in children 1 and 2
                self._pkg([0], "sync-linked -a --linked-md-only")
                self._pkg([2], "sync-linked --linked-md-only")

                # plan op
                self._pkg([1, 2, 3], "%s -nv %s" % (op, op_args))

                # verify child images are still diverged
                self._pkg([1, 2, 3], "audit-linked", rv=EXIT_DIVERGED)
                self._pkg([0], "audit-linked -a", rv=EXIT_DIVERGED)

                # verify child 3 hasn't updated its metadata
                # (it still thinks it's in sync)
                self._pkg([3], "audit-linked --no-parent-sync")

                # execute op
                def output_cb(output):
                        self.assertEqualParsable(output, **kwargs)
                self._pkg([1, 2, 3], "%s --parsable=0 %s" % (op, op_args),
                    output_cb=output_cb)

                # verify sync via audit and sync (which should be a noop)
                self._pkg([1, 2, 3], "audit-linked")
                self._pkg([1, 2, 3], "sync-linked -v", rv=EXIT_NOP)
                self._pkg([0], "audit-linked -a")
                self._pkg([0], "sync-linked -a", rv=EXIT_NOP)

        def __test_linked_sync_via_parent_op(self, op, op_args,
            li_md_change=True, **kwargs):
                """Verify that if we do a operation "op" on a parent image, it
                recurses into its children and brings them into sync.

                We perform operation on two child images.  both are push
                children.  1 has its linked image metadata in sync with the
                parent.  2 has its linked image metadata out of in sync with
                the parent and that metadata should get updated during the
                operation.

                Note that if the metadata in a child image is in sync with its
                parent, a recursive operation that isn't changing that
                metadata will assume that the child is already in sync and
                that we don't need to recurse into it.  This optimization
                occurs regardless of if the child image is actually in sync
                with that metadata (a child can be out of sync with its
                stored metadata if we do a metadata only update)."""

                # create parent (0), push child (1, 2)
                self._imgs_create(3)
                self._attach_child(0, [1, 2])

                # install synced package into each image
                self._pkg([0, 1, 2], "install -v %s" % self.p_sync1_name[2])

                # install unsynced packages
                self._pkg([0], "install -v %s" % self.p_foo1_name[1])
                self._pkg([1, 2], "install -v %s" % self.p_foo1_name[2])

                # update the parent image while ignoring the children (there
                # by putting them out of sync)
                self._pkg([0], "install -I -v %s" % self.p_sync1_name[1])

                # explicitly sync metadata in child 1
                self._pkg([0], "sync-linked --linked-md-only -l %s" %
                    self.i_name[1])

                # plan op
                self._pkg([0], "%s -nv %s" % (op, op_args))

                # verify child images are still diverged
                self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)
                self._pkg([0], "audit-linked -a", rv=EXIT_DIVERGED)

                # verify child 2 hasn't updated its metadata
                # (it still thinks it's in sync)
                self._pkg([2], "audit-linked")

                # execute op
                def output_cb(output):
                        self.assertEqualParsable(output, **kwargs)
                self._pkg([0], "%s --parsable=0 %s" % (op, op_args),
                    output_cb=output_cb)

                # verify sync via audit and sync (which should be a noop)
                # if the linked image metadata was changed during this
                # operation we should have updated both children.  if linked
                # image metadata was not changed, we'll only have updated one
                # child.
                if li_md_change:
                        synced_children=[1, 2]
                else:
                        synced_children=[2]
                for i in synced_children:
                        self._pkg([i], "audit-linked")
                        self._pkg([i], "sync-linked", rv=EXIT_NOP)
                        self._pkg([0], "audit-linked -l %s" % self.i_name[i])
                        self._pkg([0], "sync-linked -l %s" % self.i_name[i],
                            rv=EXIT_NOP)

        def test_linked_sync_via_update(self):
                """Verify that if we update child images to be in sync with
                their constraints when we do an update."""

                self.__test_linked_sync_via_child_op(
                    "update", "",
                    change_packages=[
                        [self.foo1_list[2], self.foo1_list[0]],
                        [self.s1_list[2], self.s1_list[1]]])

                self.__test_linked_sync_via_parent_op(
                    "update", "",
                    change_packages=[
                        [self.foo1_list[1], self.foo1_list[0]],
                        [self.s1_list[1], self.s1_list[0]]],
                    child_images=[{
                        "image_name": "system:img1",
                        "change_packages": [
                            [self.foo1_list[2], self.foo1_list[0]],
                            [self.s1_list[2], self.s1_list[0]]],
                        },{
                        "image_name": "system:img2",
                        "change_packages": [
                            [self.foo1_list[2], self.foo1_list[0]],
                            [self.s1_list[2], self.s1_list[0]]],
                    }])

        def test_linked_sync_via_update_pkg(self):
                """Verify that if we update child images to be in sync with
                their constraints when we do an update of a specific
                package."""

                self.__test_linked_sync_via_child_op(
                    "update", self.p_foo1_name[3],
                    change_packages=[
                        [self.foo1_list[2], self.foo1_list[3]],
                        [self.s1_list[2], self.s1_list[1]]])

                self.__test_linked_sync_via_parent_op(
                    "update", self.p_foo1_name[3],
                    change_packages=[
                        [self.foo1_list[1], self.foo1_list[3]]],
                    child_images=[{
                        "image_name": "system:img1",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                        },{
                        "image_name": "system:img2",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                    }])

        def test_linked_sync_via_install(self):
                """Verify that if we update child images to be in sync with
                their constraints when we do an install."""

                self.__test_linked_sync_via_child_op(
                    "install", self.p_foo1_name[1],
                    change_packages=[
                        [self.foo1_list[2], self.foo1_list[1]],
                        [self.s1_list[2], self.s1_list[1]]])

                self.__test_linked_sync_via_parent_op(
                    "install", self.p_foo1_name[0],
                    change_packages=[
                        [self.foo1_list[1], self.foo1_list[0]],
                    ],
                    child_images=[{
                        "image_name": "system:img1",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                        },{
                        "image_name": "system:img2",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                    }])

        def test_linked_sync_via_sync(self):
                """Verify that if we update child images to be in sync with
                their constraints when we do a sync-linked."""

                self.__test_linked_sync_via_child_op(
                    "sync-linked", "",
                    change_packages=[
                        [self.s1_list[2], self.s1_list[1]]])

                self.__test_linked_sync_via_parent_op(
                    "sync-linked", "-a",
                    child_images=[{
                        "image_name": "system:img1",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                        },{
                        "image_name": "system:img2",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                    }])

        def test_linked_sync_via_change_variant(self):
                """Verify that if we update child images to be in sync with
                their constraints when we do a change-variant."""

                self.__test_linked_sync_via_child_op(
                    "change-variant", "variant.foo=baz",
                    change_packages=[
                        [self.s1_list[2], self.s1_list[1]]],
                    affect_packages=[
                        self.foo1_list[2]],
                    change_variants=[
                        ['variant.foo', 'baz']])

                self.__test_linked_sync_via_parent_op(
                    "change-variant", "variant.foo=baz",
                    li_md_change=False,
                    affect_packages=[
                        self.foo1_list[1], self.s1_list[1]],
                    change_variants=[
                        ['variant.foo', 'baz']],
                    child_images=[{
                        "image_name": "system:img2",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                    }])

        def test_linked_sync_via_change_facet(self):
                """Verify that if we update child images to be in sync with
                their constraints when we do a change-facet."""

                self.__test_linked_sync_via_child_op(
                    "change-facet", "facet.foo=True",
                    change_packages=[
                        [self.s1_list[2], self.s1_list[1]]],
                    change_facets=[
                        ['facet.foo', True, None, 'local', False, False]])

                self.__test_linked_sync_via_parent_op(
                    "change-facet", "facet.foo=True",
                    li_md_change=False,
                    change_facets=[
                        ['facet.foo', True, None, 'local', False, False]],
                    child_images=[{
                        "image_name": "system:img2",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                    }])

        def test_linked_sync_via_uninstall(self):
                """Verify that if we update child images to be in sync with
                their constraints when we do an uninstall."""

                self.__test_linked_sync_via_child_op(
                    "uninstall", self.p_foo1_name[2],
                    change_packages=[
                        [self.s1_list[2], self.s1_list[1]]],
                    remove_packages=[
                        self.foo1_list[2]])

                self.__test_linked_sync_via_parent_op(
                    "uninstall", self.foo1_list[1],
                    remove_packages=[
                        self.foo1_list[1]],
                    child_images=[{
                        "image_name": "system:img1",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                        },{
                        "image_name": "system:img2",
                        "change_packages": [
                            [self.s1_list[2], self.s1_list[1]]],
                    }])


class TestPkgLinked3(TestPkgLinked):
        """Class used solely to split up the test suite for parallelization."""

        def test_parent_sync_1_nosync(self):
                self._imgs_create(2)

                # install synced package into each image
                self._pkg([0, 1], "install -v %s" % self.p_sync1_name[1])

                self._attach_parent([1], 0)

                # update parent image
                self._pkg([0], "install -v %s" % self.p_sync1_name[0])

                # there should be no updates with --no-parent-sync
                self._pkg([1], "sync-linked -v --no-parent-sync", rv=EXIT_NOP)
                self._pkg([1], "change-variant -v --no-parent-sync "
                    "variant.foo=bar", rv=EXIT_NOP)
                self._pkg([1], "change-facet -v --no-parent-sync "
                    "facet.foo=False")
                self._pkg([1], "install -v --no-parent-sync %s" % \
                    self.p_foo1_name[1])
                self._pkg([1], "update -v --no-parent-sync")
                self._pkg([1], "uninstall -v --no-parent-sync %s" % \
                    self.p_foo1_name[0])

                # an audit without a parent sync should thingk we're in sync
                self._pkg([1], "audit-linked --no-parent-sync")

                # an full audit should realize we're not in sync
                self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

                # the audit above should not have updated our image, so we
                # should still be out of sync.
                self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

        def test_install_constrainted(self):
                self._imgs_create(3)

                # install synced package into parent
                self._pkg([0], "install -v %s" % self.p_sync1_name[1])

                # attach children
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # try to install a different vers of synced package
                for i in [0, 2, 3, 4]:
                        self._pkg([1, 2], "install -v %s" % \
                            self.p_sync1_name[i], rv=EXIT_OOPS)

                # try to install a different synced package
                for i in [0, 1, 2, 3, 4]:
                        self._pkg([1, 2], "install -v %s" % \
                            self.p_sync2_name[i], rv=EXIT_OOPS)

                # install random un-synced package
                self._pkg([1, 2], "install -v %s" % self.p_foo1_name[0])

                # install the same ver of a synced package in the child
                self._pkg([1, 2], "install -v %s" % self.p_sync1_name[1])

        def test_verify(self):
                self._imgs_create(5)

                # install synced package into each image
                self._pkg([0, 1], "install -v %s" % self.p_sync1_name[1])

                # test with a newer synced package
                self._pkg([2], "install -v %s" % self.p_sync1_name[0])

                # test with an older synced package
                self._pkg([3], "install -v %s" % self.p_sync1_name[2])

                # test with a different synced package
                self._pkg([4], "install -v %s" % self.p_sync2_name[2])

                self._attach_parent([1], 0)
                self._attach_parent([2, 3, 4], 0, args="--linked-md-only")

                self._pkg([1], "verify")
                self._pkg([2, 3, 4], "verify", rv=EXIT_OOPS)

        def test_staged_noop(self):
                self._imgs_create(1)

                # test staged execution with an noop/empty plan
                self._pkg([0], "update --stage=plan", rv=EXIT_NOP)
                self._pkg([0], "update --stage=prepare")
                self._pkg([0], "update --stage=execute")

        def __test_missing_parent_pkgs_metadata(self,
            install="", audit_rv=EXIT_OK):
                """Verify that we can manipulate and update linked child
                images which are missing their parent package metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly."""

                # create parent (0), push child (1), and pull child (2)
                self._imgs_create(3)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # paths for the linked image metadata files
                md_files = [
                        "%s/var/pkg/linked/linked_ppkgs" % self.i_path[i]
                        for i in [1, 2]
                ]

                if install:
                        for i in [0, 1, 2]:
                                self._pkg([i], "install -v %s" % install)

                # delete linked image metadata files
                for f in md_files:
                        self.file_exists(f)
                        self._ccmd("rm %s" % f)

                # verify that audit-linked can handle missing metadata.
                self._pkg([0], "audit-linked -a")
                self._pkg([2], "audit-linked")
                self._pkg([1], "audit-linked", rv=audit_rv)
                self._pkg([2], "audit-linked --no-parent-sync", rv=audit_rv)

                # since we haven't modified the image, make sure the
                # facet metadata files weren't re-created.
                for f in md_files:
                        self.file_doesnt_exist(f)

                # verify that sync-linked can handle missing metadata.
                # also verify that the operation will succeed and is
                # not a noop (since it needs to update the metadata).
                self._pkg([0], "sync-linked -a -n")
                self._pkg([2], "sync-linked -n")

                # since we haven't modified the image, make sure the
                # facet metadata files weren't re-created.
                for f in md_files:
                        self.file_doesnt_exist(f)

                # do a sync and verify that the files get created
                self._pkg([0], "sync-linked -a")
                self._pkg([2], "sync-linked")
                for f in md_files:
                        self.file_exists(f)

        def test_missing_parent_pkgs_metadata_1(self):
                """Verify that we can manipulate and update linked child
                images which are missing their parent package metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly.

                Test when parent has no packages installed.  The children also
                have no packages installed so they are always in sync."""
                self.__test_missing_parent_pkgs_metadata()

        def test_missing_parent_pkgs_metadata_2(self):
                """Verify that we can manipulate and update linked child
                images which are missing their parent package metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly.

                Test when parent and children have sync packages installed.
                This means the children are diverged if their parent package
                metadata is missing."""
                self.__test_missing_parent_pkgs_metadata(
                    install=self.p_sync1_name[0], audit_rv=EXIT_DIVERGED)

        def __test_missing_parent_publisher_metadata(self,
            clear_pubs=False):
                """Verify that we can manipulate and update linked child
                images which are missing their parent publisher metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly."""

                # create parent (0), push child (1), and pull child (2)
                self._imgs_create(3)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # paths for the linked image metadata files
                md_files = [
                        "%s/var/pkg/linked/linked_ppubs" % self.i_path[i]
                        for i in [1, 2]
                ]

                if clear_pubs:
                        self._pkg([0, 1, 2], "unset-publisher test")

                # delete linked image metadata files
                for f in md_files:
                        self.file_exists(f)
                        self._ccmd("rm %s" % f)

                # verify that audit-linked can handle missing metadata.
                self._pkg([0], "audit-linked -a")
                self._pkg([1, 2], "audit-linked")
                self._pkg([2], "audit-linked --no-parent-sync")

                # since we haven't modified the image, make sure the
                # facet metadata files weren't re-created.
                for f in md_files:
                        self.file_doesnt_exist(f)

                # verify that sync-linked can handle missing metadata.
                # also verify that the operation will succeed and is
                # not a noop (since it needs to update the metadata).
                self._pkg([0], "sync-linked -a -n")
                self._pkg([2], "sync-linked -n")

                # since we haven't modified the image, make sure the
                # facet metadata files weren't re-created.
                for f in md_files:
                        self.file_doesnt_exist(f)

                # do a sync and verify that the files get created
                self._pkg([0], "sync-linked -a")
                self._pkg([2], "sync-linked")
                for f in md_files:
                        self.file_exists(f)

        def test_missing_parent_publisher_metadata_1(self):
                """Verify that we can manipulate and update linked child
                images which are missing their parent publisher metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly.

                Test when parent has no publishers configured."""
                self.__test_missing_parent_publisher_metadata(
                    clear_pubs=True)

        def test_missing_parent_publisher_metadata_2(self):
                """Verify that we can manipulate and update linked child
                images which are missing their parent publisher metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly.

                Test when parent has publishers configured."""
                self.__test_missing_parent_publisher_metadata()


class TestFacetInheritance(TestPkgLinked):
        """Class to test facet inheritance between images.

        These tests focus specifically on facet propagation from parent to
        child images, masked facet handling, and facet reporting.  These tests
        do not attempt to verify that the packaging system correctly handles
        operations when facets and packages are changing at the same time."""

        p_files = [
            "tmp/foo1",
            "tmp/foo2",
            "tmp/foo3",
            "tmp/sync1",
            "tmp/sync2",
            "tmp/sync3",
        ]
        p_foo_template = """
            open foo@%(ver)d
            add file tmp/foo1 mode=0555 owner=root group=bin path=foo1_foo1 facet.foo1=true
            add file tmp/foo2 mode=0555 owner=root group=bin path=foo1_foo2 facet.foo2=true
            add file tmp/foo3 mode=0555 owner=root group=bin path=foo1_foo3 facet.foo3=true
            close"""
        p_sync1_template = """
            open sync1@%(ver)d
            add file tmp/sync1 mode=0555 owner=root group=bin path=sync1_sync1 facet.sync1=true
            add file tmp/sync2 mode=0555 owner=root group=bin path=sync1_sync2 facet.sync2=true
            add file tmp/sync3 mode=0555 owner=root group=bin path=sync1_sync3 facet.sync3=true
            add depend type=parent fmri=feature/package/dependency/self
            close"""
        p_sync2_template = """
            open sync2@%(ver)d
            add file tmp/sync1 mode=0555 owner=root group=bin path=sync2_sync1 facet.sync1=true
            add file tmp/sync2 mode=0555 owner=root group=bin path=sync2_sync2 facet.sync2=true
            add file tmp/sync3 mode=0555 owner=root group=bin path=sync2_sync3 facet.sync3=true
            add depend type=parent fmri=feature/package/dependency/self
            close"""
        p_inc1_template = """
            open inc1@%(ver)d
            add depend type=require fmri=sync1
            add depend type=incorporate fmri=sync1@%(ver)d facet.123456=true
            add depend type=parent fmri=feature/package/dependency/self
            close"""
        p_inc2_template = """
            open inc2@%(ver)d
            add depend type=require fmri=sync2
            add depend type=incorporate fmri=sync2@%(ver)d facet.456789=true
            add depend type=parent fmri=feature/package/dependency/self
            close"""

        p_data_template = [
            p_foo_template,
            p_sync1_template,
            p_sync2_template,
            p_inc1_template,
            p_inc2_template,
        ]
        p_data = []
        for i in range(2):
                for j in p_data_template:
                        p_data.append(j % {"ver": (i + 1)})
        p_fmri = {}

        def setUp(self):
                self.i_count = 3
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
                    image_count=self.i_count)

                # create files that go in packages
                self.make_misc_files(self.p_files)

                # get repo url
                self.rurl1 = self.dcs[1].get_repo_url()

                # populate repository
                for p in self.p_data:
                        fmristr = self.pkgsend_bulk(self.rurl1, p)[0]
                        f = fmri.PkgFmri(fmristr)
                        pkgstr = "%s@%s" % (f.pkg_name, f.version.release)
                        self.p_fmri[pkgstr] = fmristr

                # setup image names and paths
                self.i_name = []
                self.i_path = []
                self.i_api = []
                self.i_api_reset = []
                for i in range(self.i_count):
                        name = "system:img%d" % i
                        self.i_name.insert(i, name)
                        self.i_path.insert(i, self.img_path(i))

        def test_facet_inheritance(self):
                """Verify basic facet inheritance functionality for both push
                and pull children."""

                # create parent (0), push child (1), and pull child (2)
                self._imgs_create(3)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # install packages with inheritable facets in all images
                self._pkg([0, 1, 2], "install -v %s" % self.p_fmri["inc1@2"])
                self._pkg([0, 1, 2], "install -v %s" % self.p_fmri["inc2@2"])

                # verify that there are no facets set in any images
                self._pkg([0, 1, 2], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(""))

                # set some random facets and make sure they aren't inherited
                # or affected by inherited facets
                output = {}
                for i in [0, 1, 2]:
                        i2 = i + 1
                        self._pkg([i], "change-facet "
                            "sync%d=False foo%d=True" % (i2, i2))
                for i in [0, 1, 2]:
                        i2 = i + 1
                        output = \
                            "facet.foo%d\tTrue\tlocal\n" % i2 + \
                            "facet.sync%d\tFalse\tlocal\n" % i2
                        self._pkg([i], "facet -H -F tsv", \
                            output_cb=self._assertEqual_cb(output))

                # disable an inheritable facet and verify it gets inherited
                self._pkg([0], "change-facet 123456=False")
                self._pkg([2], "sync-linked")
                for i in [1, 2]:
                        i2 = i + 1
                        output = \
                            "facet.123456\tFalse\tparent\n" + \
                            "facet.foo%d\tTrue\tlocal\n" % i2 + \
                            "facet.sync%d\tFalse\tlocal\n" % i2
                        self._pkg([i], "facet -H -F tsv", \
                            output_cb=self._assertEqual_cb(output))

                # enable an inheritable facet and verify it doesn't get
                # inherited
                self._pkg([0], "change-facet 123456=True")
                self._pkg([2], "sync-linked")
                for i in [1, 2]:
                        i2 = i + 1
                        output = \
                            "facet.foo%d\tTrue\tlocal\n" % i2 + \
                            "facet.sync%d\tFalse\tlocal\n" % i2
                        self._pkg([i], "facet -H -F tsv", \
                            output_cb=self._assertEqual_cb(output))

                # clear an inheritable facet and verify it doesn't get
                # inherited
                self._pkg([0], "change-facet 123456=False")
                self._pkg([2], "sync-linked")
                self._pkg([0], "change-facet 123456=None")
                self._pkg([2], "sync-linked")
                for i in [1, 2]:
                        i2 = i + 1
                        output = \
                            "facet.foo%d\tTrue\tlocal\n" % i2 + \
                            "facet.sync%d\tFalse\tlocal\n" % i2
                        self._pkg([i], "facet -H -F tsv", \
                            output_cb=self._assertEqual_cb(output))

        def test_facet_inheritance_globs(self):
                """Verify that all facet glob patterns which affect
                inheritable facets get propagated to children."""

                # create parent (0), push child (1)
                self._imgs_create(2)
                self._attach_child(0, [1])

                self._pkg([0], "change-facet" +
                    " 123456=False" +
                    " 456789=True" +
                    " *456*=False" +
                    " *789=True" +
                    " 123*=True")

                # verify that no facets are inherited
                output = ""
                self._pkg([1], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))

                # install packages with inheritable facets in the parent
                self._pkg([0], "install -v %s" % self.p_fmri["inc1@2"])

                # verify that three facets are inherited
                output = ""
                output += "facet.*456*\tFalse\tparent\n"
                output += "facet.123*\tTrue\tparent\n"
                output += "facet.123456\tFalse\tparent\n"
                self._pkg([1], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))

                # install packages with inheritable facets in the parent
                self._pkg([0], "install -v %s" % self.p_fmri["inc2@2"])

                # verify that five facets are inherited
                output = ""
                output += "facet.*456*\tFalse\tparent\n"
                output += "facet.*789\tTrue\tparent\n"
                output += "facet.123*\tTrue\tparent\n"
                output += "facet.123456\tFalse\tparent\n"
                output += "facet.456789\tTrue\tparent\n"
                self._pkg([1], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))

                # remove packages with inheritable facets in the parent
                self._pkg([0], "uninstall -v %s" % self.p_fmri["inc1@2"])

                # verify that three facets are inherited
                output = ""
                output += "facet.*456*\tFalse\tparent\n"
                output += "facet.*789\tTrue\tparent\n"
                output += "facet.456789\tTrue\tparent\n"
                self._pkg([1], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))

                # remove packages with inheritable facets in the parent
                self._pkg([0], "uninstall -v %s" % self.p_fmri["inc2@2"])

                # verify that no facets are inherited
                output = ""
                self._pkg([1], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(output))

        def test_facet_inheritance_masked_system(self):
                """Test reporting of system facets."""

                # create image (0)
                self._imgs_create(1)

                # install a package with facets in the image
                self._pkg([0], "install -v %s" % self.p_fmri["foo@2"])

                # set a facet
                self._pkg([0], "change-facet 'f*1'=False")

                # verify masked output
                output_am  = \
                    "facet.f*1\tFalse\tlocal\tFalse\n" + \
                    "facet.foo1\tFalse\tlocal\tFalse\n" + \
                    "facet.foo2\tTrue\tsystem\tFalse\n" + \
                    "facet.foo3\tTrue\tsystem\tFalse\n"
                output_im  = \
                    "facet.foo1\tFalse\tlocal\tFalse\n" + \
                    "facet.foo2\tTrue\tsystem\tFalse\n" + \
                    "facet.foo3\tTrue\tsystem\tFalse\n"
                self._pkg([0], "facet -H -F tsv -m -a", \
                    output_cb=self._assertEqual_cb(output_am))
                self._pkg([0], "facet -H -F tsv -m -i", \
                    output_cb=self._assertEqual_cb(output_im))

        def test_facet_inheritance_masked_preserve(self):
                """Test handling for masked facets

                Verify that pre-existing local facet settings which get masked
                by inherited facets get restored when the inherited facets go
                away."""

                # create parent (0), push child (1), and pull child (2)
                self._imgs_create(3)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # install a package with inheritable facets in the parent
                self._pkg([0], "install -v %s" % self.p_fmri["inc1@2"])

                for fv in ["True", "False"]:

                        # set inheritable facet locally in children
                        self._pkg([1, 2], "change-facet 123456=%s" % fv)

                        # disable inheritable facet in parent
                        self._pkg([0], "change-facet 123456=False")
                        self._pkg([2], "sync-linked")

                        # verify inheritable facet is disabled in children
                        output = "facet.123456\tFalse\tparent\n"
                        output_m = \
                            "facet.123456\tFalse\tparent\tFalse\n" + \
                            "facet.123456\t%s\tlocal\tTrue\n" % fv
                        for i in [1, 2]:
                                self._pkg([i], "facet -H -F tsv", \
                                    output_cb=self._assertEqual_cb(output))
                                self._pkg([i], "facet -H -F tsv -m", \
                                    output_cb=self._assertEqual_cb(output_m))

                        # clear inheritable facet in the parent
                        self._pkg([0], "change-facet 123456=None")
                        self._pkg([2], "sync-linked")

                        # verify the local child setting is restored
                        output = "facet.123456\t%s\tlocal\n" % fv
                        output_m = "facet.123456\t%s\tlocal\tFalse\n" % fv
                        for i in [1, 2]:
                                self._pkg([i], "facet -H -F tsv", \
                                    output_cb=self._assertEqual_cb(output))
                                self._pkg([i], "facet -H -F tsv -m", \
                                    output_cb=self._assertEqual_cb(output_m))

        def test_facet_inheritance_masked_update(self):
                """Test handling for masked facets.

                Verify that local facet changes can be made while inherited
                facets masking the local settings exist."""

                # create parent (0), push child (1), and pull child (2)
                self._imgs_create(3)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # install a package with inheritable facets in the parent
                self._pkg([0], "install -v %s" % self.p_fmri["inc1@2"])

                # disable inheritable facet in parent
                self._pkg([0], "change-facet 123456=False")
                self._pkg([2], "sync-linked")

                # clear inheritable facet in children
                # the facet is not set in the child so this is a noop
                self._pkg([1, 2], "change-facet 123456=None", rv=EXIT_NOP)

                # verify inheritable facet is disabled in children
                output = "facet.123456\tFalse\tparent\n"
                output_m = "facet.123456\tFalse\tparent\tFalse\n"
                for i in [1, 2]:
                        self._pkg([i], "facet -H -F tsv", \
                            output_cb=self._assertEqual_cb(output))
                        self._pkg([i], "facet -H -F tsv -m", \
                            output_cb=self._assertEqual_cb(output_m))

                for fv in ["True", "False"]:

                        # set inheritable facet locally in children
                        self._pkg([1, 2], "change-facet 123456=%s" % fv)

                        # verify inheritable facet is disabled in children
                        output = "facet.123456\tFalse\tparent\n"
                        output_m = \
                            "facet.123456\tFalse\tparent\tFalse\n" + \
                            "facet.123456\t%s\tlocal\tTrue\n" % fv
                        for i in [1, 2]:
                                self._pkg([i], "facet -H -F tsv", \
                                    output_cb=self._assertEqual_cb(output))
                                self._pkg([i], "facet -H -F tsv -m", \
                                    output_cb=self._assertEqual_cb(output_m))

                        # re-set inheritable facet locall in children
                        # this is a noop
                        self._pkg([1, 2], "change-facet 123456=%s" % fv,
                            rv=EXIT_NOP)

                        # clear inheritable facet in the parent
                        self._pkg([0], "change-facet 123456=None")
                        self._pkg([2], "sync-linked")

                        # verify the local child setting is restored
                        output = "facet.123456\t%s\tlocal\n" % fv
                        output_m = "facet.123456\t%s\tlocal\tFalse\n" % fv
                        for i in [1, 2]:
                                self._pkg([i], "facet -H -F tsv", \
                                    output_cb=self._assertEqual_cb(output))
                                self._pkg([i], "facet -H -F tsv -m", \
                                    output_cb=self._assertEqual_cb(output_m))

                        # disable inheritable facet in parent
                        self._pkg([0], "change-facet 123456=False")
                        self._pkg([2], "sync-linked")

                # clear inheritable facet locally in children
                self._pkg([1, 2], "change-facet 123456=None")

                # verify inheritable facet is disabled in children
                output = "facet.123456\tFalse\tparent\n"
                output_m = "facet.123456\tFalse\tparent\tFalse\n"
                for i in [1, 2]:
                        self._pkg([i], "facet -H -F tsv", \
                            output_cb=self._assertEqual_cb(output))
                        self._pkg([i], "facet -H -F tsv -m", \
                            output_cb=self._assertEqual_cb(output_m))

                # re-clear inheritable facet locally in children
                # this is a noop
                self._pkg([1, 2], "change-facet 123456=None", rv=EXIT_NOP)

                # clear inheritable facet in the parent
                self._pkg([0], "change-facet 123456=None")
                self._pkg([2], "sync-linked")

                # verify the local child setting is restored
                for i in [1, 2]:
                        self._pkg([i], "facet -H -F tsv", \
                            output_cb=self._assertEqual_cb(""))
                        self._pkg([i], "facet -H -F tsv -m", \
                            output_cb=self._assertEqual_cb(""))

        def __test_facet_inheritance_via_op(self, op):
                """Verify that if we do a an "op" operation, the latest facet
                data gets pushed/pulled to child images."""

                # create parent (0), push child (1), and pull child (2)
                self._imgs_create(3)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # install synced incorporations
                self._pkg([0, 1, 2], "install -v %s %s" %
                    (self.p_fmri["inc1@1"], self.p_fmri["foo@1"]))

                # disable a random facet in all images
                self._pkg([0, 1, 2], "change-facet -I foo=False")

                # disable an inheritable facet in the parent while ignoring
                # children.
                self._pkg([0], "change-facet -I 123456=False")

                # verify that the change hasn't been propagated to the child
                output = "facet.foo\tFalse\tlocal\n"
                self._pkg([1, 2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

                # do "op" in the parent and verify the latest facet data was
                # pushed to the child
                self._pkg([0], op)
                output  = "facet.123456\tFalse\tparent\n"
                output += "facet.foo\tFalse\tlocal\n"
                self._pkg([1], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

                # do "op" in the child and verify the latest facet data was
                # pulled from the parent.
                self._pkg([2], op)
                output  = "facet.123456\tFalse\tparent\n"
                output += "facet.foo\tFalse\tlocal\n"
                self._pkg([2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

        def test_facet_inheritance_via_noop_update(self):
                """Verify that if we do a noop update operation, the
                latest facet data still gets pushed/pulled to child images."""

                self.__test_facet_inheritance_via_op(
                    "update")

        def test_facet_inheritance_via_noop_install(self):
                """Verify that if we do a noop install operation, the
                latest facet data still gets pushed/pulled to child images."""

                self.__test_facet_inheritance_via_op(
                    "install -v %s" % self.p_fmri["inc1@1"])

        def test_facet_inheritance_via_noop_change_facet(self):
                """Verify that if we do a noop change-facet operation on a
                parent image, the latest facet data still gets pushed out to
                child images."""

                self.__test_facet_inheritance_via_op(
                    "change-facet foo=False")

        def test_facet_inheritance_via_uninstall(self):
                """Verify that if we do an uninstall operation on a
                parent image, the latest facet data still gets pushed out to
                child images."""

                self.__test_facet_inheritance_via_op(
                    "uninstall -v %s" % self.p_fmri["foo@1"])

        def test_facet_inheritance_cleanup_via_detach(self):
                """Verify that if we detach a child linked image, that any
                inherited facets go away."""

                # create parent (0), push child (1), and pull child (2)
                self._imgs_create(3)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # install synced incorporations
                self._pkg([0, 1, 2], "install -v %s %s" %
                    (self.p_fmri["inc1@1"], self.p_fmri["foo@1"]))

                # disable a random facet in all images
                self._pkg([0, 1, 2], "change-facet -I foo=False")

                # disable an inheritable facet in the parent and make sure the
                # change propagates to all children
                self._pkg([0], "change-facet 123456=False")
                self._pkg([2], "sync-linked")
                output  = "facet.123456\tFalse\tparent\n"
                output += "facet.foo\tFalse\tlocal\n"
                self._pkg([1, 2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

                # simulate detaching children via metadata only
                # verify the inherited facets don't get removed
                self._pkg([0], "detach-linked --linked-md-only -n -l %s" %
                    self.i_name[1])
                self._pkg([2], "detach-linked --linked-md-only -n")
                self._pkg([1, 2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

                # simulate detaching children
                # verify the inherited facets don't get removed
                self._pkg([0], "detach-linked -n -l %s" % self.i_name[1])
                self._pkg([2], "detach-linked -n")
                self._pkg([1, 2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

                # detach children via metadata only
                # verify the inherited facets don't get removed
                # (they can't get removed until we modify the image)
                self._pkg([0], "detach-linked --linked-md-only -l %s" %
                    self.i_name[1])
                self._pkg([2], "detach-linked --linked-md-only")
                self._pkg([1, 2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

                # re-attach children and sanity check facets
                self._attach_child(0, [1])
                self._attach_parent([2], 0)
                self._pkg([1, 2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

                # try to detach children with --no-pkg-updates
                # verify this fails
                # (removal of inherited facets is the equilivant of a
                # change-facet operation, which requires updating all
                # packages, but since we've specified no pkg updates this must
                # fail.)
                self._pkg([0], "detach-linked --no-pkg-updates -l %s" %
                    self.i_name[1], rv=EXIT_OOPS)
                self._pkg([2], "detach-linked --no-pkg-updates", rv=EXIT_OOPS)
                self._pkg([1, 2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

                # detach children
                # verify the inherited facets get removed
                self._pkg([0], "detach-linked -l %s" % self.i_name[1])
                self._pkg([2], "detach-linked")
                output = "facet.foo\tFalse\tlocal\n"
                self._pkg([1, 2], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))

        def __test_missing_facet_inheritance_metadata(self, pfacets="",
            cfacet_output=""):
                """Verify that we can manipulate and update linked child
                images which are missing their parent facet metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly."""

                # create parent (0), push child (1), and pull child (2)
                self._imgs_create(3)
                self._attach_child(0, [1])
                self._attach_parent([2], 0)

                # paths for the linked image metadata files
                md_files = [
                        "%s/var/pkg/linked/linked_pfacets" % self.i_path[i]
                        for i in [1, 2]
                ]

                # isntall foo into each image
                self._pkg([0], "install -v %s" % self.p_fmri["foo@1"])

                # install synced incorporation and package
                self._pkg([0], "install -v %s" % self.p_fmri["inc1@1"])
                self._pkg([2], "sync-linked")

                if pfacets:
                        self._pkg([0], "change-facet %s" % pfacets)
                        self._pkg([2], "sync-linked")

                # verify the child facet settings
                self._pkg([1, 2], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(cfacet_output))

                # verify that the child images are in sync.
                # verify that a sync-linked is a noop
                self._pkg([0], "audit-linked -a")
                self._pkg([1, 2], "audit-linked")
                self._pkg([0], "sync-linked -a -n", rv=EXIT_NOP)
                self._pkg([2], "sync-linked -n", rv=EXIT_NOP)

                # delete linked image metadata files
                for f in md_files:
                        self.file_exists(f)
                        self._ccmd("rm %s" % f)

                # verify the child facet settings
                self._pkg([1, 2], "facet -H -F tsv", \
                    output_cb=self._assertEqual_cb(cfacet_output))

                # verify that audit-linked can handle missing metadata.
                self._pkg([0], "audit-linked -a")
                self._pkg([1, 2], "audit-linked")
                self._pkg([2], "audit-linked --no-parent-sync")

                # verify that sync-linked can handle missing metadata.
                # also verify that the operation will succeed and is
                # not a noop (since it needs to update the metadata).
                self._pkg([0], "sync-linked -a -n")
                self._pkg([2], "sync-linked -n")

                # since we haven't modified the image, make sure the
                # facet metadata files weren't re-created.
                for f in md_files:
                        self.file_doesnt_exist(f)

                # do a sync and verify that the files get created
                self._pkg([0], "sync-linked -a")
                self._pkg([2], "sync-linked")
                for f in md_files:
                        self.file_exists(f)

        def test_missing_facet_inheritance_metadata_1(self):
                """Verify that we can manipulate and update linked child
                images which are missing their parent facet metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly.

                Test when there are no inherited facets present."""
                self.__test_missing_facet_inheritance_metadata()

        def test_missing_facet_inheritance_metadata_2(self):
                """Verify that we can manipulate and update linked child
                images which are missing their parent facet metadata.  Also
                verify that when we update those children the metadata gets
                updated correctly.

                Test with inherited facets present"""
                self.__test_missing_facet_inheritance_metadata(
                    pfacets="123456=False",
                    cfacet_output="facet.123456\tFalse\tparent\n")


class TestConcurrentFacetChange(TestPkgLinked):
        """Class to test that packaging operations work correctly when facets
        are changing concurrently.

        These tests do not focus on verifying that facets are propagated
        correctly from parent to child images."""

        p_misc = """
            open misc@1,5.11-0
            close"""
        p_common = """
            open common@1,5.11-0
            close"""
        p_AA_sync_template = """
            open AA-sync@%(ver)d,5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=require fmri=common
            add depend type=require fmri=A-incorp-sync
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""
        p_AB_sync_template = """
            open AB-sync@%(ver)d,5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=require fmri=common
            add depend type=require fmri=A-incorp-sync
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""
        p_BA_template = """
            open BA@%(ver)d,5.11-0
            add depend type=require fmri=common
            add depend type=require fmri=B-incorp-sync
            close"""
        p_CA_template = """
            open CA@%(ver)d,5.11-0
            add depend type=require fmri=common
            add depend type=require fmri=C-incorp
            close"""
        p_A_incorp_sync_template = """
            open A-incorp-sync@%(ver)d,5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=incorporate fmri=AA-sync@%(ver)d facet.AA-sync=true
            add depend type=incorporate fmri=AB-sync@%(ver)d facet.AA-sync=true
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""
        p_B_incorp_sync_template = """
            open B-incorp-sync@%(ver)d,5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=incorporate fmri=BA@%(ver)d facet.BA=true
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""
        p_C_incorp_template = """
            open C-incorp@%(ver)d,5.11-0
            add depend type=incorporate fmri=CA@%(ver)d facet.CA=true
            close"""
        p_entire_sync_template = """
            open entire-sync@%(ver)d,5.11-0
            add set name=variant.foo value=bar value=baz
            add depend type=require fmri=A-incorp-sync
            add depend type=incorporate fmri=A-incorp-sync@%(ver)d \
                facet.A-incorp-sync=true
            add depend type=require fmri=B-incorp-sync
            add depend type=incorporate fmri=B-incorp-sync@%(ver)d \
                facet.B-incorp-sync=true
            add depend type=require fmri=C-incorp
            add depend type=incorporate fmri=C-incorp@%(ver)d \
                facet.C-incorp=true
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            close"""

        p_data_template = [
            p_AA_sync_template,
            p_AB_sync_template,
            p_BA_template,
            p_CA_template,
            p_A_incorp_sync_template,
            p_B_incorp_sync_template,
            p_C_incorp_template,
            p_entire_sync_template,
        ]

        p_data = [p_misc, p_common]
        for i in range(4):
                for j in p_data_template:
                        p_data.append(j % {"ver": (i + 1)})
        p_fmri = {}

        def setUp(self):
                self.i_count = 2
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
                    image_count=self.i_count)

                # get repo url
                self.rurl1 = self.dcs[1].get_repo_url()

                # populate repository
                for p in self.p_data:
                        fmristr = self.pkgsend_bulk(self.rurl1, p)[0]
                        f = fmri.PkgFmri(fmristr)
                        pkgstr = "%s@%s" % (f.pkg_name, f.version.release)
                        self.p_fmri[pkgstr] = fmristr

                # setup image names and paths
                self.i_name = []
                self.i_path = []
                self.i_api = []
                self.i_api_reset = []
                for i in range(self.i_count):
                        name = "system:img%d" % i
                        self.i_name.insert(i, name)
                        self.i_path.insert(i, self.img_path(i))

        def __test_concurrent_facet_change_via_child_op(self,
            op, op_args, extra_child_pkgs=None, child_variants=None,
            child_pre_op_audit=True, **kwargs):
                """Verify that if we do a operation "op" on a child image, it
                automatically brings its packages in sync with its parent."""

                # create parent (0) and pull child (1)
                self._imgs_create(2)

                # setup the parent image
                parent_facets = [
                    "facet.AA-sync=False",
                    "facet.A-incorp-sync=False",
                    "facet.BA=False",
                ]
                parent_pkgs = [
                    "A-incorp-sync@3",
                    "AA-sync@4",
                    "B-incorp-sync@2",
                    "BA@3",
                    "C-incorp@2",
                    "CA@2",
                    "entire-sync@2",
                ]
                self._pkg([0], "change-facet -v %s" % " ".join(parent_facets))
                self._pkg([0], "install -v %s" % " ".join(parent_pkgs))

                # setup the child image
                child_facets = [
                    "facet.C*=False",
                ]
                child_pkgs = [
                    "A-incorp-sync@1",
                    "AA-sync@1",
                    "B-incorp-sync@1",
                    "BA@1",
                    "C-incorp@1",
                    "CA@1",
                    "entire-sync@1",
                ]
                self._pkg([1], "change-facet -v %s" % " ".join(child_facets))
                if child_variants is not None:
                        self._pkg([1], "change-variant -v %s" %
                            " ".join(child_variants))
                self._pkg([1], "install -v %s" % " ".join(child_pkgs))
                if extra_child_pkgs:
                        self._pkg([1], "install -v %s" %
                            " ".join(extra_child_pkgs))

                # attach the child but don't sync it
                self._attach_parent([1], 0, args="--linked-md-only")

                # verify the child image is still diverged
                if child_pre_op_audit:
                        self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

                # try and then execute op
                def output_cb(output):
                        self.assertEqualParsable(output, **kwargs)
                self._pkg([1], "%s -nv %s" % (op, op_args))
                self._pkg([1], "%s --parsable=0 %s" % (op, op_args),
                    output_cb=output_cb)

                # verify sync via audit and sync (which should be a noop)
                self._pkg([1], "audit-linked")
                self._pkg([1], "sync-linked -v", rv=EXIT_NOP)

        def __pkg_names_to_fmris(self, remove_packages):
                """Convert a list of pkg names to fmris"""
                rv = []
                for s in remove_packages:
                        rv.append(self.p_fmri[s])
                return rv

        def __pkg_name_tuples_to_fmris(self, change_packages):
                """Convert a list of pkg name tuples to fmris"""
                rv = []
                for s, d in change_packages:
                        rv.append([self.p_fmri[s], self.p_fmri[d]])
                return rv

        def test_concurrent_facet_change_via_update(self):
                """Verify that we can update and sync a child
                image while inherited facets are changing."""

                change_facets = [
                    ['facet.A-incorp-sync',
                        False, None, 'parent', False, False],
                    ['facet.AA-sync', False, None, 'parent', False, False],
                ]
                remove_packages = self.__pkg_names_to_fmris([
                    "AB-sync@1",
                ])
                change_packages = self.__pkg_name_tuples_to_fmris([
                    ["A-incorp-sync@1", "A-incorp-sync@3"],
                    ["AA-sync@1",       "AA-sync@4"],
                    ["B-incorp-sync@1", "B-incorp-sync@2"],
                    ["BA@1",            "BA@2"],
                    ["C-incorp@1",      "C-incorp@4"],
                    ["CA@1",            "CA@4"],
                    ["entire-sync@1",   "entire-sync@2"],
                ])
                self.__test_concurrent_facet_change_via_child_op(
                    "update", "--reject AB-sync",
                    extra_child_pkgs=["AB-sync@1"],
                    change_facets=change_facets,
                    remove_packages=remove_packages,
                    change_packages=change_packages)

        def test_concurrent_facet_change_via_update_pkg(self):
                """Verify that we can update a package and sync a child
                image while inherited facets are changing."""

                change_facets = [
                    ['facet.A-incorp-sync',
                        False, None, 'parent', False, False],
                    ['facet.AA-sync', False, None, 'parent', False, False],
                ]
                remove_packages = self.__pkg_names_to_fmris([
                    "AB-sync@1",
                ])
                change_packages = self.__pkg_name_tuples_to_fmris([
                    ["A-incorp-sync@1", "A-incorp-sync@3"],
                    ["AA-sync@1",       "AA-sync@4"],
                    ["B-incorp-sync@1", "B-incorp-sync@2"],
                    ["BA@1",            "BA@2"],
                    ["entire-sync@1",   "entire-sync@2"],
                ])

                # verify update pkg
                self.__test_concurrent_facet_change_via_child_op(
                    "update", "--reject AB-sync common",
                    extra_child_pkgs=["AB-sync@1"],
                    change_facets=change_facets,
                    remove_packages=remove_packages,
                    change_packages=change_packages)

        def test_concurrent_facet_change_via_install(self):
                """Verify that we can install a package and sync a child
                image while inherited facets are changing."""

                change_facets = [
                    ['facet.A-incorp-sync',
                        False, None, 'parent', False, False],
                    ['facet.AA-sync', False, None, 'parent', False, False],
                ]
                remove_packages = self.__pkg_names_to_fmris([
                    "AB-sync@1",
                ])
                add_packages = self.__pkg_names_to_fmris([
                    "misc@1",
                ])
                change_packages = self.__pkg_name_tuples_to_fmris([
                    ["A-incorp-sync@1", "A-incorp-sync@3"],
                    ["AA-sync@1",       "AA-sync@4"],
                    ["B-incorp-sync@1", "B-incorp-sync@2"],
                    ["BA@1",            "BA@2"],
                    ["entire-sync@1",   "entire-sync@2"],
                ])
                self.__test_concurrent_facet_change_via_child_op(
                    "install", "--reject AB-sync misc",
                    extra_child_pkgs=["AB-sync@1"],
                    change_facets=change_facets,
                    remove_packages=remove_packages,
                    add_packages=add_packages,
                    change_packages=change_packages)

        def test_concurrent_facet_change_via_sync(self):
                """Verify that we can sync a child
                image while inherited facets are changing."""

                change_facets = [
                    ['facet.A-incorp-sync',
                        False, None, 'parent', False, False],
                    ['facet.AA-sync', False, None, 'parent', False, False],
                ]
                remove_packages = self.__pkg_names_to_fmris([
                    "AB-sync@1",
                ])
                change_packages = self.__pkg_name_tuples_to_fmris([
                    ["A-incorp-sync@1", "A-incorp-sync@3"],
                    ["AA-sync@1",       "AA-sync@4"],
                    ["B-incorp-sync@1", "B-incorp-sync@2"],
                    ["BA@1",            "BA@2"],
                    ["entire-sync@1",   "entire-sync@2"],
                ])
                self.__test_concurrent_facet_change_via_child_op(
                    "sync-linked", "--reject AB-sync",
                    extra_child_pkgs=["AB-sync@1"],
                    change_facets=change_facets,
                    remove_packages=remove_packages,
                    change_packages=change_packages)

        def test_concurrent_facet_change_via_uninstall(self):
                """Verify that we can uninstall a package and sync a child
                image while inherited facets are changing."""

                change_facets = [
                    ['facet.A-incorp-sync',
                        False, None, 'parent', False, False],
                    ['facet.AA-sync', False, None, 'parent', False, False],
                ]
                remove_packages = self.__pkg_names_to_fmris([
                    "AB-sync@1",
                ])
                change_packages = self.__pkg_name_tuples_to_fmris([
                    ["A-incorp-sync@1", "A-incorp-sync@3"],
                    ["AA-sync@1",       "AA-sync@4"],
                    ["B-incorp-sync@1", "B-incorp-sync@2"],
                    ["BA@1",            "BA@2"],
                    ["entire-sync@1",   "entire-sync@2"],
                ])
                self.__test_concurrent_facet_change_via_child_op(
                    "uninstall", "AB-sync",
                    extra_child_pkgs=["AB-sync@1"],
                    change_facets=change_facets,
                    remove_packages=remove_packages,
                    change_packages=change_packages)

        def test_concurrent_facet_change_via_change_variant(self):
                """Verify that we can change variants and sync a child
                image while inherited facets are changing."""

                change_facets = [
                    ["facet.A-incorp-sync",
                        False, None, "parent", False, False],
                    ["facet.AA-sync", False, None, "parent", False, False],
                ]
                change_variants = [
                    ["variant.foo", "bar"]
                ]
                change_packages = self.__pkg_name_tuples_to_fmris([
                    ["A-incorp-sync@1", "A-incorp-sync@3"],
                    ["AA-sync@1",       "AA-sync@4"],
                    ["B-incorp-sync@1", "B-incorp-sync@2"],
                    ["BA@1",            "BA@2"],
                    ["entire-sync@1",   "entire-sync@2"],
                ])
                self.__test_concurrent_facet_change_via_child_op(
                    "change-variant", "variant.foo=bar",
                    child_variants=["variant.foo=baz"],
                    child_pre_op_audit=False,
                    change_facets=change_facets,
                    change_variants=change_variants,
                    change_packages=change_packages)

        def test_concurrent_facet_change_via_change_facets(self):
                """Verify that we can change facets and sync a child
                image while inherited facets are changing."""

                change_facets = [
                    ["facet.A-incorp-sync",
                        False, None, "parent", False, False],
                    ["facet.AA-sync", False, None, "parent", False, False],
                    ["facet.C-incorp", True, None, "local", False, False],
                ]
                change_packages = self.__pkg_name_tuples_to_fmris([
                    ["A-incorp-sync@1", "A-incorp-sync@3"],
                    ["AA-sync@1",       "AA-sync@4"],
                    ["B-incorp-sync@1", "B-incorp-sync@2"],
                    ["BA@1",            "BA@2"],
                    ["C-incorp@1",      "C-incorp@2"],
                    ["entire-sync@1",   "entire-sync@2"],
                ])
                self.__test_concurrent_facet_change_via_child_op(
                    "change-facet", "facet.C-incorp=True",
                    change_facets=change_facets,
                    change_packages=change_packages)

        def test_concurrent_facet_change_via_detach(self):
                """Verify that we can detach a child image which has inherited
                facets that when removed require updating the image."""

                # create parent (0) and pull child (1)
                self._imgs_create(2)

                # setup the parent image
                parent_facets = [
                    "facet.AA-sync=False",
                    "facet.A-incorp-sync=False",
                ]
                parent_pkgs = [
                    "A-incorp-sync@2",
                    "AA-sync@1",
                    "B-incorp-sync@3",
                    "BA@3",
                    "C-incorp@3",
                    "CA@3",
                    "entire-sync@3",
                ]
                self._pkg([0], "change-facet -v %s" % " ".join(parent_facets))
                self._pkg([0], "install -v %s" % " ".join(parent_pkgs))

                # attach the child.
                self._attach_parent([1], 0)

                # setup the child image
                child_facets = [
                    "facet.C*=False",
                ]
                child_pkgs = [
                    "A-incorp-sync@2",
                    "AA-sync@1",
                    "B-incorp-sync@3",
                    "BA@3",
                    "C-incorp@2",
                    "CA@2",
                    "entire-sync@3",
                ]
                self._pkg([1], "change-facet -v %s" % " ".join(child_facets))
                self._pkg([1], "install -v %s" % " ".join(child_pkgs))

                # a request to detach the child without any package updates
                # should fail.
                self._pkg([1], "detach-linked -v --no-pkg-updates",
                    rv=EXIT_OOPS)

                # detach the child
                self._pkg([1], "detach-linked -v")

                # verify the contents of the child image
                child_fmris = self.__pkg_names_to_fmris([
                    "A-incorp-sync@3",
                    "AA-sync@3",
                    "B-incorp-sync@3",
                    "BA@3",
                    "C-incorp@2",
                    "CA@2",
                    "entire-sync@3",
                ])
                self._pkg([1], "list -v %s" % " ".join(child_fmris))
                output  = "facet.C*\tFalse\tlocal\n"
                self._pkg([1], "facet -H -F tsv",
                    output_cb=self._assertEqual_cb(output))


class TestLinkedInstallHoldRelax(TestPkgLinked):
        """Class to test automatic install-hold relaxing of constrained
        packages when doing different packaging operations.

        When performing packaging operations, any package that has an install
        hold, but also has dependency on itself in its parent, must have that
        install hold relaxed if we expect to be able to bring the image in
        sync with its parent."""

        # the "common" package exists because the solver ignores
        # install-holds unless the package containing them depends on a
        # specific version of another package.  so all our packages depend on
        # the "common" package.
        p_common = """
            open common@1,5.11-0
            close"""
        p_A_template = """
            open A@%(ver)d,5.11-0
            add set name=pkg.depend.install-hold value=A
            add depend type=require fmri=common
            add depend type=incorporate fmri=common@1
            close"""
        p_B_template = """
            open B@%(ver)d,5.11-0
            add set name=variant.foo value=bar value=baz
            add set name=pkg.depend.install-hold value=B
            add depend type=parent fmri=feature/package/dependency/self \
                variant.foo=bar
            add depend type=require fmri=common
            add depend type=incorporate fmri=common@1
            close"""
        p_C_template = """
            open C@%(ver)d,5.11-0
            add set name=pkg.depend.install-hold value=C
            add depend type=require fmri=common
            add depend type=incorporate fmri=common@1
            close"""
        p_BB_template = """
            open BB@%(ver)d,5.11-0
            add depend type=require fmri=B
            add depend type=incorporate fmri=B@%(ver)d
            close"""
        p_BC_template = """
            open BC@%(ver)d,5.11-0
            add depend type=require fmri=B
            add depend type=incorporate fmri=B@%(ver)d
            add depend type=require fmri=C
            add depend type=incorporate fmri=C@%(ver)d
            close"""

        p_data_template = [
            p_A_template,
            p_B_template,
            p_C_template,
            p_BB_template,
            p_BC_template,
        ]
        p_data = [p_common]
        for i in range(4):
                for j in p_data_template:
                        p_data.append(j % {"ver": (i + 1)})
        p_fmri = {}

        def setUp(self):
                self.i_count = 2
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
                    image_count=self.i_count)

                # get repo url
                self.rurl1 = self.dcs[1].get_repo_url()

                # populate repository
                for p in self.p_data:
                        fmristr = self.pkgsend_bulk(self.rurl1, p)[0]
                        f = fmri.PkgFmri(fmristr)
                        pkgstr = "%s@%s" % (f.pkg_name, f.version.release)
                        self.p_fmri[pkgstr] = fmristr

                # setup image names and paths
                self.i_name = []
                self.i_path = []
                self.i_api = []
                self.i_api_reset = []
                for i in range(self.i_count):
                        name = "system:img%d" % i
                        self.i_name.insert(i, name)
                        self.i_path.insert(i, self.img_path(i))

        def __test_linked_install_hold_relax(self, child_pkgs, op, op_args,
            op_rv=EXIT_OK, variant_out_parent_dep=False, **kwargs):
                """Verify that all install-holds get relaxed during
                sync-linked operations."""

                # create parent (0), and pull child (1)
                self._imgs_create(2)

                # install B@2 in the parent
                self._pkg([0], "install -v B@2")

                # install A@1 and B@1 in the child
                self._pkg([1], "install -v %s" % child_pkgs)

                # the parent dependency only exists under variant.foo=bar, if
                # we change variant.foo the parent dependency should go away.
                if variant_out_parent_dep:
                        self._pkg([1], "change-variant variant.foo=baz")

                # link the two images without syncing packages
                self._attach_parent([1], 0, args="--linked-md-only")

                if variant_out_parent_dep:
                        # verify the child is synced
                        self._pkg([1], "audit-linked", rv=EXIT_OK)
                else:
                        # verify the child is diverged
                        self._pkg([1], "audit-linked", rv=EXIT_DIVERGED)

                # execute op
                def output_cb(output):
                        if op_rv == EXIT_OK:
                                self.assertEqualParsable(output, **kwargs)
                self._pkg([1], "%s --parsable=0 %s" % (op, op_args),
                    rv=op_rv, output_cb=output_cb)

        def test_linked_install_hold_relax_all(self):
                """Verify that all install-holds get relaxed during
                sync-linked operations."""

                # verify that sync-linked operation relaxes the install-hold
                # in B and syncs it.
                self.__test_linked_install_hold_relax(
                    "A@1 B@1", "sync-linked", "",
                    change_packages=[
                        [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

                # if we remove the parent dependency in B it should no longer
                # change during sync-linked operation.
                self.__test_linked_install_hold_relax(
                    "BC@1", "sync-linked", "", op_rv=EXIT_NOP,
                    variant_out_parent_dep=True)

        def test_linked_install_hold_relax_constrained_1(self):
                """Verify that any install-holds which are associated with
                constrained packages (ie, packages with parent dependencies)
                get relaxed during install, uninstall and similar
                operations.

                In our child image we'll install 3 packages, A, B, C, all at
                version 1.  pkg A, B, and C, all have install holds.  pkg B
                has a parent dependency and is out of sync.

                We will modify the child image without touching pkg B directly
                and then verify that the install hold in B gets relaxed, there
                by allowing the image to be synced."""

                # verify install
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1", "install", "A@2",
                    change_packages=[
                        [self.p_fmri["A@1"], self.p_fmri["A@2"]],
                        [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

                # verify update pkg
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1", "update", "A@2",
                    change_packages=[
                        [self.p_fmri["A@1"], self.p_fmri["A@2"]],
                        [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

                # verify uninstall
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1", "uninstall", "A@1",
                    remove_packages=[
                        self.p_fmri["A@1"]],
                    change_packages=[
                        [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

                # verify change-variant
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1", "change-variant", "variant.haha=hoho",
                    change_variants=[
                        ['variant.haha', 'hoho']],
                    change_packages=[
                        [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

                # verify change-facet
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1", "change-facet", "facet.haha=False",
                    change_facets=[
                        ['facet.haha', False, None, 'local', False, False]],
                    change_packages=[
                        [self.p_fmri["B@1"], self.p_fmri["B@2"]]])

        def test_linked_install_hold_relax_constrained_2(self):
                """Verify that any install-holds which are not associated with
                constrained packages (ie, packages with parent dependencies)
                don't get relaxed during install, uninstall and similar
                operations.

                In our child image we'll install 4 packages, A, B, C, and BC,
                all at version 1.  pkg A, B, and C, all have install holds.
                pkg B has a parent dependency and is out of sync.  pkg BC
                incorporates B and C and links their versions together.

                The child image is out of sync. we should be able to
                manipulate it, but we won't be able to bring it in sync
                because of the install hold in C."""

                # verify install
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1 BC@1", "install", "A@2",
                    change_packages=[
                        [self.p_fmri["A@1"], self.p_fmri["A@2"]]])

                # verify update pkg
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1 BC@1", "update", "A@2",
                    change_packages=[
                        [self.p_fmri["A@1"], self.p_fmri["A@2"]]])

                # verify uninstall
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1 BC@1", "uninstall", "A@1",
                    remove_packages=[
                        self.p_fmri["A@1"]])

                # verify change-variant
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1 BC@1", "change-variant", "variant.haha=hoho",
                    change_variants=[
                        ['variant.haha', 'hoho']])

                # verify change-facet
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1 BC@1", "change-facet", "facet.haha=False",
                    change_facets=[
                        ['facet.haha', False, None, 'local', False, False]])

        def test_linked_install_hold_relax_constrained_3(self):
                """Verify that any install-holds which are not associated with
                constrained packages (ie, packages with parent dependencies)
                don't get relaxed during install, uninstall and similar
                operations.

                In our child image we'll install 4 packages, A, B, C, and BC,
                all at version 1.  pkg A, B, and C, all have install holds.
                pkg B has a parent dependency and is out of sync.  pkg BC
                incorporates B and C and links their versions together.

                We'll try to update BC, which should fail because of the
                install hold in C."""

                # verify install
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1 BC@1", "install", "BC@2", op_rv=EXIT_OOPS)

                # verify update pkg
                self.__test_linked_install_hold_relax(
                    "A@1 B@1 C@1 BC@1", "update", "BC@2", op_rv=EXIT_OOPS)

        def test_linked_install_hold_relax_constrained_4(self):
                """Verify that any install-holds which are not associated with
                constrained packages (ie, packages with parent dependencies)
                don't get relaxed during install, uninstall and similar
                operations.

                In our child image we'll install 1 package, B@1.  pkg B has an
                install hold and a parent dependency, but its parent
                dependency is disabled by a variant, so the image is in sync.

                We'll try to install package BC@2, which should fail because
                of the install hold in B."""

                # verify install
                self.__test_linked_install_hold_relax(
                    "B@1", "install", "BC@2", op_rv=EXIT_OOPS,
                    variant_out_parent_dep=True)


class TestPkgLinkedScale(pkg5unittest.ManyDepotTestCase):
        """Test the scalability of the linked image subsystem."""

        max_image_count = 256

        p_sync1 = []
        p_vers = [
            "@1.2,5.11-145:19700101T000001Z",
            "@1.2,5.11-145:19700101T000000Z", # old time
            "@1.1,5.11-145:19700101T000000Z", # old ver
            "@1.1,5.11-144:19700101T000000Z", # old build
            "@1.0,5.11-144:19700101T000000Z", # oldest
        ]
        p_files = [
            "tmp/bar",
            "tmp/baz",
        ]

        # generate packages that do need to be synced
        p_sync1_name_gen = "sync1"
        pkgs = [p_sync1_name_gen + ver for ver in p_vers]
        p_sync1_name = dict(zip(range(len(pkgs)), pkgs))
        for i in p_sync1_name:
                p_data = "open %s\n" % p_sync1_name[i]
                p_data += "add depend type=parent fmri=%s" % \
                    pkg.actions.depend.DEPEND_SELF
                p_data += """
                    close\n"""
                p_sync1.append(p_data)

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test"],
                    image_count=self.max_image_count)

                # create files that go in packages
                self.make_misc_files(self.p_files)

                # get repo url
                self.rurl1 = self.dcs[1].get_repo_url()

                # populate repository
                self.pkgsend_bulk(self.rurl1, self.p_sync1)


        def __req_phys_mem(self, phys_mem_req):
                """Verify that the current machine has a minimal amount of
                physical memory (in GB).  If it doesn't raise
                TestSkippedException."""

                psize = os.sysconf(os.sysconf_names["SC_PAGESIZE"])
                ppages = os.sysconf(os.sysconf_names["SC_PHYS_PAGES"])
                phys_mem = psize * ppages / 1024.0 / 1024.0 / 1024.0

                if phys_mem < phys_mem_req:
                        raise pkg5unittest.TestSkippedException(
                            "Not enough memory, "\
                            "%d GB required, %d GB detected.\n" %
                            (phys_mem_req, phys_mem))

        def pkg(self, *args, **kwargs):
                """This is a wrapper function to disable coverage for all
                tests in this class since these are essentially stress tests.
                we don't need the coverage data (since other functional tests
                should have already covered these code paths) and we don't
                want the added overhead of gathering coverage data (since we
                want to use all available resource for actually running the
                tests)."""

                kwargs["coverage"] = False
                return pkg5unittest.ManyDepotTestCase.pkg(self, *args,
                    **kwargs);

        def test_li_scale(self):
                """Verify that we can operate on a large number of linked
                images in parallel.

                For parallel linked image operations, 256 images is high
                enough to cause file descriptor allocation to exceed
                FD_SETSIZE, which in turn can cause select.select() to fail if
                it's invoked.  In practice that's the only failure mode we've
                ever seen when people have tried to update a large number of
                zones in parallel.

                The maximum value successfully tested here has been 512.  I
                tried 1024 but it resulted in death by swapping on a u27 with
                12 GB of memory."""

                # we will require at least 11 GB of memory to run this test.
                # This is a rough estimate of required memory based on
                # observing this test running on s12_20 on an x86 machine.  on
                # that machine i observed the peak RSS for pkg child process
                # was about 24 MB.  with 256 child processes this comes out to
                # about 6 GB of memory.  we require 11 GB so that the machine
                # doesn't get bogged down and other things can continue to
                # run.
                self.__req_phys_mem(11)

                limit = self.max_image_count

                # create an image with a synced package
                self.set_image(0)
                self.image_create(repourl=self.rurl1)
                self.pkg("install -v %s" % self.p_sync1_name[1])

                # create copies of the image.
                for i in range(1, self.max_image_count):
                        self.image_clone(i)

                # attach the copies as children of the original image
                for i in range(1, self.max_image_count):
                        name = "system:img%d" % i
                        cmd = "attach-linked --linked-md-only -c %s %s" % (
                            name, self.img_path(i))
                        self.pkg(cmd)

                # update the parent image and all child images in parallel
                self.pkg("update -C0 -q")


if __name__ == "__main__":
        unittest.main()
