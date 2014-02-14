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

# Copyright (c) 2008, 2013, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import shutil
import unittest

import pkg.actions as actions
import pkg.fmri as fmri

class TestPkgInfoBasics(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        bronze10 = """
            open bronze@1.0,5.11-0:20110908T004546Z
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add license tmp/copyright1 license=copyright
            close
        """

        bronze05 = """
            open bronze@0.5,5.11-0:20110908T004546Z
            add license tmp/copyright0 license=copyright
            close
        """

        badfile10 = """
            open badfile@1.0,5.11-0
            add file tmp/baz mode=644 owner=root group=bin path=/tmp/baz-file
            close
        """

        baddir10 = """
            open baddir@1.0,5.11-0
            add dir mode=755 owner=root group=bin path=/tmp/baz-dir
            close
        """

        human = """
            open human@0.9.8.18,5.11-0:20110908T004546Z
            add set name=pkg.human-version value=0.9.8r
            close
        """

        human2 = """
            open human2@0.9.8.18,5.11-0:20110908T004546Z
            add set name=pkg.human-version value=0.9.8.18
            close
        """

        misc_files = [ "tmp/bronzeA1",  "tmp/bronzeA2", "tmp/bronze1",
            "tmp/bronze2", "tmp/copyright1", "tmp/copyright0", "tmp/sh",
            "tmp/baz"]

        def __check_qoutput(self, errout=False):
                self.assertEqualDiff(self.output, "")
                if errout:
                        self.assert_(self.errout != "",
                            "-q must print fatal errors!")
                else:
                        self.assert_(self.errout == "",
                            "-q should only print fatal errors!")

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.plist = self.pkgsend_bulk(self.rurl, (self.badfile10,
                    self.baddir10, self.bronze10, self.bronze05, self.human,
                    self.human2))

        def test_pkg_info_bad_fmri(self):
                """Test bad frmi's with pkg info."""

                pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    close
                """
                self.pkgsend_bulk(self.rurl, pkg1)
                self.image_create(self.rurl)

                self.pkg("info foo@x.y", exit=1)
                # Should only print fatal errors when using -q.
                self.pkg("info -q foo@x.y", exit=1)
                self.__check_qoutput(errout=True)
                self.pkg("info pkg:/man@0.5.11,5.11-0.95:20080807T160129",
                    exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-0.95:20080807T1", exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-0.95:", exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-0.", exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-", exit=1)
                self.pkg("info pkg:/man@0.5.11,-", exit=1)
                self.pkg("info pkg:/man@-", exit=1)
                self.pkg("info pkg:/man@", exit=1)

                # Bug 4878
                self.pkg("info -r _usr/bin/stunnel", exit=1)
                self.pkg("info _usr/bin/stunnel", exit=1)

		# bad version
                self.pkg("install jade")
                self.pkg("info pkg:/foo@bar.baz", exit=1)
                self.pkg("info pkg:/foo@bar.baz jade", exit=1)
                self.pkg("info -r pkg:/foo@bar.baz", exit=1)

		# bad time
                self.pkg("info pkg:/foo@0.5.11,5.11-0.91:20080613T999999Z",
                    exit=1)

        def test_info_empty_image(self):
                """local pkg info should fail in an empty image; remote
                should succeed on a match """

                self.image_create(self.rurl)
                self.pkg("info", exit=1)

        def test_info_local_remote(self):
                """pkg: check that info behaves for local and remote cases."""

                pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video"
                    close
                """

                pkg2 = """
                    open turquoise@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value=org.opensolaris.category.2008:System/Security/Foo/bar/Baz
                    add set pkg.description="Short desc"
                    close
                """

                pkg3 = """
                    open copper@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set pkg.description="This package constrains package versions to those for build 123.  WARNING: Proper system update and correct package selection depend on the presence of this incorporation.  Removing this package will result in an unsupported system."
                    close
                """

                # This unit test needs an actual depot due to unprivileged user
                # testing.
                self.dc.start()
                plist = self.pkgsend_bulk(self.durl, (pkg1, pkg2, pkg3))
                self.image_create(self.durl)

                # Install one package and verify
                self.pkg("install jade")
                self.pkg("verify -v")

                # Check local info
                self.pkg("info jade | grep 'State: Installed'")
                self.pkg("info jade | grep '      Category: Applications/Sound and Video'")
                self.pkg("info jade | grep '      Category: Applications/Sound and Video (org.opensolaris.category.2008)'", exit=1)
                self.pkg("info jade | grep 'Description:'", exit=1)
                self.pkg("info turquoise 2>&1 | grep 'no packages matching'")
                self.pkg("info emerald", exit=1)
                self.pkg("info emerald 2>&1 | grep 'no packages matching'")
                self.pkg("info 'j*'")
                self.pkg("info '*a*'")
                self.pkg("info jade", su_wrap=True)
                # Should only print fatal errors when using -q.
                self.pkg("info -q jade")
                self.__check_qoutput(errout=False)

                # Check remote info
                self.pkg("info -r jade | grep 'State: Installed'")
                self.pkg("info -r jade | grep '      Category: Applications/Sound and Video'")
                self.pkg("info -r jade | grep '      Category: Applications/Sound and Video (org.opensolaris.category.2008)'", exit=1)
                self.pkg("info -r turquoise | grep 'State: Not installed'")
                self.pkg("info -r turquoise | grep '      Category: System/Security/Foo/bar/Baz'")
                self.pkg("info -r turquoise | grep '      Category: System/Security/Foo/bar/Baz (org.opensolaris.category.2008)'", exit=1)
                self.pkg("info -r turquoise | grep '   Description: Short desc'")
                # Should only print fatal errors when using -q.
                self.pkg("info -qr turquoise")
                self.__check_qoutput(errout=False)
                self.pkg("info -r turquoise")

                # Now remove the manifest for turquoise and retry the info -r
                # for an unprivileged user.
                mdir = os.path.dirname(self.get_img_manifest_path(
                    fmri.PkgFmri(plist[1])))
                shutil.rmtree(mdir)
                self.assertFalse(os.path.exists(mdir))
                self.pkg("info -r turquoise", su_wrap=True)

                # Verify output.
                lines = self.output.split("\n")
                self.assertEqual(lines[2], "   Description: Short desc")
                self.assertEqual(lines[3],
                    "      Category: System/Security/Foo/bar/Baz")
                self.pkg("info -r copper")
                lines = self.output.split("\n")
                self.assertEqual(lines[2],
                   "   Description: This package constrains package versions to those for build 123.")

                self.assertEqual(lines[3], "                WARNING: Proper system update and correct package selection")
                self.assertEqual(lines[4], "                depend on the presence of this incorporation.  Removing this")
                self.assertEqual(lines[5], "                package will result in an unsupported system.")
                self.assertEqual(lines[6], "         State: Not installed")
                # Should only print fatal errors when using -q.
                self.pkg("info -qr turquoise")
                self.__check_qoutput(errout=False)
                # Now check for an unknown remote package.
                self.pkg("info -r emerald", exit=1)
                self.pkg("info -r emerald 2>&1 | grep 'no packages matching'")
                # Should only print fatal errors when using -q.
                self.pkg("info -qr emerald", exit=1)
                self.__check_qoutput(errout=False)

                self.dc.stop()

        def test_bug_2274(self):
                """Verify that a failure to retrieve license information, for
                one or more packages specified, will result in an exit code of
                1 (complete failure) or 3 (partial failure) and a printed
                message.
                """

                pkg1 = """
                    open silver@1.0,5.11-0
                    close
                """

                self.pkgsend_bulk(self.rurl, pkg1)
                self.image_create(self.rurl)
                self.pkg("info --license -r bronze")
                self.pkg("info --license -r silver", exit=1)
                # Should only print fatal errors when using -q.
                self.pkg("info --license -qr silver", exit=1)
                self.__check_qoutput(errout=False)
                self.pkg("info --license -r bronze silver", exit=3)
                self.pkg("info --license -r silver 2>&1 | grep 'no license information'")

                self.pkg("install bronze silver")

                self.pkg("info --license bronze")
                # Should only print fatal errors when using -q.
                self.pkg("info --license -q bronze")
                self.__check_qoutput(errout=False)

                self.pkg("info --license silver", exit=1)
                # Should only print fatal errors when using -q.
                self.pkg("info --license -q silver", exit=1)
                self.__check_qoutput(errout=False)

                self.pkg("info --license bronze silver", exit=3)
                # Should only print fatal errors when using -q.
                self.pkg("info --license -q bronze silver", exit=3)
                self.__check_qoutput(errout=False)

                self.pkg("info --license silver 2>&1 | grep 'no license information'")

        def test_info_bad_packages(self):
                """Verify that pkg info handles packages with invalid
                metadata."""

                self.image_create(self.rurl)

                # Verify that no packages are installed.
                self.pkg("list", exit=1)
                plist = self.plist[:2]

                # This should succeed and cause the manifests to be cached.
                self.pkg("info -r %s" % " ".join(p for p in plist))

                # Now attempt to corrupt the client's copy of the manifest by
                # adding malformed actions.
                for p in plist:
                        self.debug("Testing package %s ..." % p)
                        pfmri = fmri.PkgFmri(p)
                        mdata = self.get_img_manifest(pfmri)
                        if mdata.find("dir") != -1:
                                src_mode = "mode=755"
                        else:
                                src_mode = "mode=644"

                        for bad_act in (
                            'set name=description value="" \" my desc \" ""',
                            "set name=com.sun.service.escalations value="):
                                self.debug("Testing with bad action "
                                    "'%s'." % bad_act)
                                bad_mdata = mdata + "%s\n" % bad_act
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("info -r %s" % pfmri.pkg_name, exit=0)

        def test_human_version(self):
                """Verify that info returns the expected output for packages
                with a human-readable version defined. If it is the same as
                version number, then only version number is displayed"""

                self.image_create(self.rurl)
                self.pkg("info -r human | grep 'Version: 0.9.8.18 (0.9.8r)'")

                # Verify that human version number should not be displayed
                # if it is identical to the version number.
                self.pkg("info -r human2 | grep 'Version: 0.9.8.18$'")

        def test_ranked(self):
                """Verify that pkg info -r returns expected results when
                multiple publishers provide the same package based on
                publisher search order."""

		# because we compare date strings we must run this in
		# a consistent locale, which we made 'C'

		os.environ['LC_ALL'] = 'C'

                # Create an isolated repository for this test
                repodir = os.path.join(self.test_root, "test-ranked")
                self.create_repo(repodir)
                self.pkgrepo("add-publisher -s %s test" % repodir)
                self.pkgsend_bulk(repodir, (self.bronze10, self.human))

                self.pkgrepo("add-publisher -s %s test2" % repodir)
                self.pkgrepo("set -s %s publisher/prefix=test2" % repodir)
                self.pkgsend_bulk(repodir, self.bronze10)

                self.pkgrepo("add-publisher -s %s test3" % repodir)
                self.pkgrepo("set -s %s publisher/prefix=test3" % repodir)
                self.pkgsend_bulk(repodir, self.bronze10)

                # Create a test image.
                self.image_create()
                self.pkg("set-publisher -p %s" % repodir)

                # Test should be higher ranked than test2 since the default
                # for auto-configuration is to use lexical order when
                # multiple publishers are found.  As such, info -r should
                # return results for 'test' by default.
                self.pkg("info -r bronze human")
                expected = """\
 Name: bronze
 Summary: 
 State: Not installed
 Publisher: test
 Version: 1.0
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test/bronze@1.0-0:20110908T004546Z

 Name: human
 Summary: 
 State: Not installed
 Publisher: test
 Version: 0.9.8.18 (0.9.8r)
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 0.00 B
 FMRI: pkg://test/human@0.9.8.18-0:20110908T004546Z
"""
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))

                # Verify that if the publisher is specified, that is preferred
                # over rank.
                self.pkg("info -r //test2/bronze")
                expected = """\
 Name: bronze
 Summary: 
 State: Not installed
 Publisher: test2
 Version: 1.0
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test2/bronze@1.0-0:20110908T004546Z
"""
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))

                # Verify that if stem is specified with and without publisher,
                # both matches are listed if the higher-ranked publisher differs
                # from the publisher specified.
                self.pkg("info -r //test/bronze bronze")
                expected = """\
 Name: bronze
 Summary: 
 State: Not installed
 Publisher: test
 Version: 1.0
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test/bronze@1.0-0:20110908T004546Z
"""
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))

                self.pkg("info -r //test2/bronze bronze")
                expected = """\
 Name: bronze
 Summary: 
 State: Not installed
 Publisher: test
 Version: 1.0
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test/bronze@1.0-0:20110908T004546Z

 Name: bronze
 Summary: 
 State: Not installed
 Publisher: test2
 Version: 1.0
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test2/bronze@1.0-0:20110908T004546Z
"""
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))

                self.pkg("info -r //test3/bronze //test2/bronze bronze")
                expected = """\
 Name: bronze
 Summary: 
 State: Not installed
 Publisher: test
 Version: 1.0
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test/bronze@1.0-0:20110908T004546Z

 Name: bronze
 Summary: 
 State: Not installed
 Publisher: test2
 Version: 1.0
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test2/bronze@1.0-0:20110908T004546Z

 Name: bronze
 Summary: 
 State: Not installed
 Publisher: test3
 Version: 1.0
 Branch: 0
Packaging Date: Thu Sep 08 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test3/bronze@1.0-0:20110908T004546Z
"""
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))

        def test_renamed_packages(self):
                """Verify that info returns the expected output for renamed
                packages."""

		# because we compare date strings we must run this in
		# a consistent locale, which we made 'C'

		os.environ['LC_ALL'] = 'C'

                target10 = """
                    open target@1.0
                    close
                """

                # Renamed package for all variants, with correct dependencies.
                ren_correct10 = """
                    open ren_correct@1.0
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=target@1.0 variant.cat=bobcat
                    add depend type=require fmri=target@1.0 variant.cat=lynx
                    close
                """

                # Renamed package for other variant, with dependencies only for
                # for other variant.
                ren_op_variant10 = """
                    open ren_op_variant@1.0
                    add set name=pkg.renamed value=true variant.cat=lynx
                    add depend type=require fmri=target@1.0 variant.cat=lynx
                    close
                """

                # Renamed package for current image variant, with dependencies
                # only for other variant.
                ren_variant_missing10 = """
                    open ren_variant_missing@1.0
                    add set name=pkg.renamed value=true variant.cat=bobcat
                    add depend type=require fmri=target@1.0 variant.cat=lynx
                    close
                """

                # Renamed package for multiple variants, with dependencies
                # missing for one variant.
                ren_partial_variant10 = """
                    open ren_partial_variant@1.0
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=target@1.0 variant.cat=lynx
                    close
                """

                plist = self.pkgsend_bulk(self.rurl, (target10, ren_correct10,
                    ren_op_variant10, ren_variant_missing10,
                    ren_partial_variant10))

                # Create an image.
                variants = { "variant.cat": "bobcat" }
                self.image_create(self.rurl, variants=variants)

                # First, verify that a renamed package (for all variants), and
                # with the correct dependencies will provide the expected info.
                self.pkg("info -r ren_correct")
                actual = self.output
                pfmri = fmri.PkgFmri(plist[1])
                pkg_date = pfmri.version.get_timestamp().strftime("%c")
                expected = """\
          Name: ren_correct
       Summary: 
         State: Not installed (Renamed)
    Renamed to: target@1.0
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: %(pkg_date)s
          Size: 0.00 B
          FMRI: %(pkg_fmri)s
""" % { "pkg_date": pkg_date, "pkg_fmri": pfmri.get_fmri(include_build=False) }
                self.assertEqualDiff(expected, actual)

                # Next, verify that a renamed package (for a variant not
                # applicable to this image), and with dependencies that
                # are only for that other variant will provide the expected
                # info.  Ensure package isn't seen as renamed for current
                # variant.
                self.pkg("info -r ren_op_variant")
                actual = self.output
                pfmri = fmri.PkgFmri(plist[2])
                pkg_date = pfmri.version.get_timestamp().strftime("%c")
                expected = """\
          Name: ren_op_variant
       Summary: 
         State: Not installed
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: %(pkg_date)s
          Size: 0.00 B
          FMRI: %(pkg_fmri)s
""" % { "pkg_date": pkg_date, "pkg_fmri": pfmri.get_fmri(include_build=False) }
                self.assertEqualDiff(expected, actual)

                # Next, verify that a renamed package (for a variant applicable
                # to this image), and with dependencies that are only for that
                # other variant will provide the expected info.
                self.pkg("info -r ren_variant_missing")
                actual = self.output
                pfmri = fmri.PkgFmri(plist[3])
                pkg_date = pfmri.version.get_timestamp().strftime("%c")
                expected = """\
          Name: ren_variant_missing
       Summary: 
         State: Not installed (Renamed)
    Renamed to: 
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: %(pkg_date)s
          Size: 0.00 B
          FMRI: %(pkg_fmri)s
""" % { "pkg_date": pkg_date, "pkg_fmri": pfmri.get_fmri(include_build=False) }
                self.assertEqualDiff(expected, actual)


                # Next, verify that a renamed package (for all variants),
                # but that is missing a dependency for the current variant
                # will provide the expected info.
                self.pkg("info -r ren_partial_variant")
                actual = self.output
                pfmri = fmri.PkgFmri(plist[4])
                pkg_date = pfmri.version.get_timestamp().strftime("%c")
                expected = """\
          Name: ren_partial_variant
       Summary: 
         State: Not installed (Renamed)
    Renamed to: 
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: %(pkg_date)s
          Size: 0.00 B
          FMRI: %(pkg_fmri)s
""" % { "pkg_date": pkg_date, "pkg_fmri": pfmri.get_fmri(include_build=False) }
                self.assertEqualDiff(expected, actual)

        def test_appropriate_license_files(self):
                """Verify that the correct license file is displayed."""

                self.image_create(self.rurl)

                self.pkg("info -r --license bronze")
                self.assertEqual("tmp/copyright1\n", self.output)
                self.pkg("info -r --license bronze@0.5")
                self.assertEqual("tmp/copyright0\n", self.output)

                self.pkg("install --licenses bronze@0.5")
                self.assert_("tmp/copyright0" in self.output, "Expected "
                    "tmp/copyright0 to be in the output of the install. Output "
                    "was:\n%s" % self.output)
                self.pkg("info -l --license bronze")
                self.assertEqual("tmp/copyright0\n", self.output)
                self.pkg("info -r --license bronze")
                self.assertEqual("tmp/copyright1\n", self.output)
                self.pkg("info -r --license bronze@1.0")
                self.assertEqual("tmp/copyright1\n", self.output)

                self.pkg("update --licenses bronze@1.0")
                self.assert_("tmp/copyright1" in self.output, "Expected "
                    "tmp/copyright1 to be in the output of the install. Output "
                    "was:\n%s" % self.output)
                self.pkg("info -r --license bronze")
                self.assertEqual("tmp/copyright1\n", self.output)
                self.pkg("info -l --license bronze")
                self.assertEqual("tmp/copyright1\n", self.output)
                self.pkg("info -r --license bronze@0.5")
                self.assertEqual("tmp/copyright0\n", self.output)


class TestPkgInfoPerTestRepo(pkg5unittest.SingleDepotTestCase):
        """A separate test class is needed because these tests modify packages
        after they've been published and need to avoid corrupting packages for
        other tests."""

        persistent_setup = False

        bronze10 = """
            open bronze@1.0,5.11-0:20110908T004546Z
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add license tmp/copyright1 license=copyright
            close
        """

        misc_files = [ "tmp/bronzeA1", "tmp/bronze1", "tmp/bronze2", "tmp/cat",
            "tmp/copyright1", "tmp/sh"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.plist = self.pkgsend_bulk(self.rurl, (self.bronze10))

        def __mangle_license(self, fmri):
                repo = self.dc.get_repo()
                m_path = repo.manifest(fmri)
                with open(m_path, "rb") as fh:
                        fmri_lines = fh.readlines()
                with open(m_path, "wb") as fh:
                        a = None
                        for l in fmri_lines:
                                if "license=copyright" in l:
                                        continue
                                elif "path=etc/bronze1" in l:
                                        a = actions.fromstr(l)
                                fh.write(l)
                        self.assert_(a)
                        l = """\
license %(hash)s license=foo chash=%(chash)s pkg.csize=%(csize)s \
pkg.size=%(size)s""" % {
    "hash":a.hash,
    "chash":a.attrs["chash"],
    "csize":a.attrs["pkg.csize"],
    "size":a.attrs["pkg.size"]
}
                        fh.write(l)
                repo.rebuild()

        def test_info_installed_changed_manifest(self):
                """Test that if an installed manifest has changed in the
                repository the original manifest is used for pkg info and info
                -r."""

                self.image_create(self.rurl)
                self.pkg("install bronze")

                self.pkg("info --license bronze")
                self.assert_("tmp/copyright1" in self.output)
                self.__mangle_license(self.plist[0])

                self.pkg("refresh --full")

                self.pkg("info --license bronze")
                self.assert_("tmp/bronze1" not in self.output)
                self.assert_("tmp/copyright1" in self.output)

                self.pkg("info -r --license bronze")
                self.assert_("tmp/bronze1" not in self.output)
                self.assert_("tmp/copyright1" in self.output)

        def test_info_uninstalled_changed_manifest(self):
                """Test that if an uninstalled manifest has changed in the
                repository but is cached locally, that the changed manifest is
                reflected in info -r."""

                # First test remote retrieval.
                self.image_create(self.rurl)

                self.pkg("info -r  --license bronze")
                self.assert_("tmp/copyright1" in self.output)
                self.__mangle_license(self.plist[0])
                self.pkg("refresh --full")

                self.pkg("info -r  --license bronze")
                self.assert_("tmp/bronze1" in self.output)
                self.assert_("tmp/copyright1" not in self.output)


if __name__ == "__main__":
        unittest.main()
