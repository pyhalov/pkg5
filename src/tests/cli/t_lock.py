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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.fmri as fmri
import pkg.nrlock as nrlock
import unittest


class TestPkgApi(pkg5unittest.SingleDepotTestCase):
        # restart the depot for every test
        persistent_depot = False

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            close """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11))
                self.image_create(self.rurl)

        def test_api_locking(self):
                """Verify that a locked image cannot be modified if it is
                already locked and that the API will raise an appropriate
                exception."""

                # Get an image object and tests its manual lock mechanism.
                api_obj = self.get_img_api_obj()
                img = api_obj.img

                # Verify a lock file is created and is not zero size.
                img.lock()
                lfpath = os.path.join(img.imgdir, "lock")
                self.assertTrue(os.path.exists(lfpath))
                self.assertNotEqual(os.stat(lfpath).st_size, 0)

                # Verify attempting to re-lock when locked fails.
                self.assertRaises(nrlock.NRLockException, img.lock)

                # Verify lock file still exists on failure.
                self.assertTrue(os.path.exists(lfpath))

                # Verify that an API function will fail the same way.
                self.assertRaises(nrlock.NRLockException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_install(*args, **kwargs)),
                    ["foo"])
                api_obj.reset()

                # Now verify that after unlocking the image that it will work.
                img.unlock()

                # Verify that after unlock, lock file still exists, but is
                # zero size.
                self.assertTrue(os.path.exists(lfpath))
                self.assertEqual(os.stat(lfpath).st_size, 0)

                for pd in api_obj.gen_plan_install(["foo"]):
                        continue
                api_obj.reset()

                # Verify that if a state change occurs at any point after
                # planning before a plan successfully executes, that an
                # InvalidPlanError will be raised.
                api_obj2 = self.get_img_api_obj()

                # Both of these should succeed since no state change exists yet.
                for pd in api_obj.gen_plan_install(["foo"]):
                        continue
                for pd in api_obj2.gen_plan_install(["foo"]):
                        continue

                # Execute the first plan.
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

                # Now verify preparing second plan fails since first has changed
                # the image state.
                self.assertRaises(api_errors.InvalidPlanError, api_obj2.prepare)

                # Restart plan process.
                api_obj2.reset()
                for pd in api_obj2.gen_plan_uninstall(["foo"]):
                        continue
                for pd in api_obj.gen_plan_uninstall(["foo"]):
                        continue

                # Prepare second and first plan.
                api_obj2.prepare()
                api_obj.prepare()

                # Execute second plan, which should mean that the first can't
                # execute due to state change since plan was created.
                api_obj2.execute_plan()
                self.assertRaises(api_errors.InvalidPlanError,
                    api_obj.execute_plan)

        def test_process_locking(self):
                """Verify that image locking works across processes."""

                # Get an image object and tests its manual lock mechanism.
                api_obj = self.get_img_api_obj()
                img = api_obj.img

                # Verify a lock file is created.
                img.lock()
                lfpath = os.path.join(img.imgdir, "lock")
                self.assertTrue(os.path.exists(lfpath))

                # Verify attempting to re-lock when lock fails.
                self.assertRaises(nrlock.NRLockException, img.lock)

                # Verify that the pkg process will fail if the image is locked.
                self.pkg("install foo", exit=7)

                # Now verify that after unlocking the image that it will work.
                img.unlock()
                self.pkg("install foo")

                # Now plan an uninstall using the API object.
                api_obj.reset()
                for pd in api_obj.gen_plan_uninstall(["foo"]):
                        continue
                api_obj.prepare()

                # Execute the client to actually uninstall the package, and then
                # attempt to execute the plan which should fail since the image
                # state has changed since the plan was created.
                self.pkg("uninstall foo")
                self.assertRaises(api_errors.InvalidPlanError,
                    api_obj.execute_plan)

        def test_symlink_lock(self):
                """Verify that if a install/refresh operation is performed
                on lock file, the lock file is not a symlink."""

                # Get an image object and tests its manual lock mechanism.
                api_obj = self.get_img_api_obj()
                img = api_obj.img

                # Verify a lock file is created.
                img.lock()
                lfpath = os.path.join(img.imgdir, "lock")
                self.assertTrue(os.path.exists(lfpath))
                img.unlock()
                os.remove(lfpath)

                # Make lock file a symlink by pointing it to a random file .
                tmp_file = os.path.join(img.imgdir, "test_symlink")
                fo = open(tmp_file, 'wb+')
                fo.close()
                os.symlink(tmp_file, lfpath)

                # Verify that both pkg install and refresh generate an error
                # if the lock file is a symlink.
                self.pkg("install foo", su_wrap=True, exit=1)
                self.assertTrue("contains a symlink" in self.errout)

                self.pkg("refresh --full", su_wrap=True, exit=1)
                self.assertTrue("contains a symlink" in self.errout)

# Vim hints
# vim:ts=8:sw=8:et:fdm=marker
