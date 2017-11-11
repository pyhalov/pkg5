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
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.catalog as catalog
import pkg.config as cfg
import pkg.client.pkgdefs as pkgdefs
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.p5p as p5p
import pkg.portable as portable
import pkg.server.repository as repo
import shutil
import subprocess
import tempfile
import time
import urllib
import urlparse
import unittest
import zlib

from pkg.digest import DEFAULT_HASH_FUNC

class TestPkgrecvMulti(pkg5unittest.ManyDepotTestCase):
        # Cleanup after every test.
        persistent_setup = False

        scheme10 = """
            open pkg:/scheme@1.0,5.11-0
            close
        """

        tree10 = """
            open tree@1.0,5.11-0
            add depend type=require-any fmri=leaf@1.0 fmri=branch@1.0
            close
        """

        leaf10 = """
            open leaf@1.0,5.11-0
            close
        """

        branch10 = """
            open branch@1.0,5.11-0
            close
        """

        amber10 = """
            open amber@1.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
            close
        """

        amber20 = """
            open amber@2.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
            close
        """

        amber30 = """
            open amber@3.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
            close
        """

        bronze10 = """
            open bronze@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add depend fmri=pkg:/amber@1.0 type=require
            add license tmp/copyright2 license=copyright
            close
        """

        bronze20 = """
            open bronze@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/amber2
            add license tmp/copyright3 license=copyright
            add file tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """

        misc_files = [ "tmp/bronzeA1",  "tmp/bronzeA2", "tmp/bronze1",
            "tmp/bronze2", "tmp/copyright2", "tmp/copyright3", "tmp/libc.so.1",
            "tmp/sh"]

        def setUp(self):
                """ Start two depots.
                    depot 1 gets foo and moo, depot 2 gets foo and bar
                    depot1 is mapped to publisher test1 (preferred)
                    depot2 is mapped to publisher test1 (alternate)
                    depot3 and depot4 are scratch depots"""

                # This test suite needs actual depots.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test1",
                    "test2", "test2"], start_depots=True)

                self.make_misc_files(self.misc_files)

                self.dpath1 = self.dcs[1].get_repodir()
                self.durl1 = self.dcs[1].get_depot_url()
                self.published = self.pkgsend_bulk(self.durl1, (self.amber10,
                    self.amber20, self.bronze10, self.bronze20))

                # Purposefully republish bronze20 a second later so a version
                # exists that only differs in timestamp.  Also publish tree
                # and scheme after that.
                time.sleep(1)
                self.published.extend(self.pkgsend_bulk(self.durl1,
                    (self.bronze20, self.tree10, self.branch10, self.leaf10,
                    self.scheme10)))

                self.dpath2 = self.dcs[2].get_repodir()
                self.durl2 = self.dcs[2].get_depot_url()
                self.tempdir = tempfile.mkdtemp(dir=self.test_root)

                self.durl3 = self.dcs[3].get_depot_url()
                self.durl4 = self.dcs[4].get_depot_url()

        @staticmethod
        def get_repo(uri):
                parts = urlparse.urlparse(uri, "file", allow_fragments=0)
                path = urllib.url2pathname(parts[2])

                try:
                        return repo.Repository(root=path)
                except cfg.ConfigError as e:
                        raise repo.RepositoryError(_("The specified "
                            "repository's configuration data is not "
                            "valid:\n{0}").format(e))

        def test_0_opts(self):
                """Verify that various basic options work as expected and that
                invalid options or option values return expected exit code."""

                # Test that bad options return expected exit code.
                self.pkgrecv(command="--newest", exit=2)
                self.pkgrecv(self.durl1, "-!", exit=2)
                self.pkgrecv(self.durl1, "-p foo", exit=2)
                self.pkgrecv(self.durl1, "-d {0} gold@1.0-1".format(self.tempdir),
                    exit=1)
                self.pkgrecv(self.durl1, "-d {0} invalid.fmri@1.0.a".format(
                    self.tempdir), exit=1)

                # Test help.
                self.pkgrecv(command="-h", exit=0)

                # Verify that pkgrecv requires a destination repository.
                self.pkgrecv(self.durl1, "'*'", exit=2)

                # Verify that a non-existent repository results in failure.
                npath = os.path.join(self.test_root, "nochance")
                self.pkgrecv(self.durl1, "-d file://{0} foo".format(npath),  exit=1)

                # Test list newest.
                self.pkgrecv(self.durl1, "--newest")
                output = self.reduceSpaces(self.output)
                
                def  _nobuild_fmri(pfmri):
                        return fmri.PkgFmri(pfmri).get_fmri(
                            include_build=False)

                # The latest version of amber and bronze should be listed
                # (sans publisher prefix currently).
                amber = _nobuild_fmri(self.published[1])
                scheme = _nobuild_fmri(self.published[8])
                bronze = _nobuild_fmri(self.published[4])
                tree = _nobuild_fmri(self.published[5])
                branch = _nobuild_fmri(self.published[6])
                leaf = _nobuild_fmri(self.published[7])

                expected = "\n".join((amber, branch, bronze, leaf, scheme, tree)) + "\n"
                self.assertEqualDiff(expected, output)

        def test_1_recv_pkgsend(self):
                """Verify that a received package can be used by pkgsend."""

                f = fmri.PkgFmri(self.published[3], None)

                # First, retrieve the package.
                self.pkgrecv(self.durl1, "--raw -d {0} {1}".format(self.tempdir, f))

                # Next, load the manifest.
                basedir = os.path.join(self.tempdir, f.get_dir_path())
                mpath = os.path.join(basedir, "manifest")

                m = manifest.Manifest()
                raw = open(mpath, "rb").read()
                m.set_content(raw)

                # Verify that the files aren't compressed since -k wasn't used.
                # This is also the format pkgsend will expect for correct
                # republishing.
                ofile = file(os.devnull, "rb")
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                ifile = file(os.path.join(basedir, a.hash),
                                    "rb")

                                # Since the file shouldn't be compressed, this
                                # should return a zlib.error.
                                self.assertRaises(zlib.error,
                                    misc.gunzip_from_stream, ifile, ofile,
                                    ignore_hash=True)

                # Next, send it to another depot
                self.pkgsend(self.durl2, "open foo@1.0-1")
                self.pkgsend(self.durl2,
                    "include -d {0} {1}".format(basedir, mpath))
                self.pkgsend(self.durl2, "close")

        def test_2_recv_compare(self):
                """Verify that a received package is identical to the
                original source."""

                f = fmri.PkgFmri(self.published[4], None)

                # First, pkgrecv the pkg to a directory.  The files are
                # kept compressed so they can be compared directly to the
                # repository's internal copy.
                self.pkgrecv(self.durl1, "--raw -k -d {0} {1}".format(self.tempdir,
                    f))

                # Next, compare the manifests.
                orepo = self.get_repo(self.dpath1)
                old = orepo.manifest(f)
                new = os.path.join(self.tempdir, f.get_dir_path(), "manifest")

                self.assertEqual(
                    misc.get_data_digest(old, hash_func=DEFAULT_HASH_FUNC),
                    misc.get_data_digest(new, hash_func=DEFAULT_HASH_FUNC))

                # Next, load the manifest.
                m = manifest.Manifest()
                raw = open(new, "rb").read()
                m.set_content(raw)

                # Next, compare the package actions that have data.
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                old = orepo.file(a.hash)
                                new = os.path.join(self.tempdir,
                                    f.get_dir_path(), a.hash)
                                self.assertNotEqual(old, new)
                                self.assertEqual(misc.get_data_digest(old,
                                    hash_func=DEFAULT_HASH_FUNC),
                                    misc.get_data_digest(new,
                                    hash_func=DEFAULT_HASH_FUNC))

                # Second, pkgrecv to the pkg to a file repository.
                npath = tempfile.mkdtemp(dir=self.test_root)
                self.pkgsend("file://{0}".format(npath),
                    "create-repository --set-property publisher.prefix=test1")
                self.pkgrecv(self.durl1, "-d file://{0} {1}".format(npath, f))

                # Next, compare the manifests (this will also only succeed if
                # the fmris are exactly the same including timestamp).
                nrepo = self.get_repo(npath)
                old = orepo.manifest(f)
                new = nrepo.manifest(f)

                self.debug(old)
                self.debug(new)
                self.assertEqual(
                    misc.get_data_digest(old, hash_func=DEFAULT_HASH_FUNC),
                    misc.get_data_digest(new, hash_func=DEFAULT_HASH_FUNC))

                # Next, load the manifest.
                m = manifest.Manifest()
                raw = open(new, "rb").read()
                m.set_content(raw)

                # Next, compare the package actions that have data.
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                old = orepo.file(a.hash)
                                new = nrepo.file(a.hash)
                                self.assertNotEqual(old, new)
                                self.assertEqual(misc.get_data_digest(old,
                                    hash_func=DEFAULT_HASH_FUNC),
                                    misc.get_data_digest(new,
                                    hash_func=DEFAULT_HASH_FUNC))

                # Third, pkgrecv to the pkg to a http repository from the
                # file repository from the last test.
                self.pkgrecv("file://{0}".format(npath), "-d {0} {1}".format(
                    self.durl2, f))
                orepo = nrepo

                # Next, compare the manifests (this will also only succeed if
                # the fmris are exactly the same including timestamp).
                nrepo = self.get_repo(self.dpath2)
                old = orepo.manifest(f)
                new = nrepo.manifest(f)

                self.assertEqual(
                    misc.get_data_digest(old, hash_func=DEFAULT_HASH_FUNC),
                    misc.get_data_digest(new, hash_func=DEFAULT_HASH_FUNC))

                # Next, load the manifest.
                m = manifest.Manifest()
                raw = open(new, "rb").read()
                m.set_content(raw)

                # Next, compare the package actions that have data.
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                old = orepo.file(a.hash)
                                new = nrepo.file(a.hash)
                                self.assertNotEqual(old, new)
                                self.assertEqual(
                                    misc.get_data_digest(old,
                                    hash_func=DEFAULT_HASH_FUNC),
                                    misc.get_data_digest(new,
                                    hash_func=DEFAULT_HASH_FUNC))

                # Fourth, create an image and verify that the sent package is
                # seen by the client.
                self.wait_repo(self.dpath2)
                self.image_create(self.durl2, prefix="test1")
                self.pkg("info -r bronze@2.0")

                # Fifth, pkgrecv the pkg to a file repository and compare the
                # manifest of a package published with the scheme (pkg:/) given.
                f = fmri.PkgFmri(self.published[6], None)
                npath = tempfile.mkdtemp(dir=self.test_root)
                self.pkgsend("file://{0}".format(npath),
                    "create-repository --set-property publisher.prefix=test1")
                self.pkgrecv(self.durl1, "-d file://{0} {1}".format(npath, f))

                # Next, compare the manifests (this will also only succeed if
                # the fmris are exactly the same including timestamp).
                orepo = self.get_repo(self.dpath1)
                nrepo = self.get_repo(npath)
                old = orepo.manifest(f)
                new = nrepo.manifest(f)

                self.assertEqual(
                    misc.get_data_digest(old, hash_func=DEFAULT_HASH_FUNC),
                    misc.get_data_digest(new, hash_func=DEFAULT_HASH_FUNC))

        def test_3_recursive(self):
                """Verify that retrieving a package recursively will retrieve
                its dependencies as well."""

                bronze = fmri.PkgFmri(self.published[4], None)

                # Retrieve bronze recursively to a directory, this should
                # also retrieve its dependency: amber, and amber's dependency:
                # tree.
                self.pkgrecv(self.durl1, "--raw -r -k -d {0} {1}".format(self.tempdir,
                    bronze))

                amber = fmri.PkgFmri(self.published[1], None)
                tree = fmri.PkgFmri(self.published[5], None)

                # Verify that the manifests for each package was retrieved.
                for f in (amber, bronze, tree):
                        mpath = os.path.join(self.tempdir, f.get_dir_path(),
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

        def test_4_timever(self):
                """Verify that receiving with -m options work as expected."""

                bronze10 = fmri.PkgFmri(self.published[2], None)
                bronze20_1 = fmri.PkgFmri(self.published[3], None)
                bronze20_2 = fmri.PkgFmri(self.published[4], None)

                # Retrieve bronze using -m all-timestamps and a version pattern.
                # This should only retrieve bronze20_1 and bronze20_2.
                self.pkgrecv(self.durl1, "--raw -m all-timestamps -r -k "
                    "-d {0} {1}".format(self.tempdir, "/bronze@2.0"))

                # Verify that only expected packages were retrieved.
                expected = [
                    bronze20_1.get_dir_path(),
                    bronze20_2.get_dir_path(),
                ]

                for d in os.listdir(os.path.join(self.tempdir, "bronze")):
                        self.assertTrue(os.path.join("bronze", d) in expected)

                        mpath = os.path.join(self.tempdir, "bronze", d,
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

                # Cleanup for next test.
                shutil.rmtree(os.path.join(self.tempdir, "bronze"))

                # Retrieve bronze using -m all-timestamps and a package stem.
                # This should retrieve bronze10, bronze20_1, and bronze20_2.
                self.pkgrecv(self.durl1, "--raw -m all-timestamps -r -k "
                    "-d {0} {1}".format(self.tempdir, "bronze"))

                # Verify that only expected packages were retrieved.
                expected = [
                    bronze10.get_dir_path(),
                    bronze20_1.get_dir_path(),
                    bronze20_2.get_dir_path(),
                ]

                for d in os.listdir(os.path.join(self.tempdir, "bronze")):
                        self.assertTrue(os.path.join("bronze", d) in expected)

                        mpath = os.path.join(self.tempdir, "bronze", d,
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

                # Cleanup for next test.
                shutil.rmtree(os.path.join(self.tempdir, "bronze"))

                # Retrieve bronze using -m all-versions, this should only
                # retrieve bronze10 and bronze20_2.
                self.pkgrecv(self.durl1, "--raw -m all-versions -r -k "
                    "-d {0} {1}".format(self.tempdir, "bronze"))

                # Verify that only expected packages were retrieved.
                expected = [
                    bronze10.get_dir_path(),
                    bronze20_2.get_dir_path(),
                ]

                for d in os.listdir(os.path.join(self.tempdir, "bronze")):
                        self.assertTrue(os.path.join("bronze", d) in expected)

                        mpath = os.path.join(self.tempdir, "bronze", d,
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

                # Cleanup for next test.
                shutil.rmtree(os.path.join(self.tempdir, "bronze"))

                # Retrieve bronze using -m latest, this should only
                # retrieve bronze20_2.
                self.pkgrecv(self.durl1, "--raw -m latest -r -k "
                    "-d {0} {1}".format(self.tempdir, "bronze"))

                # Verify that only expected packages were retrieved.
                expected = [
                    bronze20_2.get_dir_path(),
                ]

                for d in os.listdir(os.path.join(self.tempdir, "bronze")):
                        self.assertTrue(os.path.join("bronze", d) in expected)

                        mpath = os.path.join(self.tempdir, "bronze", d,
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

                # Cleanup for next test.
                shutil.rmtree(os.path.join(self.tempdir, "bronze"))

                # Retrieve bronze using default setting.
                # This should retrieve bronze10, bronze20_1, and bronze20_2.
                self.pkgrecv(self.durl1, "--raw -r -k "
                    "-d {0} {1}".format(self.tempdir, "bronze"))

                # Verify that all expected packages were retrieved.
                expected = [
                    bronze10.get_dir_path(),
                    bronze20_1.get_dir_path(),
                    bronze20_2.get_dir_path(),
                ]

                for d in expected:
                        paths = os.listdir(os.path.join(self.tempdir, "bronze"))
                        self.assertTrue(os.path.basename(d) in paths)

                        mpath = os.path.join(self.tempdir, d, "manifest")
                        self.assertTrue(os.path.isfile(mpath))

        def test_5_recv_env(self):
                """Verify that pkgrecv environment vars work as expected."""

                f = fmri.PkgFmri(self.published[3], None)

                os.environ["PKG_SRC"] = self.durl1
                os.environ["PKG_DEST"] = self.tempdir

                # First, retrieve the package.
                self.pkgrecv(command="--raw {0}".format(f))

                # Next, load the manifest.
                basedir = os.path.join(self.tempdir, f.get_dir_path())
                mpath = os.path.join(basedir, "manifest")

                m = manifest.Manifest()
                raw = open(mpath, "rb").read()
                m.set_content(raw)

                # This is also the format pkgsend will expect for correct
                # republishing.
                ofile = file(os.devnull, "rb")
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                ifile = file(os.path.join(basedir, a.hash),
                                    "rb")

                                # Since the file shouldn't be compressed, this
                                # should return a zlib.error.
                                self.assertRaises(zlib.error,
                                    misc.gunzip_from_stream, ifile, ofile,
                                    ignore_hash=True)

                for var in ("PKG_SRC", "PKG_DEST"):
                        del os.environ[var]

        def test_6_recv_republish_preexisting(self):
                f = fmri.PkgFmri(self.published[5], None)
                f2 = fmri.PkgFmri(self.published[4], None)

                # First, pkgrecv tree into a file repository
                npath = tempfile.mkdtemp(dir=self.test_root)
                self.pkgsend("file://{0}".format(npath),
                    "create-repository --set-property publisher.prefix=test1")
                self.pkgrecv(self.durl1, "-d file://{0} {1}".format(npath, f))

                # Next, recursively pkgrecv bronze2.0 into a file repository
                # This would fail before behavior fixed to skip existing pkgs.
                self.pkgrecv(self.durl1, "-r -d file://{0} {1}".format(npath, f2))

        def test_7_recv_multipublisher(self):
                """Verify that pkgrecv handles multi-publisher repositories as
                expected."""

                # Setup a repository with packages from multiple publishers.
                amber = self.amber10.replace("open ", "open //test2/")
                self.pkgsend_bulk(self.durl3, amber)
                self.pkgrecv(self.durl1, "-d {0} amber@1.0 bronze@1.0".format(
                    self.durl3))

                # Now attempt to receive from a repository with packages from
                # multiple publishers and verify entry exists only for test1.
                self.pkgrecv(self.durl3, "-d {0} bronze".format(self.durl4))
                self.pkgrecv(self.durl3, "--newest")
                self.assertNotEqual(self.output.find("test1/bronze"), -1)
                self.assertEqual(self.output.find("test2/bronze"), -1)

                # Now retrieve amber, and verify entries exist for both pubs.
                self.wait_repo(self.dcs[4].get_repodir())
                self.wait_repo(self.dcs[3].get_repodir())
                self.pkgrecv(self.durl3, "-d {0} amber".format(self.durl4))
                self.pkgrecv(self.durl4, "--newest")
                self.assertNotEqual(self.output.find("test1/amber"), -1)
                self.assertNotEqual(self.output.find("test2/amber"), -1)

                # Verify attempting to retrieve a non-existent package fails
                # for a multi-publisher repository.
                self.pkgrecv(self.durl3, "-d {0} nosuchpackage".format(self.durl4),
                    exit=1)

        def test_8_archive(self):
                """Verify that pkgrecv handles package archives as expected."""

                # Setup a repository with packages from multiple publishers.
                amber = self.amber10.replace("open ", "open pkg://test2/")
                t2_amber10 = self.pkgsend_bulk(self.durl3, amber)[0]
                self.pkgrecv(self.durl1, "-d {0} amber@1.0 bronze@1.0".format(
                    self.durl3))

                # Now attempt to receive from a repository to a package archive.
                arc_path = os.path.join(self.test_root, "test.p5p")
                self.pkgrecv(self.durl3, "-a -d {0} \*".format(arc_path))

                #
                # Verify that the archive can be opened and the expected
                # packages are inside.
                #
                amber10 = self.published[0]
                bronze10 = self.published[2]
                arc = p5p.Archive(arc_path, mode="r")

                # Check for expected publishers.
                expected = set(["test1", "test2"])
                pubs = set(p.prefix for p in arc.get_publishers())
                self.assertEqualDiff(expected, pubs)

                # Check for expected package FMRIs.
                expected = set([amber10, t2_amber10, bronze10])
                tmpdir = tempfile.mkdtemp(dir=self.test_root)
                returned = []
                for pfx in pubs:
                        catdir = os.path.join(tmpdir, pfx)
                        os.mkdir(catdir)
                        for part in ("catalog.attrs", "catalog.base.C"):
                                arc.extract_catalog1(part, catdir, pfx)

                        cat = catalog.Catalog(meta_root=catdir, read_only=True)
                        returned.extend(str(f) for f in cat.fmris())
                self.assertEqualDiff(expected, set(returned))
                arc.close()
                shutil.rmtree(tmpdir)

                #
                # Verify that packages can be received from an archive to an
                # archive.
                #
                arc2_path = os.path.join(self.test_root, "test2.p5p")
                self.pkgrecv(arc_path, "-a -d {0} pkg://test2/amber".format(arc2_path))

                # Check for expected publishers.
                arc = p5p.Archive(arc2_path, mode="r")
                expected = set(["test2"])
                pubs = set(p.prefix for p in arc.get_publishers())
                self.assertEqualDiff(expected, pubs)

                # Check for expected package FMRIs.
                expected = set([t2_amber10])
                tmpdir = tempfile.mkdtemp(dir=self.test_root)
                returned = []
                for pfx in pubs:
                        catdir = os.path.join(tmpdir, pfx)
                        os.mkdir(catdir)
                        for part in ("catalog.attrs", "catalog.base.C"):
                                arc.extract_catalog1(part, catdir, pfx)

                        cat = catalog.Catalog(meta_root=catdir, read_only=True)
                        returned.extend(str(f) for f in cat.fmris())
                self.assertEqualDiff(expected, set(returned))
                arc.close()

                #
                # Verify that pkgrecv gracefully fails if archive already
                # exists.
                #
                self.pkgrecv(arc_path, "-d {0} \*".format(arc2_path), exit=1)

                #
                # Verify that packages can be received from an archive to
                # a repository.
                #
                self.pkgrecv(arc_path, "--newest")
                self.pkgrecv(arc_path, "-d {0} pkg://test2/amber bronze".format(
                    self.durl4))
                self.wait_repo(self.dcs[4].get_repodir())
                repo = self.dcs[4].get_repo()
                self.pkgrecv(repo.root, "--newest")

                # Check for expected publishers.
                expected = set(["test1", "test2"])
                pubs = repo.publishers
                self.assertEqualDiff(expected, pubs)

                # Check for expected package FMRIs.
                expected = sorted([t2_amber10, bronze10])
                returned = []
                for pfx in repo.publishers:
                        cat = repo.get_catalog(pub=pfx)
                        returned.extend(str(f) for f in cat.fmris())
                self.assertEqualDiff(expected, sorted(returned))

                # Attempt a dry-run to receive a package archive.
                # We should not have the archive created in this case.
                arc_path = os.path.join(self.test_root, "dry-run.p5p")
                self.pkgrecv(self.durl3, "-n -a -d {0} \*".format(arc_path))
                self.assertFalse(os.path.exists(arc_path))

        def test_9_dryruns(self):
                """Test that the dry run option to pkgrecv works as expected."""

                f = fmri.PkgFmri(self.published[3], None)

                rpth = tempfile.mkdtemp(dir=self.test_root)
                self.pkgrepo("create {0}".format(rpth))
                expected = ["pkg5.repository"]
                self.pkgrecv(self.durl1, "-n -d {0} {1}".format(rpth, f))
                self.assertEqualDiff(expected, os.listdir(rpth))

                self.pkgrecv(self.durl1, "-r -n -d {0} {1}".format(rpth, f))
                self.assertEqualDiff(expected, os.listdir(rpth))

                self.pkgrecv(self.durl1, "--clone -n -p '*' -d {0}".format(rpth))
                self.assertEqualDiff(expected, os.listdir(rpth))

                arc_path = os.path.join(self.test_root, "test.p5p")
                self.pkgrecv(self.durl1, "-a -n -d {0} \*".format(arc_path))
                self.assert_(not os.path.exists(arc_path))

                # --raw actually populates the destination with manifests even
                # with -n, so just check that it exits 0.
                self.pkgrecv(self.durl1, "--raw -n -d {0} {1}".format(
                    self.tempdir, f))

                # --raw actually populates the destination with manifests even
                # with -n, so just check that it exits 0.
                self.pkgrecv(self.durl1, "--raw -r -n -d {0} {1}".format(
                    self.tempdir, f))

        def test_10_unsupported_actions(self):
                """Test that pkgrecv skips packages with actions it can't
                understand, processes those it can, and exits with appropriate
                exit codes."""

                def __count_pulled_packages(pth):
                        self.pkgrepo("list -F tsv -H -s {0}".format(pth))
                        return len(self.output.splitlines())

                def __check_errout(pfmri):
                        s1 = "invalid action in package {0}".format(pfmri)
                        s2 = "Malformed action in package '{0}'".format(pfmri)
                        self.assert_(s1 in self.errout or s2 in self.errout,
                            "{0} not in error".format(pfmri))

                def __empty_repo(uri, arg_string):
                        if uri.startswith("http://"):
                                rurl = self.dcs[4].get_repo_url()
                                self.pkgrepo("remove -s {0} '*'".format(rurl))
                                # Refresh the depot to get it to realize that
                                # the catalog has changed.
                                self.dcs[4].refresh()
                        elif arg_string:
                                portable.remove(uri)
                        else:
                                self.pkgrepo("remove -s {0} '*'".format(uri))


                def __test_rec(duri, arg_string, pfmris):
                        self.debug("\n\nNow pkgrecv'ing to {0}".format(duri))

                        # It's necessary to use the -D option below because
                        # otherwise pkgrecv will fail because the manifest
                        # doesn't validate.

                        novalidate = "-D manifest_validate=Never "
                        # Check that invalid action attributes don't cause
                        # tracebacks.
                        self.pkgrecv(self.durl1, novalidate +
                            "-d {0} {1} {2}".format(duri, arg_string,
                            " ".join(pfmris)), exit=pkgdefs.EXIT_OOPS)
                        for pfmri in pfmris:
                                __check_errout(pfmri)
                        self.assertEqual(__count_pulled_packages(duri), 0)
                        if arg_string:
                                portable.remove(duri)

                        self.pkgrecv(self.rurl1, novalidate +
                            "-d {0} {1} {2}".format(duri, arg_string,
                            " ".join(pfmris)), exit=pkgdefs.EXIT_OOPS)
                        for pfmri in pfmris:
                                __check_errout(pfmri)
                        self.assertEqual(__count_pulled_packages(duri), 0)
                        if arg_string:
                                portable.remove(duri)

                        # Check that other packages are retrieved and the exit
                        # code reflects partial success.
                        self.pkgrecv(self.durl1, novalidate +
                            "-d {0} {1} -m all-timestamps '*'".format(
                            duri, arg_string), exit=pkgdefs.EXIT_PARTIAL)
                        for pfmri in pfmris:
                                __check_errout(pfmri)
                        self.assertEqual(__count_pulled_packages(duri),
                            len(self.published) - len(pfmris))
                        __empty_repo(duri, arg_string)

                        self.pkgrecv(self.rurl1, novalidate +
                            "-d {0} {1} -m all-timestamps '*'".format(
                            duri, arg_string), exit=pkgdefs.EXIT_PARTIAL)
                        for pfmri in pfmris:
                                __check_errout(pfmri)
                        self.assertEqual(__count_pulled_packages(duri),
                            len(self.published) - len(pfmris))
                        __empty_repo(duri, arg_string)

                self.rurl1 = self.dcs[1].get_repo_url()
                repo = self.dcs[1].get_repo()
                rd = repo.get_pub_rstore()
                pfmri = fmri.PkgFmri(self.published[4])
                mp = rd.manifest(pfmri)

                with open(mp, "rb") as fh:
                        original_txt = fh.read()
                txt = original_txt.replace("type=require", "type=foo")
                with open(mp, "wb") as fh:
                        fh.write(txt)

                rpth = tempfile.mkdtemp(dir=self.test_root)
                self.pkgrepo("create {0}".format(rpth))
                adir = tempfile.mkdtemp(dir=self.test_root)

                # The __empty repo function above assumes that the only http uri
                # used is the one for depot number 4.
                dest_uris = ((rpth, ""), (self.durl4, ""),
                    (os.path.join(adir, "archive.p5p"), "-a"))
                for duri, arg_string in dest_uris:
                        __test_rec(duri, arg_string, [self.published[4]])

                # Test that multiple packages failing are handled correctly.
                for i in range(5, 7):
                        pfmri = fmri.PkgFmri(self.published[i])
                        mp = rd.manifest(pfmri)
                        with open(mp, "rb") as fh:
                                original_txt = fh.read()
                        txt = "foop\n" + original_txt
                        with open(mp, "wb") as fh:
                                fh.write(txt)

                for duri, arg_string, in dest_uris:
                        __test_rec(duri, arg_string, self.published[4:7])

        def test_11_clone(self):
                """Verify that pkgrecv handles cloning repos as expected."""
                # Test basic operation of cloning repo which contains one
                # publisher to repo which contains same publisher
                self.pkgrecv(self.durl1, "--clone -d {0}".format(self.dpath2))

                ret = subprocess.call(["/usr/bin/gdiff", "-Naur", "-x", 
                    "index", "-x", "trans", self.dpath1, self.dpath2])
                self.assertTrue(ret==0)

                # Test that packages in dst which are not in src get removed.
                self.pkgsend_bulk(self.durl2, (self.amber30))
                self.pkgrecv(self.durl1, "--clone -d {0}".format(self.dpath2))
                ret = subprocess.call(["/usr/bin/gdiff", "-Naur", "-x", 
                    "index", "-x", "trans", self.dpath1, self.dpath2])
                self.assertTrue(ret==0)

                # Test that clone reports publishers not in the dest repo.
                amber = self.amber10.replace("open ", "open pkg://test2/")
                self.pkgsend_bulk(self.durl1, amber)
                self.pkgrecv(self.durl1, "--clone -d {0}".format(self.dpath2), exit=1)

                # Test that clone adds new publishers if requested.
                amber = self.amber10.replace("open ", "open pkg://test2/")
                self.pkgsend_bulk(self.durl1, amber)
                self.pkgrecv(self.durl1, "--clone -d {0} -p test2".format(self.dpath2))
                ret = subprocess.call(["/usr/bin/gdiff", "-Naur", "-x", 
                    "index", "-x", "trans", self.dpath1,
                    self.dpath2])
                self.assertTrue(ret==0)

                # Test that clone removes all packages if source is empty
                self.pkgrecv(self.durl3, "--clone -d {0}".format(self.dpath2))
                self.pkgrepo("-s {0} list -H -p test2".format(self.dpath2))
                self.assertEqualDiff("", self.output)

                # Test that clone works fine with mulitple publishers
                amber = self.amber10.replace("open ", "open pkg://test2/")
                self.pkgsend_bulk(self.durl1, amber)

                path = os.path.join(self.dpath2, "publisher/test1")
                shutil.rmtree(path)
                path = os.path.join(self.dpath2, "publisher/test2")
                shutil.rmtree(path)
                self.pkgrecv(self.durl1, "--clone -d {0} -p test2 -p test1".format(
                    self.dpath2))
                ret = subprocess.call(["/usr/bin/gdiff", "-Naur", "-x",
                    "index", "-x", "trans", self.dpath1, self.dpath2])
                self.assertTrue(ret==0)

                # Test that clone fails if --raw is specified.
                self.pkgrecv(self.durl1, "--raw --clone -d {0} -p test2".format(
                    self.dpath2), exit=2)

                # Test that clone fails if -c is specified.
                self.pkgrecv(self.durl1, "-c /tmp/ --clone -d {0} -p test2".format(
                    self.dpath2), exit=2)

                # Test that clone fails if -a is specified.
                self.pkgrecv(self.durl1, "-a --clone -d {0} -p test2".format(
                    self.dpath2), exit=2)

                # Test that clone fails if --newest is specified.
                self.pkgrecv(self.durl1, "--newest --clone -d {0} -p test2".format(
                    self.dpath2), exit=2)

        def test_12_multihash(self):
                """Tests that we can recv to and from repositories with
                multi-hash support, interoperating with repositories without
                multi-hash support."""
                self.base_12_multihash("sha256")

        def base_12_multihash(self, hash_alg):
                f = fmri.PkgFmri(self.published[3], None)
                # We create an image simply so we can use "contents -g" to
                # inspect the repository.
                self.image_create()

                # First, recv the package and verify it has no extended hashes
                self.pkgrecv(self.durl1, "-d {0} {1}".format(self.durl3, f))
                self.pkg("contents -g {0} -m {1}".format(self.durl3, f))
                self.assert_("pkg.hash.{0}".format(hash_alg not in self.output))

                # Now stop and start the repository as multi-hash aware, and
                # recv it again, making sure that we do not get multiple hashes
                # added (because modifying the manifest would break signatures)
                self.dcs[3].stop()
                self.dcs[3].set_debug_feature("hash=sha1+{0}".format(hash_alg))
                self.dcs[3].start()
                self.pkgrecv(self.durl1, "-d {0} {1}".format(self.durl3, f))
                self.pkg("contents -g {0} -m {1}".format(self.durl3, f))
                self.assert_("pkg.hash.{0}".format(hash_alg not in self.output))

                # Now check the reverse - that a package with multiple hashes
                # can be received into a repository that is not multi-hash aware
                b = "bronze@1.0,5.11-0"
                self.pkgsend_bulk(self.durl3, self.bronze10)
                self.pkg("contents -g {0} -m {1}".format(self.durl3, b))
                self.assert_("pkg.hash.{0}".format(hash_alg in self.output))
                self.pkgrecv(self.durl3, "-d {0} {1}".format(self.durl4, b))
                self.pkg("contents -g {0} -m {1}".format(self.durl4, b))
                self.assert_("pkg.hash.{0}".format(hash_alg in self.output))

                # Ensure that we can recv multi-hash packages into p5p files
                p5p_path = os.path.join(self.test_root,
                    "multi-hash-{0}.p5p".format(hash_alg))
                self.pkgrecv(self.durl3, "-ad {0} {1}".format(p5p_path, b))
                self.pkg("contents -g {0} -m {1}".format(p5p_path, b))
                self.assert_("pkg.hash.{0}".format(hash_alg in self.output))

                # Finally, stop and start our scratch repository to clear the
                # debug feature. If this doesn't happen because we've failed
                # before now, it's not the end of the world.
                self.dcs[3].stop()
                self.dcs[3].unset_debug_feature("hash=sha1+{0}".format(hash_alg))
                self.dcs[3].start()

        def test_13_output(self):
                """Verify that pkgrecv handles verbose output as expected."""

                # Now attempt to receive from a repository.
                self.pkgrepo("create {0}".format(self.tempdir))
                self.pkgrecv(self.dpath1, "-d {0} -n -v \*".format(self.tempdir))
                expected = """\
Retrieving packages (dry-run) ...
        Packages to add:        9
      Files to retrieve:       17
Estimated transfer size: 528.00 B
"""
                self.assert_(expected in self.output, self.output)
                for s in self.published:
                        self.assert_(fmri.PkgFmri(s).get_fmri(anarchy=True,
                            include_scheme=False) in self.output)

                # Clean up for next test.
                shutil.rmtree(self.tempdir)

                # Now attempt to receive from a repository to a package archive.
                self.pkgrecv(self.dpath1, "-a -d {0} -n -v \*".format(self.tempdir))
                expected = """\
Archiving packages (dry-run) ...
        Packages to add:        9
      Files to retrieve:       17
Estimated transfer size: 528.00 B
"""
                self.assert_(expected in self.output, self.output)
                for s in self.published:
                        self.assert_(fmri.PkgFmri(s).get_fmri(anarchy=True,
                            include_scheme=False) in self.output)

                # Now attempt to clone a repository.
                self.pkgrepo("create {0}".format(self.tempdir))
                self.pkgrecv(self.dpath1, "--clone -d {0} -p \* -n -v" \
                   .format(self.tempdir))
                expected = """\
Retrieving packages (dry-run) ...
        Packages to add:        9
      Files to retrieve:       17
Estimated transfer size: 528.00 B
"""
                self.assert_(expected in self.output, self.output)
                for s in self.published:
                        self.assert_(fmri.PkgFmri(s).get_fmri(anarchy=True,
                            include_scheme=False) in self.output)

                # Test that output is correct if -n is not specified.
                self.pkgrecv(self.dpath1, "-d {0} -v \*".format(self.tempdir))
                self.assert_("dry-run" not in self.output)


class TestPkgrecvHTTPS(pkg5unittest.HTTPSTestClass):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=/usr/bin/example_path
            close"""

        misc_files = ["tmp/example_file", "tmp/empty", "tmp/verboten"]

        def setUp(self):
                pubs = ["src", "dst"]

                pkg5unittest.HTTPSTestClass.setUp(self, pubs,
                    start_depots=True)

                self.srurl = self.dcs[1].get_repo_url()
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.srurl, self.example_pkg10)

                self.surl = self.ac.url + "/{0}".format(pubs[0])
                self.durl = self.ac.url + "/{0}".format(pubs[1])

                #set permissions of tmp/verboten to make it non-readable
                self.verboten = os.path.join(self.test_root, "tmp/verboten")
                os.system("chmod 600 {0}".format(self.verboten))
                

        def test_01_basics(self):
                """Test that transfering a package from an https repo to
                another https repo works"""

                self.ac.start()

                arg_dict = {
                    "cert": os.path.join(self.cs_dir, self.get_cli_cert("src")),
                    "key": os.path.join(self.keys_dir, self.get_cli_key("src")),
                    "dst": self.durl,
                    "dcert": os.path.join(self.cs_dir, self.get_cli_cert("dst")),
                    "dkey": os.path.join(self.keys_dir, self.get_cli_key("dst")),
                    "pkg": "example_pkg@1.0,5.11-0",
                    "empty": os.path.join(self.test_root, "tmp/empty"),
                    "noexist": os.path.join(self.test_root, "octopus"),
                    "verboten": self.verboten,
                }

                # We need an image for seed_ta_dir() to work.
                # TODO: there might be a cleaner way of doing this
                self.image_create()
                # Add the trust anchor needed to verify the server's identity.
                self.seed_ta_dir("ta7")

                # We try to receive a pkg from a secured repo and publish it to
                # another secured repo where both repos require different
                # credentials
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict))

                # Now try to use the same credentials for source and dest.
                # This should fail.
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {key} --dcert {cert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Make sure we don't traceback when credential files are invalid
                # Src certificate option missing
                self.pkgrecv(self.surl, "--key {key} -d {dst} "
                    "--dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Dst certificate option missing
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {dkey} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Src key option missing
                self.pkgrecv(self.surl, "--cert {cert} "
                    "-d {dst} --dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Dst key option missing
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Src certificate not found
                self.pkgrecv(self.surl, "--key {key} --cert {noexist} "
                    "-d {dst} --dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Dst certificate not found
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {dkey} --dcert {noexist} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Src key not found
                self.pkgrecv(self.surl, "--key {noexist} --cert {cert} "
                    "-d {dst} --dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Dst key not found
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {noexist} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Src certificate is empty file
                self.pkgrecv(self.surl, "--key {key} --cert {empty} "
                    "-d {dst} --dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Dst certificate is empty file
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {dkey} --dcert {empty} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Src key is empty file
                self.pkgrecv(self.surl, "--key {empty} --cert {cert} "
                    "-d {dst} --dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)

                # Dst key is empty file
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {empty} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), exit=1)
                
                # No permissions to read src certificate 
                self.pkgrecv(self.surl, "--key {key} --cert {verboten} "
                    "-d {dst} --dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), su_wrap=True, exit=1)

                # No permissions to read dst certificate 
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {dkey} --dcert {verboten} "
                    "{pkg}".format(**arg_dict), su_wrap=True, exit=1)

                # No permissions to read src key 
                self.pkgrecv(self.surl, "--key {verboten} --cert {cert} "
                    "-d {dst} --dkey {dkey} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), su_wrap=True, exit=1)

                # No permissions to read dst key 
                self.pkgrecv(self.surl, "--key {key} --cert {cert} "
                    "-d {dst} --dkey {verboten} --dcert {dcert} "
                    "{pkg}".format(**arg_dict), su_wrap=True, exit=1)


if __name__ == "__main__":
        unittest.main()
