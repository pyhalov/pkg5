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

"""
Linked image module classes.

The following classes for manipulating linked images are defined here:

        LinkedImage
        LinkedImageChild

The following template classes which linked image plugins should inherit from
are also defined here:

        LinkedImagePlugin
        LinkedImageChildPlugin

"""

# standard python classes
import collections
import copy
import operator
import os
import select
import simplejson as json

# pkg classes
import pkg.actions
import pkg.altroot as ar
import pkg.catalog
import pkg.client.api_errors as apx
import pkg.client.bootenv as bootenv
import pkg.client.linkedimage
import pkg.client.pkgdefs as pkgdefs
import pkg.client.pkgplan as pkgplan
import pkg.client.pkgremote
import pkg.client.progress as progress
import pkg.facet
import pkg.fmri
import pkg.misc as misc
import pkg.pkgsubprocess
import pkg.version

from pkg.client import global_settings

logger = global_settings.logger

# linked image relationship types (returned by LinkedImage.list_related())
REL_PARENT = "parent"
REL_SELF   = "self"
REL_CHILD  = "child"

# linked image properties
PROP_NAME           = "li-name"
PROP_ALTROOT        = "li-altroot"
PROP_PARENT_PATH    = "li-parent"
PROP_PATH           = "li-path"
PROP_MODEL          = "li-model"
PROP_RECURSE        = "li-recurse"
prop_values         = frozenset([
    PROP_ALTROOT,
    PROP_NAME,
    PROP_PATH,
    PROP_MODEL,
    PROP_PARENT_PATH,
    PROP_RECURSE,
])

# properties that never get saved
temporal_props = frozenset([
    PROP_ALTROOT,
])

# special linked image name values (PROP_NAME)
PV_NAME_NONE = "-"

# linked image model values (PROP_MODEL)
PV_MODEL_PUSH = "push"
PV_MODEL_PULL = "pull"
model_values = frozenset([
    PV_MODEL_PUSH,
    PV_MODEL_PULL,
])

# files which contain linked image data
__DATA_DIR     = "linked"
PATH_PFACETS    = os.path.join(__DATA_DIR, "linked_pfacets")
PATH_PPKGS     = os.path.join(__DATA_DIR, "linked_ppkgs")
PATH_PROP      = os.path.join(__DATA_DIR, "linked_prop")
PATH_PUBS      = os.path.join(__DATA_DIR, "linked_ppubs")

LI_RVTuple = collections.namedtuple("LI_RVTuple", "rvt_rv rvt_e rvt_p_dict")

def _li_rvtuple_check(rvtuple):
        """Sanity check a linked image operation return value tuple.
        The format of said tuple is:
                process return code
                LinkedImageException exception (optional)
                json dictionary containing planned image changes
        """

        # make sure we're using the LI_RVTuple class
        assert type(rvtuple) == LI_RVTuple

        # decode the tuple
        rv, e, p_dict = rvtuple

        # rv must be an integer
        assert type(rv) == int
        # any exception returned must be a LinkedImageException
        assert e is None or type(e) == apx.LinkedImageException
        # if specified, p_dict must be a dictionary
        assert p_dict is None or type(p_dict) is dict
        # some child return codes should never be associated with an exception
        assert rv not in [pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP] or e is None
        # a p_dict can only be returned if the child returned EXIT_OK
        assert rv == pkgdefs.EXIT_OK or p_dict is None

        # return the value that was passed in
        return rvtuple

def _li_rvdict_check(rvdict):
        """Given a linked image return value dictionary, sanity check all the
        entries."""

        assert(type(rvdict) == dict)
        for k, v in rvdict.iteritems():
                assert type(k) == LinkedImageName, \
                    ("Unexpected rvdict key: ", k)
                _li_rvtuple_check(v)

        # return the value that was passed in
        return rvdict

def _li_rvdict_exceptions(rvdict):
        """Given a linked image return value dictionary, return a list of any
        exceptions that were encountered while processing children."""

        # sanity check rvdict
        _li_rvdict_check(rvdict)

        # get a list of exceptions
        return [
            rvtuple.rvt_e
            for rvtuple in rvdict.values()
            if rvtuple.rvt_e is not None
        ]

def _li_rvdict_raise_exceptions(rvdict):
        """If an exception was encountered while operating on a linked
        child then raise that exception.  If multiple exceptions were
        encountered while operating on multiple children, then bundle
        those exceptions together and raise them."""

        # get a list of exceptions
        exceptions = _li_rvdict_exceptions(rvdict)

        if len(exceptions) == 1:
                # one exception encountered
                raise exceptions[0]

        if exceptions:
                # multiple exceptions encountered
                raise apx.LinkedImageException(bundle=exceptions)

class LinkedImagePlugin(object):
        """This class is a template that all linked image plugins should
        inherit from.  Linked image plugins derived from this class are
        designed to manage linked aspects of the current image (vs managing
        linked aspects of a specific child of the current image).

        All the interfaces exported by this class and its descendants are
        private to the linked image subsystem and should not be called
        directly by any other subsystem."""

        # functionality flags
        support_attach = False
        support_detach = False

        # Unused argument; pylint: disable=W0613
        def __init__(self, pname, linked):
                """Initialize a linked image plugin.

                'pname' is the name of the plugin class derived from this
                base class.

                'linked' is the LinkedImage object initializing this plugin.
                """

                return

        def init_root(self, old_altroot):
                """Called when the path to the image that we're operating on
                is changing.  This normally occurs when we clone an image
                after we've planned and prepared to do an operation."""

                # return value: None
                raise NotImplementedError

        def get_altroot(self, ignore_errors=False):
                """If the linked image plugin is able to detect that we're
                operating on an image in an alternate root then return the
                path of the alternate root."""

                # return value: string or None
                raise NotImplementedError

        def get_child_list(self, nocache=False, ignore_errors=False):
                """Return a list of the child images associated with the
                current image."""

                # return value: list
                raise NotImplementedError

        def get_child_props(self, lin):
                """Get the linked image properties associated with the
                specified child image."""

                # return value: dict
                raise NotImplementedError

        def attach_child_inmemory(self, props, allow_relink):
                """Attach the specified child image. This operation should
                only affect in-memory state of the current image. It should
                not update any persistent on-disk linked image state or access
                the child image in any way. This routine should assume that
                the linked image properties have already been validated."""

                # return value: None
                raise NotImplementedError

        def detach_child_inmemory(self, lin):
                """Detach the specified child image. This operation should
                only affect in-memory state of the current image. It should
                not update any persistent on-disk linked image state or access
                the child image in any way."""

                # return value: None
                raise NotImplementedError

        def sync_children_todisk(self):
                """Sync out the in-memory linked image state of this image to
                disk."""

                # return value: LI_RVTuple()
                raise NotImplementedError


class LinkedImageChildPlugin(object):
        """This class is a template that all linked image child plugins should
        inherit from.  Linked image child plugins derived from this class are
        designed to manage linked aspects of children of the current image.
        (vs managing linked aspects of the current image itself).

        All the interfaces exported by this class and its descendants are
        private to the linked image subsystem and should not be called
        directly by any other subsystem."""

        def __init__(self, lic): # Unused argument; pylint: disable=W0613
                """Initialize a linked image child plugin.

                'lic' is the LinkedImageChild object initializing this plugin.
                """

                return

        def munge_props(self, props):
                """Called before a parent image saves linked image properties
                into a child image.  Gives the linked image child plugin a
                chance to update the properties that will be saved within the
                child image."""

                # return value: None
                raise NotImplementedError


class LinkedImageName(object):
        """A class for naming child linked images.  Linked image names are
        used for all child images (and only child images), and they encode two
        pieces of information.  The name of the plugin used to manage the
        image and a linked image name.  Linked image names have the following
        format "<linked_image_plugin>:<linked_image_name>"""

        def __init__(self, name):
                assert type(name) == str

                self.lin_type = self.lin_name = None

                try:
                        self.lin_type, self.lin_name = name.split(":")
                except ValueError:
                        raise apx.LinkedImageException(lin_malformed=name)

                if len(self.lin_type) == 0 or len(self.lin_name) == 0 :
                        raise apx.LinkedImageException(lin_malformed=name)

                if self.lin_type not in pkg.client.linkedimage.p_types:
                        raise apx.LinkedImageException(lin_malformed=name)

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""
                # Unused argument; pylint: disable=W0613
                return str(obj)

        @staticmethod
        def fromstate(state, jd_state=None):
                """Allocate a new object using previously serialized state
                obtained via getstate()."""
                # Unused argument; pylint: disable=W0613
                return LinkedImageName(state)

        def __str__(self):
                return "%s:%s" % (self.lin_type, self.lin_name)

        def __len__(self):
                return len(self.__str__())

        def __cmp__(self, other):
                assert (type(self) == LinkedImageName)
                if not other:
                        return 1
                if other == PV_NAME_NONE:
                        return 1
                assert type(other) == LinkedImageName
                c = cmp(self.lin_type, other.lin_type)
                if c != 0:
                        return c
                c = cmp(self.lin_name, other.lin_name)
                return c

        def __hash__(self):
                return hash(str(self))

        def __eq__(self, other):
                if not isinstance(other, LinkedImageName):
                        return False

                return str(self) == str(other)

        def __ne__(self, other):
                return not self.__eq__(other)

class LinkedImage(object):
        """A LinkedImage object is used to manage the linked image aspects of
        an image.  This image could be a child image, a parent image, or both
        a parent and child.  This object allows for access to linked image
        properties and also provides routines that allow operations to be
        performed on child images."""

        # Properties that a parent image with push children should save locally.
        __parent_props = frozenset([
            PROP_PATH
        ])

        # Properties that a pull child image should save locally.
        __pull_child_props = frozenset([
            PROP_NAME,
            PROP_PATH,
            PROP_MODEL,
            PROP_PARENT_PATH,
        ])

        # Properties that a parent image with push children should save in
        # those children.
        __push_child_props = frozenset([
            PROP_NAME,
            PROP_PATH,
            PROP_MODEL,
            PROP_RECURSE,
        ])

        # make sure there is no invalid overlap
        assert not (temporal_props & (
            __parent_props |
            __pull_child_props |
            __push_child_props))

        def __init__(self, img):
                """Initialize a new LinkedImage object."""

                # globals
                self.__img = img

                # variables reset by self.__update_props()
                self.__props = dict()
                self.__ppkgs = frozenset()
                self.__ppubs = None
                self.__pfacets = pkg.facet.Facets()
                self.__pimg = None

                # variables reset by self.__recursion_init()
                self.__lic_ignore = None
                self.__lic_dict = {}

                # variables reset by self._init_root()
                self.__root = None
                self.__path_ppkgs = None
                self.__path_prop = None
                self.__path_ppubs = None
                self.__path_pfacets = None
                self.__img_insync = True

                # initialize with no properties
                self.__update_props()

                # initialize linked image plugin objects
                self.__plugins = dict()
                for p in pkg.client.linkedimage.p_types:
                        self.__plugins[p] = \
                            pkg.client.linkedimage.p_classes[p](p, self)

                # if the image has a path setup, we can load data from it.
                if self.__img.imgdir:
                        self._init_root()

        @property
        def image(self):
                """Get a pointer to the image object associated with this
                linked image object."""
                return self.__img

        def _init_root(self):
                """Called during object initialization and by
                image.py`__set_root() to let us know when we're changing the
                root location of the image.  (The only time we change the root
                path is when changes BEs during operations which clone BEs.
                So when this happens most our metadata shouldn't actually
                change."""

                assert self.__img.root, \
                    "root = %s" % str(self.__img.root)
                assert self.__img.imgdir, \
                    "imgdir = %s" % str(self.__img.imgdir)

                # save the old root image path
                old_root = None
                if self.__root:
                        old_root = self.__root

                # figure out the new root image path
                new_root = self.__img.root.rstrip(os.sep)
                if new_root == "":
                        new_root = os.sep

                # initialize paths for linked image data files
                self.__root = new_root
                imgdir = self.__img.imgdir.rstrip(os.sep)
                self.__path_ppkgs = os.path.join(imgdir, PATH_PPKGS)
                self.__path_prop = os.path.join(imgdir, PATH_PROP)
                self.__path_ppubs = os.path.join(imgdir, PATH_PUBS)
                self.__path_pfacets = os.path.join(imgdir, PATH_PFACETS)

                # if this isn't a reset, then load data from the image
                if not old_root:
                        # the first time around we load non-temporary data (if
                        # there is any) so that we can audit ourselves and see
                        # if we're in currently in sync.
                        self.__load(tmp=False)
                        if self.ischild():
                                self.__img_insync = self.__insync()

                        # now re-load all the data taking into account any
                        # temporary new data associated with an in-progress
                        # operation.
                        self.__load()

                # we're not linked or we're not changing root paths we're done
                if not old_root or not self.__props:
                        return

                # get the old altroot directory
                old_altroot = self.altroot()

                # update the altroot property
                self.__set_altroot(self.__props, old_root=old_root)

                # Tell linked image plugins about the updated paths
                # Unused variable 'plugin'; pylint: disable=W0612
                for plugin, lip in self.__plugins.iteritems():
                # pylint: enable=W0612
                        lip.init_root(old_altroot)

                # Tell linked image children about the updated paths
                for lic in self.__lic_dict.itervalues():
                        lic.child_init_root(old_altroot)

        def __update_props(self, props=None):
                """Internal helper routine used when we want to update any
                linked image properties.  This routine sanity check the
                new properties, updates them, and resets any cached state
                that is affected by property values."""

                if props == None:
                        props = dict()
                elif props:
                        self.__verify_props(props)

                        # all temporal properties must exist
                        assert (temporal_props - set(props)) == set(), \
                            "%s - %s == set()" % (temporal_props, set(props))

                # update state
                self.__props = props
                self.__ppkgs = frozenset()
                self.__ppubs = None
                self.__pfacets = pkg.facet.Facets()
                self.__pimg = None

        def __verify_props(self, props):
                """Perform internal consistency checks for a set of linked
                image properties.  Don't update any state."""

                props_set = set(props)

                # if we're not a child image ourselves, then we're done
                if (props_set - temporal_props) == self.__parent_props:
                        return props

                # make sure PROP_MODEL was specified
                if PROP_NAME not in props:
                        _rterr(path=self.__root,
                            missing_props=[PROP_NAME])

                # validate the linked image name
                try:
                        lin = LinkedImageName(str(props[PROP_NAME]))
                except apx.LinkedImageException:
                        _rterr(path=self.__root,
                            bad_prop=(PROP_NAME, props[PROP_NAME]))

                if lin.lin_type not in self.__plugins:
                        _rterr(path=self.__root, lin=lin,
                            bad_lin_type=lin.lin_type)

                # make sure PROP_MODEL was specified
                if PROP_MODEL not in props:
                        _rterr(path=self.__root, lin=lin,
                            missing_props=[PROP_MODEL])

                model = props[PROP_MODEL]
                if model not in model_values:
                        _rterr(path=self.__root, lin=lin,
                            bad_prop=(PROP_MODEL, model))

                if model == PV_MODEL_PUSH:
                        missing = self.__push_child_props - props_set
                        if missing:
                                _rterr(path=self.__root, lin=lin,
                                    missing_props=missing)

                if model == PV_MODEL_PULL:
                        missing = self.__pull_child_props - props_set
                        if missing:
                                _rterr(path=self.__root, lin=lin,
                                    missing_props=missing)

        @staticmethod
        def __unset_altroot(props):
                """Given a set of linked image properties, strip out any
                altroot properties.  This involves removing the altroot
                component from the image path property.  This is normally done
                before we write image properties to disk."""

                # get the current altroot
                altroot = props[PROP_ALTROOT]

                # remove it from the image path
                props[PROP_PATH] = rm_altroot_path(
                    props[PROP_PATH], altroot)

                if PROP_PARENT_PATH in props:
                        # remove it from the parent image path
                        props[PROP_PARENT_PATH] = rm_altroot_path(
                            props[PROP_PARENT_PATH], altroot)

                # delete the current altroot
                del props[PROP_ALTROOT]

        def __set_altroot(self, props, old_root=None):
                """Given a set of linked image properties, the image paths
                stored within those properties may not match the actual image
                paths if we're executing within an alternate root environment.
                We try to detect this condition here, and if this situation
                occurs we update the linked image paths to reflect the current
                image paths and we fabricate a new linked image altroot
                property that points to the new path prefix that was
                pre-pended to the image paths."""

                # we may have to update the parent image path as well
                p_path = None
                if PROP_PARENT_PATH in props:
                        p_path = props[PROP_PARENT_PATH]

                if old_root:
                        # get the old altroot
                        altroot = props[PROP_ALTROOT]

                        # remove the altroot from the image paths
                        path = rm_altroot_path(old_root, altroot)
                        if p_path:
                                p_path = rm_altroot_path(p_path, altroot)

                        # get the new altroot
                        altroot = get_altroot_path(self.__root, path)
                else:
                        path = props[PROP_PATH]
                        altroot = get_altroot_path(self.__root, path)

                # update properties with altroot
                props[PROP_ALTROOT] = altroot
                props[PROP_PATH] = add_altroot_path(path, altroot)
                if p_path:
                        props[PROP_PARENT_PATH] = \
                            add_altroot_path(p_path, altroot)

        def __guess_altroot(self, ignore_errors=False):
                """If we're initializing parent linked image properties for
                the first time (or if those properties somehow got deleted)
                then we need to know if the parent image that we're currently
                operating on is located within an alternate root.  One way to
                do this is to ask our linked image plugins if they can
                determine this (the zones linked image plugin usually can
                if the image is a global zone)."""

                # ask each plugin if we're operating in an alternate root
                p_altroots = []
                for plugin, lip in self.__plugins.iteritems():
                        p_altroot = lip.get_altroot(
                            ignore_errors=ignore_errors)
                        if p_altroot:
                                p_altroots.append((plugin, p_altroot))

                if not p_altroots:
                        # no altroot suggested by plugins
                        return os.sep

                # check for conflicting altroots
                altroots = list(set([
                        p_altroot
                        # Unused variable; pylint: disable=W0612
                        for pname, p_altroot in p_altroots
                        # pylint: enable=W0612
                ]))

                if len(altroots) == 1:
                        # we have an altroot from our plugins
                        return altroots[0]

                # we have conflicting altroots, time to die
                _rterr(li=self, multiple_altroots=p_altroots)

        def __fabricate_parent_props(self, ignore_errors=False):
                """Fabricate the minimum set of properties required for a
                parent image."""

                props = dict()
                props[PROP_PATH] = self.__img.root
                props[PROP_ALTROOT] = self.__guess_altroot(
                    ignore_errors=ignore_errors)
                return props

        def __load_ondisk_props(self, tmp=True):
                """Load linked image properties from disk and return them to
                the caller.  We sanity check the properties, but we don't
                update any internal linked image state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                path = self.__path_prop
                path_tmp = "%s.%d" % (self.__path_prop,
                    global_settings.client_runid)

                # read the linked image properties from disk
                if tmp and path_exists(path_tmp):
                        path = path_tmp
                        props = load_data(path)
                elif path_exists(path):
                        props = load_data(path)
                else:
                        return None

                # make sure there are no saved temporal properties
                assert not (set(props) & temporal_props)

                if PROP_NAME in props:
                        # convert PROP_NAME into a linked image name obj
                        name = props[PROP_NAME]
                        try:
                                lin = LinkedImageName(name)
                                props[PROP_NAME] = lin
                        except apx.LinkedImageException:
                                _rterr(path=self.__root,
                                    bad_prop=(PROP_NAME, name))

                # sanity check our properties
                self.__verify_props(props)
                return props

        def __load_ondisk_pfacets(self, tmp=True):
                """Load linked image inherited facets from disk.
                Don't update any internal state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                pfacets = misc.EmptyDict
                path = "%s.%d" % (self.__path_pfacets,
                    global_settings.client_runid)
                if tmp and path_exists(path):
                        pfacets = load_data(path)
                else:
                        path = self.__path_pfacets
                        pfacets = load_data(path, missing_ok=True)

                if pfacets is None:
                        return None

                rv = pkg.facet.Facets()
                for k, v in pfacets.iteritems():
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        rv._set_inherited(k, v)
                return rv

        def __load_ondisk_ppkgs(self, tmp=True):
                """Load linked image parent packages from disk.
                Don't update any internal state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                fmri_strs = None
                path = "%s.%d" % (self.__path_ppkgs,
                    global_settings.client_runid)
                if tmp and path_exists(path):
                        fmri_strs = load_data(path)
                else:
                        path = self.__path_ppkgs
                        fmri_strs = load_data(path, missing_ok=True)

                if fmri_strs is None:
                        return None

                return frozenset([
                    pkg.fmri.PkgFmri(str(s))
                    for s in fmri_strs
                ])

        def __load_ondisk_ppubs(self, tmp=True):
                """Load linked image parent publishers from disk.
                Don't update any internal state.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                ppubs = None
                path = "%s.%d" % (self.__path_ppubs,
                    global_settings.client_runid)
                if tmp and path_exists(path):
                        ppubs = load_data(path)
                else:
                        path = self.__path_ppubs
                        ppubs = load_data(path, missing_ok=True)

                return ppubs

        def __load(self, tmp=True):
                """Load linked image properties and constraints from disk.
                Update the linked image internal state with the loaded data."""

                #
                # Normally, if we're a parent image we'll have linked image
                # properties stored on disk.  So load those now.
                #
                # If no properties are loaded, we may still be a parent image
                # that is just missing it's metadata.  (oops.)  We attempt to
                # detect this situation by invoking __isparent(), which will
                # ask each child if there are any children.  This is a best
                # effort attempt, so when we do this we ignore any plugin
                # runtime errors since we really want Image object
                # initialization to succeed.  If we don't have any linked
                # image metadata, and we're having runtime errors querying for
                # children, then we'll allow initialization here, but any
                # subsequent operation that tries to access children will fail
                # and the caller will have to specify that they want to ignore
                # all children to allow the operation to succeed.
                #
                props = self.__load_ondisk_props(tmp=tmp)
                if not props and not self.__isparent(ignore_errors=True):
                        # we're not linked
                        return

                if not props:
                        #
                        # Oops.  We're a parent image with no properties
                        # stored on disk.  Rather than throwing an exception
                        # try to fabricate up some props with reasonably
                        # guessed values which the user can subsequently
                        # change and/or fix.
                        #
                        props = self.__fabricate_parent_props(
                            ignore_errors=True)
                else:
                        self.__set_altroot(props)

                self.__update_props(props)

                if not self.ischild():
                        return

                # load parent packages. if parent package data is missing just
                # continue along and hope for the best.
                ppkgs = self.__load_ondisk_ppkgs(tmp=tmp)
                if ppkgs is not None:
                        self.__ppkgs = ppkgs

                # load inherited facets. if inherited facet data is missing
                # just continue along and hope for the best.
                pfacets = self.__load_ondisk_pfacets(tmp=tmp)
                if pfacets is not None:
                        self.__pfacets = pfacets

                # load parent publisher data. if publisher data is missing
                # continue along and we'll just skip the publisher checks,
                # it's better than failing and preventing any image updates.
                self.__ppubs = self.__load_ondisk_ppubs(tmp=tmp)

        @staticmethod
        def __validate_prop_recurse(v):
                """Verify property value for PROP_RECURSE."""
                if v in [True, False]:
                        return True
                if type(v) == str and v.lower() in ["true", "false"]:
                        return True
                return False

        def __validate_attach_props(self, model, props):
                """Validate user supplied linked image attach properties.
                Don't update any internal state."""

                # make sure that only attach time options have been
                # specified, and that they have allowed values.
                validate_props = {
                        PROP_RECURSE: self.__validate_prop_recurse
                }

                if model == PV_MODEL_PUSH:
                        allowed_props = self.__push_child_props
                else:
                        assert model == PV_MODEL_PULL
                        allowed_props = self.__pull_child_props

                errs = []

                # check each property the user specified.
                for k, v in props.iteritems():

                        # did the user specify an allowable property?
                        if k not in validate_props:
                                errs.append(apx.LinkedImageException(
                                    attach_bad_prop=k))
                                continue

                        # did the user specify a valid property value?
                        if not validate_props[k](v):
                                errs.append(apx.LinkedImageException(
                                    attach_bad_prop_value=(k, v)))
                                continue

                        # is this property valid for this type of image?
                        if k not in allowed_props:
                                errs.append(apx.LinkedImageException(
                                    attach_bad_prop=k))
                                continue

                if len(errs) == 1:
                        raise errs[0]
                if errs:
                        raise apx.LinkedImageException(bundle=errs)

        def __init_pimg(self, path):
                """Initialize an Image object which can be used to access a
                parent image."""

                try:
                        os.stat(path)
                except OSError:
                        raise apx.LinkedImageException(parent_bad_path=path)

                try:
                        pimg = self.__img.alloc(
                            root=path,
                            user_provided_dir=True,
                            cmdpath=self.__img.cmdpath)
                except apx.ImageNotFoundException:
                        raise apx.LinkedImageException(parent_bad_img=path)

                return pimg

        def altroot(self):
                """Return the altroot path prefix for the current image."""

                return self.__props.get(PROP_ALTROOT, os.sep)

        def nothingtodo(self):
                """If our in-memory linked image state matches the on-disk
                linked image state then there's nothing to do.  If the state
                differs then there is stuff to do since the new state needs
                to be saved to disk."""

                # check if we're not a linked image.
                if not self.isparent() and not self.ischild():
                        # if any linked image metadata files exist they need
                        # to be deleted.
                        paths = [
                            self.__path_pfacets,
                            self.__path_ppkgs,
                            self.__path_ppubs,
                            self.__path_prop,
                        ]
                        for path in paths:
                                if path_exists(path):
                                        return False
                        return True

                # compare in-memory and on-disk properties
                li_ondisk_props = self.__load_ondisk_props(tmp=False)
                if li_ondisk_props == None:
                        li_ondisk_props = dict()
                li_inmemory_props = self.__props.copy()
                if li_inmemory_props:
                        self.__unset_altroot(li_inmemory_props)
                li_inmemory_props = rm_dict_ent(li_inmemory_props,
                    temporal_props)
                if li_ondisk_props != li_inmemory_props:
                        return False

                # linked image metadata files with inherited data
                paths = [
                    self.__path_pfacets,
                    self.__path_ppkgs,
                    self.__path_ppubs,
                ]

                # check if we're just a parent image.
                if not self.ischild():
                        # parent images only have properties.  if any linked
                        # image metadata files that contain inherited
                        # information exist they need to be deleted.
                        for path in paths:
                                if path_exists(path):
                                        return False
                        return True

                # if we're missing any metadata files then there's work todo
                for path in paths:
                        if not path_exists(path):
                                return False

                # compare in-memory and on-disk inherited facets
                li_ondisk_pfacets = self.__load_ondisk_pfacets(tmp=False)
                if self.__pfacets != li_ondisk_pfacets:
                        return False

                # compare in-memory and on-disk parent packages
                li_ondisk_ppkgs = self.__load_ondisk_ppkgs(tmp=False)
                if self.__ppkgs != li_ondisk_ppkgs:
                        return False

                # compare in-memory and on-disk parent publishers
                li_ondisk_ppubs = self.__load_ondisk_ppubs(tmp=False)
                if self.__ppubs != li_ondisk_ppubs:
                        return False

                return True

        def pubcheck(self):
                """If we're a child image's, verify that the parent image
                publisher configuration is a subset of the child images
                publisher configuration.  This means that all publishers
                configured within the parent image must also be configured
                within the child image with the same:

                        - publisher rank
                        - sticky and disabled settings

                The child image may have additional publishers configured but
                they must all be lower ranked than the parent's publishers.
                """

                # if we're not a child image then bail
                if not self.ischild():
                        return

                # if we're using the sysrepo then don't bother
                if self.__img.cfg.get_policy("use-system-repo"):
                        return

                pubs = get_pubs(self.__img)
                ppubs = self.__ppubs

                if ppubs == None:
                        # parent publisher data is missing, press on and hope
                        # for the best.
                        return

                # child image needs at least as many publishers as the parent
                if len(pubs) < len(ppubs):
                        raise apx.PlanCreationException(
                            linked_pub_error=(pubs, ppubs))

                # check rank, sticky, and disabled settings
                for (p, pp) in zip(pubs, ppubs):
                        if p == pp:
                                continue
                        raise apx.PlanCreationException(
                            linked_pub_error=(pubs, ppubs))

        def __syncmd_from_parent(self):
                """Update linked image constraint, publisher data, and
                state from our parent image."""

                if not self.ischild():
                        # we're not a child image, nothing to do
                        return

                if self.__props[PROP_MODEL] == PV_MODEL_PUSH:
                        # parent pushes data to us, nothing to do
                        return

                # initialize the parent image
                if not self.__pimg:
                        path = self.__props[PROP_PARENT_PATH]
                        self.__pimg = self.__init_pimg(path)

                # get metadata from our parent image
                self.__ppubs = get_pubs(self.__pimg)
                self.__ppkgs = get_packages(self.__pimg)
                self.__pfacets = get_inheritable_facets(self.__pimg)

        def syncmd_from_parent(self, catch_exception=False):
                """Update linked image constraint, publisher data, and state
                from our parent image.  If catch_exception is true catch any
                linked image exceptions and pack them up in a linked image
                return value tuple."""

                try:
                        self.__syncmd_from_parent()
                except apx.LinkedImageException, e:
                        if not catch_exception:
                                raise e
                        return LI_RVTuple(e.lix_exitrv, e, None)
                return

        def syncmd(self):
                """Write in-memory linked image state to disk."""

                # create a list of metadata file paths
                paths = [
                    self.__path_pfacets,
                    self.__path_ppkgs,
                    self.__path_ppubs,
                    self.__path_prop,
                ]

                # cleanup any temporary files
                for path in paths:
                        path = "%s.%d" % (path,
                            global_settings.client_runid)
                        path_unlink(path, noent_ok=True)

                if not self.ischild() and not self.isparent():
                        # we're no longer linked; delete metadata
                        for path in paths:
                                path_unlink(path, noent_ok=True)
                        return

                # save our properties, but first remove altroot path prefixes
                # and any temporal properties
                props = self.__props.copy()
                self.__unset_altroot(props)
                props = rm_dict_ent(props, temporal_props)
                save_data(self.__path_prop, props)

                if not self.ischild():
                        # if we're not a child we don't have parent data
                        path_unlink(self.__path_pfacets, noent_ok=True)
                        path_unlink(self.__path_ppkgs, noent_ok=True)
                        path_unlink(self.__path_ppubs, noent_ok=True)
                        return

                # we're a child so save our latest constraints
                save_data(self.__path_pfacets, self.__pfacets)
                save_data(self.__path_ppkgs, self.__ppkgs)
                save_data(self.__path_ppubs, self.__ppubs)

        @property
        def child_name(self):
                """If the current image is a child image, this function
                returns a linked image name object which represents the name
                of the current image."""

                if not self.ischild():
                        raise self.__apx_not_child()
                return self.__props[PROP_NAME]

        def ischild(self):
                """Indicates whether the current image is a child image."""

                return PROP_NAME in self.__props

        def __isparent(self, ignore_errors=False):
                """Indicates whether the current image is a parent image.

                'ignore_plugin_errors' ignore plugin runtime errors when
                trying to determine if we're a parent image.
                """

                return len(self.__list_children(
                    ignore_errors=ignore_errors)) > 0

        def isparent(self, li_ignore=None):
                """Indicates whether the current image is a parent image."""

                return len(self.__list_children(li_ignore=li_ignore)) > 0

        def child_props(self, lin=None):
                """Return a dictionary which represents the linked image
                properties associated with a linked image.

                'lin' is the name of the child image.  If lin is None then
                the current image is assumed to be a linked image and it's
                properties are returned.

                Always returns a copy of the properties in case the caller
                tries to update them."""

                if lin == None:
                        # If we're not linked we'll return an empty
                        # dictionary.  That's ok.
                        return self.__props.copy()

                # make sure the specified child exists
                self.__verify_child_name(lin, raise_except=True)

                # make a copy of the props in case they are updated
                lip = self.__plugins[lin.lin_type]
                props = lip.get_child_props(lin).copy()

                # add temporal properties
                props[PROP_ALTROOT] = self.altroot()
                return props

        def __apx_not_child(self):
                """Raise an exception because the current image is not a child
                image."""

                return apx.LinkedImageException(self_not_child=self.__root)

        def __verify_child_name(self, lin, raise_except=False):
                """Check if a specific child image exists."""

                assert type(lin) == LinkedImageName, \
                    "%s == LinkedImageName" % type(lin)

                for i in self.__list_children():
                        if i[0] == lin:
                                return True

                if raise_except:
                        raise apx.LinkedImageException(child_unknown=lin)
                return False

        def verify_names(self, lin_list):
                """Given a list of linked image name objects, make sure all
                the children exist."""

                assert isinstance(lin_list, list), \
                    "type(lin_list) == %s, str(lin_list) == %s" % \
                    (type(lin_list), str(lin_list))

                for lin in lin_list:
                        self.__verify_child_name(lin, raise_except=True)

        def inherited_facets(self):
                """Facets inherited from our parent image."""
                return self.__pfacets

        def parent_fmris(self):
                """A set of the fmris installed in our parent image."""

                if not self.ischild():
                        # We return None since frozenset() would indicate
                        # that there are no packages installed in the parent
                        # image.
                        return None

                return self.__ppkgs

        def parse_name(self, name, allow_unknown=False):
                """Given a string representing a linked image child name,
                returns linked image name object representing the same name.

                'allow_unknown' indicates whether the name must represent
                actual children or simply be syntactically correct."""

                assert type(name) == str

                lin = LinkedImageName(name)
                if not allow_unknown:
                        self.__verify_child_name(lin, raise_except=True)
                return lin

        def __list_children(self, li_ignore=None, ignore_errors=False):
                """Returns a list of linked child images associated with the
                current image.

                'li_ignore' see list_related() for a description.

                The returned value is a list of tuples where each tuple
                contains (<li name>, <li path>)."""

                if li_ignore == []:
                        # ignore all children
                        return []

                li_children = [
                    entry
                    for p in pkg.client.linkedimage.p_types
                    for entry in self.__plugins[p].get_child_list(
                        ignore_errors=ignore_errors)
                ]

                # sort by linked image name
                li_children = sorted(li_children, key=operator.itemgetter(0))

                if li_ignore == None:
                        # don't ignore any children
                        return li_children

                li_all = set([lin for lin, path in li_children])
                errs = [
                    apx.LinkedImageException(child_unknown=lin)
                    for lin in (set(li_ignore) - li_all)
                ]
                if len(errs) == 1:
                        raise errs[0]
                if errs:
                        raise apx.LinkedImageException(bundle=errs)

                return [
                    (lin, path)
                    for lin, path in li_children
                    if lin not in li_ignore
                ]

        def list_related(self, li_ignore=None):
                """Returns a list of linked images associated with the
                current image.  This includes both child and parent images.

                'li_ignore' is either None or a list.  If it's None (the
                default), all children will be listed.  If it's an empty list
                no children will be listed.  Otherwise, any children listed
                in li_ignore will be ommited from the results.

                The returned value is a list of tuples where each tuple
                contains (<li name>, <relationship>, <li path>)."""

                li_children = self.__list_children(li_ignore=li_ignore)
                li_list = [
                    (lin, REL_CHILD, path)
                    for lin, path in li_children
                ]

                if not li_list and not self.ischild():
                        # we're not linked
                        return []

                # we're linked so append ourself to the list
                lin = PV_NAME_NONE
                if self.ischild():
                        lin = self.child_name
                li_self = (lin, REL_SELF, self.__props[PROP_PATH])
                li_list.append(li_self)

                # if we have a path to our parent then append that as well.
                if PROP_PARENT_PATH in self.__props:
                        li_parent = (PV_NAME_NONE, REL_PARENT,
                            self.__props[PROP_PARENT_PATH])
                        li_list.append(li_parent)

                # sort by linked image name
                li_list = sorted(li_list, key=operator.itemgetter(0))

                return li_list

        def attach_parent(self, lin, path, props, allow_relink=False,
            force=False):
                """We only update in-memory state; nothing is written to
                disk, to sync linked image state to disk call syncmd."""

                assert type(lin) == LinkedImageName
                assert type(path) == str
                assert props == None or type(props) == dict, \
                    "type(props) == %s" % type(props)
                if props == None:
                        props = dict()

                lip = self.__plugins[lin.lin_type]

                if self.ischild() and not allow_relink:
                        raise apx.LinkedImageException(self_linked=self.__root)

                if not lip.support_attach and not force:
                        raise apx.LinkedImageException(
                            attach_parent_notsup=lin.lin_type)

                # Path must be an absolute path.
                if not os.path.isabs(path):
                        raise apx.LinkedImageException(parent_path_notabs=path)

                # we don't bother to cleanup the path to the parent image here
                # because when we allocate an Image object for the parent
                # image, it will do that work for us.
                pimg = self.__init_pimg(path)

                # make sure we're not linking to ourselves
                if self.__img.root == pimg.root:
                        raise apx.LinkedImageException(link_to_self=True)

                # make sure we're not linking the root image as a child
                if self.__img.root == misc.liveroot():
                        raise apx.LinkedImageException(
                            attach_root_as_child=True)

                # get the cleaned up parent image path.
                path = pimg.root

                # If we're in an alternate root, the parent must also be within
                # that alternate root.
                if not check_altroot_path(path, self.altroot()):
                        raise apx.LinkedImageException(
                            parent_not_in_altroot=(path, self.altroot()))

                self.__validate_attach_props(PV_MODEL_PULL, props)

                # make a copy of the properties
                props = props.copy()
                props[PROP_NAME] = lin
                props[PROP_PARENT_PATH] = path
                props[PROP_PATH] = self.__img.root
                props[PROP_MODEL] = PV_MODEL_PULL
                props[PROP_ALTROOT] = self.altroot()

                for k, v in lip.attach_props_def.iteritems():
                        if k not in self.__pull_child_props:
                                # this prop doesn't apply to pull images
                                continue
                        if k not in props:
                                props[k] = v

                self.__update_props(props)
                self.__pimg = pimg

        def detach_parent(self, force=False):
                """We only update in memory state; nothing is written to
                disk, to sync linked image state to disk call syncmd."""

                lin = self.child_name
                lip = self.__plugins[lin.lin_type]
                if not force:
                        if self.__props[PROP_MODEL] == PV_MODEL_PUSH:
                                raise apx.LinkedImageException(
                                    detach_from_parent=self.__root)

                        if not lip.support_detach:
                                raise apx.LinkedImageException(
                                    detach_parent_notsup=lin.lin_type)

                # Generate a new set of linked image properties.  If we have
                # no children then we don't need any more properties.
                props = None

                # If we have children we'll need to keep some properties.
                if self.isparent():
                        strip = prop_values - \
                            (self.__parent_props | temporal_props)
                        props = rm_dict_ent(self.__props, strip)

                # Update our linked image properties.
                self.__update_props(props)

        def __insync(self):
                """Determine if an image is in sync with its constraints."""

                assert self.ischild()

                cat = self.__img.get_catalog(self.__img.IMG_CATALOG_INSTALLED)
                excludes = [ self.__img.cfg.variants.allow_action ]

                sync_fmris = []

                for fmri in cat.fmris():
                        # get parent dependencies from the catalog
                        parent_deps = [
                            a
                            for a in cat.get_entry_actions(fmri,
                                [pkg.catalog.Catalog.DEPENDENCY],
                                excludes=excludes)
                            if a.name == "depend" and \
                                a.attrs["type"] == "parent"
                        ]

                        if parent_deps:
                                sync_fmris.append(fmri)

                if not sync_fmris:
                        # No packages to sync
                        return True

                # create a dictionary of packages installed in the parent
                ppkgs_dict = dict([
                        (fmri.pkg_name, fmri)
                        for fmri in self.parent_fmris()
                ])

                for fmri in sync_fmris:
                        if fmri.pkg_name not in ppkgs_dict:
                                return False
                        pfmri = ppkgs_dict[fmri.pkg_name]
                        if fmri.version != pfmri.version and \
                            not pfmri.version.is_successor(fmri.version,
                                pkg.version.CONSTRAINT_AUTO):
                                return False
                return True

        def audit_self(self, latest_md=True):
                """If the current image is a child image, this function
                audits the current image to see if it's in sync with its
                parent."""

                if not self.ischild():
                        e = self.__apx_not_child()
                        return LI_RVTuple(pkgdefs.EXIT_OOPS, e, None)

                if not latest_md:
                        # we don't use the latest linked image metadata.
                        # instead return cached insync value which was
                        # computed using the initial linked image metadata
                        # that we loaded from disk.
                        if not self.__img_insync:
                                e = apx.LinkedImageException(
                                    child_diverged=self.child_name)
                                return LI_RVTuple(pkgdefs.EXIT_DIVERGED, e,
                                    None)
                        return LI_RVTuple(pkgdefs.EXIT_OK, None, None)

                if not self.__insync():
                        e = apx.LinkedImageException(
                            child_diverged=self.child_name)
                        return LI_RVTuple(pkgdefs.EXIT_DIVERGED, e, None)

                return LI_RVTuple(pkgdefs.EXIT_OK, None, None)

        def insync(self, latest_md=True):
                """A convenience wrapper for audit_self().  Note that we
                consider non-child images as always in sync and ignore
                any runtime errors."""

                rv = self.image.linked.audit_self(latest_md=latest_md)[0]
                if rv == pkgdefs.EXIT_DIVERGED:
                        return False
                return True

        @staticmethod
        def __rvdict2rv(rvdict, rv_map=None):
                """Internal helper function that takes a dictionary returned
                from an operations on multiple children and merges the results
                into a single return code."""

                _li_rvdict_check(rvdict)
                if type(rv_map) != type(None):
                        assert type(rv_map) == list
                        for (rv_set, rv) in rv_map:
                                assert(type(rv_set) == set)
                                assert(type(rv) == int)

                if not rvdict:
                        return LI_RVTuple(pkgdefs.EXIT_OK, None, None)

                if not rv_map:
                        rv_map = [(set([pkgdefs.EXIT_OK]), pkgdefs.EXIT_OK)]

                p_dicts = [
                    rvtuple.rvt_p_dict
                    for rvtuple in rvdict.itervalues()
                    if rvtuple.rvt_p_dict is not None
                ]

                rv_mapped = set()
                rv_seen = set([
                    rvtuple.rvt_rv
                    for rvtuple in rvdict.itervalues()
                ])
                for (rv_map_set, rv_map_rv) in rv_map:
                        if (rv_seen == rv_map_set):
                                return LI_RVTuple(rv_map_rv, None, p_dicts)
                        # keep track of all the return values that are mapped
                        rv_mapped |= rv_map_set

                # the mappings better have included pkgdefs.EXIT_OK
                assert pkgdefs.EXIT_OK in rv_mapped

                # if we had errors for unmapped return values, bundle them up
                errs = [
                        rvtuple.rvt_e
                        for rvtuple in rvdict.itervalues()
                        if rvtuple.rvt_e and rvtuple.rvt_rv not in rv_mapped
                ]
                if len(errs) == 1:
                        err = errs[0]
                elif errs:
                        err = apx.LinkedImageException(bundle=errs)
                else:
                        err = None

                if len(rv_seen) == 1:
                        # we have one consistent return value
                        return LI_RVTuple(list(rv_seen)[0], err, p_dicts)

                return LI_RVTuple(pkgdefs.EXIT_PARTIAL, err, p_dicts)

        def audit_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                rv_map = [
                    (set([pkgdefs.EXIT_OK]), pkgdefs.EXIT_OK),
                    (set([pkgdefs.EXIT_DIVERGED]), pkgdefs.EXIT_DIVERGED),
                    (set([pkgdefs.EXIT_OK, pkgdefs.EXIT_DIVERGED]),
                        pkgdefs.EXIT_DIVERGED),
                ]
                return self.__rvdict2rv(rvdict, rv_map)

        def sync_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                rv_map = [
                    (set([pkgdefs.EXIT_OK]), pkgdefs.EXIT_OK),
                    (set([pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP]), pkgdefs.EXIT_OK),
                    (set([pkgdefs.EXIT_NOP]), pkgdefs.EXIT_NOP),
                ]
                return self.__rvdict2rv(rvdict, rv_map)

        def detach_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                return self.__rvdict2rv(rvdict)

        def __validate_child_attach(self, lin, path, props,
            allow_relink=False):
                """Sanity check the parameters associated with a child image
                that we are trying to attach."""

                assert type(lin) == LinkedImageName
                assert type(props) == dict
                assert type(path) == str

                # check the name to make sure it doesn't already exist
                if self.__verify_child_name(lin) and not allow_relink:
                        raise apx.LinkedImageException(child_dup=lin)

                self.__validate_attach_props(PV_MODEL_PUSH, props)

                # Path must be an absolute path.
                if not os.path.isabs(path):
                        raise apx.LinkedImageException(child_path_notabs=path)

                # If we're in an alternate root, the child must also be within
                # that alternate root
                if not check_altroot_path(path, self.altroot()):
                        raise apx.LinkedImageException(
                            child_not_in_altroot=(path, self.altroot()))

                # path must be an image
                try:
                        img_prefix = ar.ar_img_prefix(path)
                except OSError:
                        raise apx.LinkedImageException(child_path_eaccess=path)
                if not img_prefix:
                        raise apx.LinkedImageException(child_bad_img=path)

                # Does the parent image (ourselves) reside in clonable BE?
                # Unused variable 'be_uuid'; pylint: disable=W0612
                (be_name, be_uuid) = bootenv.BootEnv.get_be_name(self.__root)
                # pylint: enable=W0612
                if be_name:
                        img_is_clonable = True
                else:
                        img_is_clonable = False

                # If the parent image is clonable then the new child image
                # must be nested within the parents filesystem namespace.
                path = path.rstrip(os.sep) + os.sep
                p_root = self.__root.rstrip(os.sep) + os.sep
                if img_is_clonable and not path.startswith(p_root):
                        raise apx.LinkedImageException(
                            child_not_nested=(path, p_root))

                # Find the common parent directory of the both parent and the
                # child image.
                dir_common = os.path.commonprefix([p_root, path])
                dir_common.rstrip(os.sep)

                # Make sure there are no additional images in between the
                # parent and the child. (Ie, prevent linking of images if one
                # of the images is nested within another unrelated image.)
                # This is done by looking at all the parent directories for
                # both the parent and the child image until we reach a common
                # ancestor.

                # First check the parent directories of the child.
                d = os.path.dirname(path.rstrip(os.sep))
                while d != dir_common and d.startswith(dir_common):
                        try:
                                tmp = ar.ar_img_prefix(d)
                        except OSError, e:
                                # W0212 Access to a protected member
                                # pylint: disable=W0212
                                raise apx._convert_error(e)
                        if not tmp:
                                d = os.path.dirname(d)
                                continue
                        raise apx.LinkedImageException(child_nested=(path, d))

                # Then check the parent directories of the parent.
                d = os.path.dirname(p_root.rstrip(os.sep))
                while d != dir_common and d.startswith(dir_common):
                        try:
                                tmp = ar.ar_img_prefix(d)
                        except OSError, e:
                                # W0212 Access to a protected member
                                # pylint: disable=W0212
                                raise apx._convert_error(e)
                        if not tmp:
                                d = os.path.dirname(d)
                                continue
                        raise apx.LinkedImageException(child_nested=(path, d))

                # Child image should not already be linked
                img_li_data_props = os.path.join(img_prefix, PATH_PROP)
                try:
                        exists = ar.ar_exists(path, img_li_data_props)
                except OSError, e:
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        raise apx._convert_error(e)
                if exists and not allow_relink:
                        raise apx.LinkedImageException(img_linked=path)

        def attach_child(self, lin, path, props,
            accept=False, allow_relink=False, force=False, li_md_only=False,
            li_pkg_updates=True, noexecute=False,
            progtrack=None, refresh_catalogs=True, reject_list=misc.EmptyI,
            show_licenses=False, update_index=True):
                """Attach an image as a child to the current image (the
                current image will become a parent image. This operation
                results in attempting to sync the child image with the parent
                image.

                For descriptions of parameters please see the descriptions in
                api.py`gen_plan_*"""

                assert type(lin) == LinkedImageName
                assert type(path) == str
                assert props == None or type(props) == dict, \
                    "type(props) == %s" % type(props)
                if props == None:
                        props = dict()

                lip = self.__plugins[lin.lin_type]
                if not lip.support_attach and not force:
                        e = apx.LinkedImageException(
                            attach_child_notsup=lin.lin_type)
                        return LI_RVTuple(e.lix_exitrv, e, None)

                # Path must be an absolute path.
                if not os.path.isabs(path):
                        e = apx.LinkedImageException(child_path_notabs=path)
                        return LI_RVTuple(e.lix_exitrv, e, None)

                # cleanup specified path
                cwd = os.getcwd()
                try:
                        os.chdir(path)
                except OSError, e:
                        e = apx.LinkedImageException(child_path_eaccess=path)
                        return LI_RVTuple(e.lix_exitrv, e, None)
                path = os.getcwd()
                os.chdir(cwd)

                # make sure we're not linking to ourselves
                if self.__img.root == path:
                        raise apx.LinkedImageException(link_to_self=True)

                # make sure we're not linking the root image as a child
                if path == misc.liveroot():
                        raise apx.LinkedImageException(
                            attach_root_as_child=True)

                # if the current image isn't linked yet then we need to
                # generate some linked image properties for ourselves
                if PROP_PATH not in self.__props:
                        p_props = self.__fabricate_parent_props()
                        self.__update_props(p_props)

                # sanity check the input
                try:
                        self.__validate_child_attach(lin, path, props,
                            allow_relink=allow_relink)
                except apx.LinkedImageException, e:
                        return LI_RVTuple(e.lix_exitrv, e, None)

                # make a copy of the options and start updating them
                child_props = props.copy()
                child_props[PROP_NAME] = lin
                child_props[PROP_PATH] = path
                child_props[PROP_MODEL] = PV_MODEL_PUSH
                child_props[PROP_ALTROOT] = self.altroot()

                # fill in any missing defaults options
                for k, v in lip.attach_props_def.iteritems():
                        if k not in child_props:
                                child_props[k] = v

                # attach the child in memory
                lip.attach_child_inmemory(child_props, allow_relink)

                if noexecute and li_md_only:
                        # we've validated parameters, nothing else to do
                        return LI_RVTuple(pkgdefs.EXIT_OK, None, None)

                # update the child
                try:
                        lic = LinkedImageChild(self, lin)
                except apx.LinkedImageException, e:
                        return LI_RVTuple(e.lix_exitrv, e, None)

                rvdict = {}
                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_SYNC,
                    _lic_list=[lic],
                    _rvdict=rvdict,
                    _progtrack=progtrack,
                    _failfast=False,
                    _expect_plan=True,
                    _syncmd_tmp=True,
                    accept=accept,
                    li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates,
                    noexecute=noexecute,
                    refresh_catalogs=refresh_catalogs,
                    reject_list=reject_list,
                    show_licenses=show_licenses,
                    update_index=update_index))

                rvtuple = rvdict[lin]

                if noexecute or rvtuple.rvt_rv not in [
                    pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP ]:
                        return rvtuple

                # commit child image property updates
                rvtuple2 = lip.sync_children_todisk()
                _li_rvtuple_check(rvtuple2)
                if rvtuple2.rvt_e:
                        return rvtuple2

                # save parent image properties
                self.syncmd()

                # The recursive child operation may have returned NOP, but
                # since we always update our own image metadata, we always
                # return OK.
                if rvtuple.rvt_rv == pkgdefs.EXIT_NOP:
                        return LI_RVTuple(pkgdefs.EXIT_OK, None, None)
                return rvtuple

        def audit_children(self, lin_list):
                """Audit one or more children of the current image to see if
                they are in sync with this image."""

                if lin_list == []:
                        lin_list = None

                lic_dict, rvdict = self.__children_init(lin_list=lin_list,
                    failfast=False)

                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_AUDIT_LINKED,
                    _lic_list=lic_dict.values(),
                    _rvdict=rvdict,
                    _progtrack=progress.QuietProgressTracker(),
                    _failfast=False))
                return rvdict

        def sync_children(self, lin_list, accept=False,
            li_md_only=False, li_pkg_updates=True, progtrack=None,
            noexecute=False, refresh_catalogs=True, reject_list=misc.EmptyI,
            show_licenses=False, update_index=True):
                """Sync one or more children of the current image."""

                if progtrack is None:
                        progtrack = progress.NullProgressTracker()

                if lin_list == []:
                        lin_list = None

                lic_dict = self.__children_init(lin_list=lin_list)

                _syncmd_tmp = True
                if not noexecute and li_md_only:
                        _syncmd_tmp = False

                rvdict = {}
                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_SYNC,
                    _lic_list=lic_dict.values(),
                    _rvdict=rvdict,
                    _progtrack=progtrack,
                    _failfast=False,
                    _expect_plan=True,
                    _syncmd_tmp=_syncmd_tmp,
                    accept=accept,
                    li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates,
                    noexecute=noexecute,
                    refresh_catalogs=refresh_catalogs,
                    reject_list=reject_list,
                    show_licenses=show_licenses,
                    update_index=update_index))
                return rvdict

        def detach_children(self, lin_list, force=False, noexecute=False,
            li_md_only=False, li_pkg_updates=True):
                """Detach one or more children from the current image. This
                operation results in the removal of any constraint package
                from the child images."""

                if lin_list == []:
                        lin_list = None

                lic_dict, rvdict = self.__children_init(lin_list=lin_list,
                    failfast=False)

                # check if we support detach for these children.  we don't use
                # iteritems() when walking lic_dict because we might modify
                # lic_dict.
                for lin in lic_dict:
                        lip = self.__plugins[lin.lin_type]
                        if lip.support_detach or force:
                                continue

                        # we can't detach this type of image.
                        e = apx.LinkedImageException(
                                detach_child_notsup=lin.lin_type)
                        rvdict[lin] = LI_RVTuple(e.lix_exitrv, e, None)
                        _li_rvtuple_check(rvdict[lin])
                        del lic_dict[lin]

                # do the detach
                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_DETACH,
                    _lic_list=lic_dict.values(),
                    _rvdict=rvdict,
                    _progtrack=progress.NullProgressTracker(),
                    _failfast=False,
                    li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates,
                    noexecute=noexecute))

                # if any of the children successfully detached, then we want
                # to discard our metadata for that child.
                for lin, rvtuple in rvdict.iteritems():

                        # if the detach failed leave metadata in parent
                        if rvtuple.rvt_e and not force:
                                continue

                        # detach the child in memory
                        lip = self.__plugins[lin.lin_type]
                        lip.detach_child_inmemory(lin)

                        if noexecute:
                                continue

                        # commit child image property updates
                        rvtuple2 = lip.sync_children_todisk()
                        _li_rvtuple_check(rvtuple2)

                        # don't overwrite previous errors
                        if rvtuple2.rvt_e and rvtuple.rvt_e is None:
                                rvdict[lin] = rvtuple2

                if not (self.ischild() or self.isparent()):
                        # we're not linked anymore, so delete all our linked
                        # properties.
                        self.__update_props()
                        self.syncmd()

                return rvdict

        def __children_op(self, _pkg_op, _lic_list, _rvdict, _progtrack,
            _failfast, _expect_plan=False, _ignore_syncmd_nop=True,
            _syncmd_tmp=False, _pd=None, **kwargs):
                """An iterator function which performs a linked image
                operation on multiple children in parallel.

                '_pkg_op' is the pkg.1 operation that we're going to perform

                '_lic_list' is a list of linked image child objects to perform
                the operation on.

                '_rvdict' is a dictionary, indexed by linked image name, which
                contains rvtuples of the result of the operation for each
                child.

                '_prograck' is a ProgressTracker pointer.

                '_failfast' is a boolean.  If True and we encounter a failure
                operating on a child then we raise an exception immediately.
                If False then we'll attempt to perform the operation on all
                children and rvdict will contain a LI_RVTuple result for all
                children.

                '_expect_plan' is a boolean that indicates if we expect this
                operation to generate an image plan.

                '_ignore_syncmd_nop' a boolean that indicates if we should
                always recurse into a child even if the linked image meta data
                isn't changing.

                '_syncmd_tmp' a boolean that indicates if we should write
                linked image metadata in a temporary location in child images,
                or just overwrite any existing data.

                '_pd' a PlanDescription pointer."""

                if _lic_list:
                        _progtrack.li_recurse_start(_pkg_op, len(_lic_list))

                if _pkg_op in [ pkgdefs.PKG_OP_AUDIT_LINKED,
                    pkgdefs.PKG_OP_PUBCHECK ]:
                        # these operations are cheap so ideally we'd like to
                        # use full parallelism.  but if the user specified a
                        # concurrency limit we should respect that.
                        if global_settings.client_concurrency_set:
                                concurrency = global_settings.client_concurrency
                        else:
                                # no limit was specified, use full concurrency
                                concurrency = -1
                else:
                        concurrency = global_settings.client_concurrency

                # If we have a plan for the current image that means linked
                # image metadata is probably changing so we always save it to
                # a temporary file (and we don't overwrite the existing
                # metadata until after we execute the plan).
                if _pd is not None:
                        _syncmd_tmp = True

                # get parent metadata common to all child images
                _pmd = None
                if _pkg_op != pkgdefs.PKG_OP_DETACH:
                        ppubs = get_pubs(self.__img)
                        ppkgs = get_packages(self.__img, pd=_pd)
                        pfacets = get_inheritable_facets(self.__img, pd=_pd)
                        _pmd = (ppubs, ppkgs, pfacets)

                # setup operation for each child
                lic_setup = []
                for lic in _lic_list:
                        try:
                                lic.child_op_setup(_pkg_op, _pmd, _progtrack,
                                    _ignore_syncmd_nop, _syncmd_tmp, **kwargs)
                                lic_setup.append(lic)
                        except apx.LinkedImageException, e:
                                _rvdict[lic.child_name] = \
                                    LI_RVTuple(e.lix_exitrv, e, None)

                # if _failfast is true, then throw an exception if we failed
                # to setup any of the children.  if _failfast is false we'll
                # continue to perform the operation on any children that
                # successfully initialized and we'll report setup errors along
                # with the final results for all children.
                if _failfast and _li_rvdict_exceptions(_rvdict):
                        # before we raise an exception we need to cleanup any
                        # children that we setup.
                        for lic in lic_setup:
                                lic.child_op_abort()
                        # raise an exception
                        _li_rvdict_raise_exceptions(_rvdict)

                def __child_op_finish(lic, lic_list, _pkg_op, _rvdict,
                    _progtrack, _failfast, _expect_plan):
                        """An iterator function invoked when a child has
                        finished an operation.

                        'lic' is the child that has finished execution.

                        'lic_list' a list of children to remove 'lic' from.

                        See __children_op() for an explanation of the other
                        parameters."""

                        assert lic.child_op_is_done()

                        lic_list.remove(lic)

                        rvtuple, stdout, stderr = lic.child_op_rv(_pkg_op,
                            _expect_plan)
                        _li_rvtuple_check(rvtuple)
                        _rvdict[lic.child_name] = rvtuple

                        # check if we should raise an exception
                        if _failfast and _li_rvdict_exceptions(_rvdict):

                                # we're going to raise an exception.  abort
                                # the remaining children.
                                for lic in lic_list:
                                        lic.child_op_abort()

                                # raise an exception
                                _li_rvdict_raise_exceptions(_rvdict)

                        if rvtuple.rvt_rv in [ pkgdefs.EXIT_OK,
                            pkgdefs.EXIT_NOP ]:

                                # only display child output if there was no
                                # error (otherwise the exception includes the
                                # output so we'll display it twice.)
                                _progtrack.li_recurse_output(lic.child_name,
                                    stdout, stderr)

                        # check if we should yield a plan.
                        if _expect_plan and rvtuple.rvt_rv == pkgdefs.EXIT_OK:
                                yield rvtuple.rvt_p_dict

                # check if we did everything we needed to do during child
                # setup.  (this can happen if we're just doing an implicit
                # syncmd during setup we discover the linked image metadata
                # isn't changing.)  we iterate over a copy of lic_setup to
                # allow __child_op_finish() to remove elements from lic_setup
                # while we're walking through it.
                for lic in copy.copy(lic_setup):
                        if not lic.child_op_is_done():
                                continue
                        for p_dict in __child_op_finish(lic, lic_setup,
                            _pkg_op, _rvdict, _progtrack, _failfast,
                            _expect_plan):
                                yield p_dict

                # keep track of currently running children
                lic_running = []

                # keep going as long as there are children to process
                progtrack_update = False
                while len(lic_setup) or len(lic_running):

                        while lic_setup and (
                            concurrency > len(lic_running) or
                            concurrency <= 0):
                                # start processing on a child
                                progtrack_update = True
                                lic = lic_setup.pop()
                                lic_running.append(lic)
                                lic.child_op_start()

                        if progtrack_update:
                                # display progress on children
                                progtrack_update = False
                                done = len(_lic_list) - len(lic_setup) - \
                                    len(lic_running)
                                lin_running = sorted([
                                    lic.child_name for lic in lic_running])
                                _progtrack.li_recurse_status(lin_running,
                                    done)

                        # poll on all the linked image children and see which
                        # ones have pending output.
                        fd_hash = dict([
                            (lic.fileno(), lic)
                            for lic in lic_running
                        ])
                        p = select.poll()
                        for fd in fd_hash.keys():
                                p.register(fd, select.POLLIN)
                        events = p.poll()
                        lic_list = [ fd_hash[event[0]] for event in events ]

                        for lic in lic_list:
                                _progtrack.li_recurse_progress(lic.child_name)
                                if not lic.child_op_is_done():
                                        continue
                                # a child finished processing
                                progtrack_update = True
                                for p_dict in __child_op_finish(lic,
                                    lic_running, _pkg_op, _rvdict, _progtrack,
                                    _failfast, _expect_plan):
                                        yield p_dict

                _li_rvdict_check(_rvdict)
                if _lic_list:
                        _progtrack.li_recurse_end()

        def __children_init(self, lin_list=None, li_ignore=None, failfast=True):
                """Initialize LinkedImageChild objects for children specified
                in 'lin_list'.  If 'lin_list' is not specified, then
                initialize objects for all children (excluding any being
                ignored via 'li_ignore')."""

                # you can't specify children to operate on and children to be
                # ignored at the same time
                assert lin_list is None or li_ignore is None

                # if no children we listed, build a list of children
                if lin_list is None:
                        lin_list = [
                            i[0]
                            for i in self.__list_children(li_ignore)
                        ]
                else:
                        self.verify_names(lin_list)

                rvdict = {}
                lic_dict = {}
                for lin in lin_list:
                        try:
                                lic = LinkedImageChild(self, lin)
                                lic_dict[lin] = lic
                        except apx.LinkedImageException, e:
                                rvdict[lin] = LI_RVTuple(e.lix_exitrv, e, None)

                if failfast:
                        _li_rvdict_raise_exceptions(rvdict)
                        return lic_dict

                return (lic_dict, rvdict)

        def __recursion_init(self, li_ignore):
                """Initialize child objects used during recursive packaging
                operations."""

                self.__lic_ignore = li_ignore
                self.__lic_dict = self.__children_init(li_ignore=li_ignore)

        def api_recurse_init(self, li_ignore=None, repos=None):
                """Initialize planning state.  If we're a child image we save
                our current state (which may reflect a planned state that we
                have not committed to disk) into the plan.  We also initialize
                all our children to prepare to recurse into them."""

                if PROP_RECURSE in self.__props and \
                    not self.__props[PROP_RECURSE]:
                        # we don't want to recurse
                        self.__recursion_init(li_ignore=[])
                        return

                # Initialize children
                self.__recursion_init(li_ignore)

                if not self.__lic_dict:
                        # we don't need to recurse
                        return

                # if we have any children we don't support operations using
                # temporary repositories.
                if repos:
                        raise apx.PlanCreationException(no_tmp_origins=True)

        def api_recurse_pubcheck(self, progtrack):
                """Do a recursive publisher check"""

                # get a list of of children to recurse into.
                lic_list = self.__lic_dict.values()

                # do a publisher check on all of them
                rvdict = {}
                list(self.__children_op(
                    _pkg_op=pkgdefs.PKG_OP_PUBCHECK,
                    _lic_list=lic_list,
                    _rvdict=rvdict,
                    _progtrack=progtrack,
                    _failfast=False))

                # raise an exception if one or more children failed the
                # publisher check.
                _li_rvdict_raise_exceptions(rvdict)

        def __api_recurse(self, stage, progtrack):
                """This is an iterator function.  It recurses into linked
                image children to perform the specified operation.
                """

                # get a pointer to the current image plan
                pd = self.__img.imageplan.pd

                # get a list of of children to recurse into.
                lic_list = self.__lic_dict.values()

                # sanity check stage
                assert stage in [pkgdefs.API_STAGE_PLAN,
                    pkgdefs.API_STAGE_PREPARE, pkgdefs.API_STAGE_EXECUTE]

                # if we're ignoring all children then we can't be recursing
                assert pd.children_ignored != [] or lic_list == []

                # sanity check the plan description state
                if stage == pkgdefs.API_STAGE_PLAN:
                        # the state should be uninitialized
                        assert pd.children_planned == []
                        assert pd.children_nop == []
                else:
                        # if we ignored all children, we better not have
                        # recursed into any children.
                        assert pd.children_ignored != [] or \
                            pd.children_planned == pd.children_nop == []

                        # there shouldn't be any overloap between sets of
                        # children in the plan
                        assert not (set(pd.children_planned) &
                            set(pd.children_nop))
                        if pd.children_ignored:
                                assert not (set(pd.children_ignored) &
                                    set(pd.children_planned))
                                assert not (set(pd.children_ignored) &
                                    set(pd.children_nop))

                        # make sure set of child handles matches the set of
                        # previously planned children.
                        assert set(self.__lic_dict) == set(pd.children_planned)

                # if we're in the planning stage, we should pass the current
                # image plan onto the child and also expect an image plan from
                # the child.
                expect_plan = False
                if stage == pkgdefs.API_STAGE_PLAN:
                        expect_plan = True

                # get target op and arguments
                pkg_op = pd.child_op

                # assume that for most operations we want to recurse into the
                # child image even if the linked image metadata isn't
                # changing.  (this would be required for recursive operations,
                # update operations, etc.)
                _ignore_syncmd_nop = True
                if pd.child_op_implicit:
                        # the exception is if we're doing an implicit sync.
                        # to improve performance we assume the child is
                        # already in sync, so if its linked image metadata
                        # isn't changing then the child won't need any updates
                        # so there will be no need to recurse into it.
                        _ignore_syncmd_nop = False

                rvdict = {}
                for p_dict in self.__children_op(
                    _pkg_op=pkg_op,
                    _lic_list=lic_list,
                    _rvdict=rvdict,
                    _progtrack=progtrack,
                    _failfast=True,
                    _expect_plan=expect_plan,
                    _ignore_syncmd_nop=_ignore_syncmd_nop,
                    _pd=pd,
                    stage=stage,
                    **pd.child_kwargs):
                        yield p_dict

                assert not _li_rvdict_exceptions(rvdict)

                for lin in rvdict:
                        # check for children that don't need any updates
                        if rvdict[lin].rvt_rv == pkgdefs.EXIT_NOP:
                                assert lin not in pd.children_nop
                                pd.children_nop.append(lin)
                                del self.__lic_dict[lin]

                        # record the children that are done planning
                        if stage == pkgdefs.API_STAGE_PLAN and \
                            rvdict[lin].rvt_rv == pkgdefs.EXIT_OK:
                                assert lin not in pd.children_planned
                                pd.children_planned.append(lin)

        @staticmethod
        def __recursion_op(api_op, api_kwargs):
                """Determine what pkg command to use when recursing into child
                images."""

                #
                # given the api operation being performed on the current
                # image, figure out what api operation should be performed on
                # child images.
                #
                # the recursion policy which hard coded here is that if we do
                # an pkg update in the parent image without any packages
                # specified (ie, we want to update everything) then when we
                # recurse we'll also do an update of everything.  but if we're
                # doing any other operation like install, uninstall, an update
                # of specific packages, etc, then when we recurse we'll do a
                # sync in the child.
                #
                implicit = False
                if api_op == pkgdefs.API_OP_UPDATE and not \
                    api_kwargs["pkgs_update"]:
                        pkg_op = pkgdefs.PKG_OP_UPDATE
                elif api_op == pkgdefs.API_OP_SYNC:
                        pkg_op = pkgdefs.PKG_OP_SYNC
                else:
                        pkg_op = pkgdefs.PKG_OP_SYNC
                        implicit = True
                return pkg_op, implicit

        @staticmethod
        def __recursion_args(pd, refresh_catalogs, update_index, api_kwargs):
                """Determine what pkg command arguments to use when recursing
                into child images."""

                kwargs = {}
                kwargs["noexecute"] = api_kwargs["noexecute"]
                kwargs["refresh_catalogs"] = refresh_catalogs
                kwargs["show_licenses"] = False
                kwargs["update_index"] = update_index

                #
                # when we recurse we always accept all new licenses (for now).
                #
                # ultimately (when start yielding back plan descriptions for
                # children) in addition to accepting licenses on the plan for
                # the current image the api client will also have to
                # explicitly accept licenses for all child images.  but until
                # that happens we'll just assume that the parent image license
                # space is a superset of the child image license space (and
                # since the api consumer must accept licenses in the parent
                # before we'll do anything, we'll assume licenses in the child
                # are accepted as well).
                #
                kwargs["accept"] = True

                if "li_pkg_updates" in api_kwargs:
                        # option specific to: attach, set-property-linked, sync
                        kwargs["li_pkg_updates"] = api_kwargs["li_pkg_updates"]

                if pd.child_op == pkgdefs.PKG_OP_UPDATE:
                        # skip ipkg up to date check for child images
                        kwargs["force"] = True

                return kwargs

        def api_recurse_plan(self, api_kwargs, refresh_catalogs,
            update_index, progtrack):
                """Plan child image updates."""

                pd = self.__img.imageplan.pd
                api_op = pd.plan_type

                # update the plan arguments
                pd.child_op, pd.child_op_implicit = \
                    self.__recursion_op(api_op, api_kwargs)
                pd.child_kwargs = self.__recursion_args(pd,
                    refresh_catalogs, update_index, api_kwargs)
                pd.children_ignored = self.__lic_ignore

                # recurse into children
                for p_dict in self.__api_recurse(pkgdefs.API_STAGE_PLAN,
                    progtrack):
                        yield p_dict

        def api_recurse_prepare(self, progtrack):
                """Prepare child image updates."""
                list(self.__api_recurse(pkgdefs.API_STAGE_PREPARE, progtrack))

        def api_recurse_execute(self, progtrack):
                """Execute child image updates."""
                list(self.__api_recurse(pkgdefs.API_STAGE_EXECUTE, progtrack))

        def init_plan(self, pd):
                """Initialize our state in the PlanDescription."""

                # if we're a child, save our parent package state into the
                # plan description
                pd.li_props = self.__props
                pd.li_ppkgs = self.__ppkgs
                pd.li_ppubs = self.__ppubs
                pd.li_pfacets = self.__pfacets

        def setup_plan(self, pd):
                """Reload a previously created plan."""

                # load linked image state from the plan
                self.__update_props(pd.li_props)
                self.__ppubs = pd.li_ppubs
                self.__ppkgs = pd.li_ppkgs
                self.__pfacets = pd.li_pfacets

                # now initialize our recursion state, this involves allocating
                # handles to operate on children.  we don't need handles for
                # children that were either ignored during planning, or which
                # return EXIT_NOP after planning (since these children don't
                # need any updates).
                li_ignore = copy.copy(pd.children_ignored)

                # merge the children that returned nop into li_ignore (since
                # we don't need to recurse into them).  if li_ignore is [],
                # then we ignored all children during planning
                if li_ignore != [] and pd.children_nop:
                        if li_ignore is None:
                                # no children were ignored during planning
                                li_ignore = []
                        li_ignore += pd.children_nop

                # Initialize children
                self.__recursion_init(li_ignore=li_ignore)

        def recurse_nothingtodo(self):
                """Return True if there is no planned work to do on child
                image."""

                for lic in self.__lic_dict.itervalues():
                        if lic.child_name not in \
                            self.__img.imageplan.pd.children_nop:
                                return False
                return True

        @staticmethod
        def __has_parent_dep(fmri, cat, excludes):
                """Check if a package has a parent dependency."""

                for a in cat.get_entry_actions(fmri,
                    [pkg.catalog.Catalog.DEPENDENCY], excludes=excludes):
                        if a.name == "depend" and a.attrs["type"] == "parent":
                                return True
                return False

        def extra_dep_actions(self, excludes=misc.EmptyI,
            installed_catalog=False):
                """Since we don't publish packages with parent dependencies
                yet, but we want to be able to sync packages between zones,
                we'll need to fake up some extra package parent dependencies.

                Here we'll inspect the catalog to find packages that we think
                should have parent dependencies and then we'll return a
                dictionary, indexed by fmri, which contains the extra
                dependency actions that should be added to each package."""

                # create a parent dependency action with a nonglobal zone
                # variant tag.
                attrs = dict()
                attrs["type"] = "parent"
                attrs["fmri"] = pkg.actions.depend.DEPEND_SELF
                attrs["variant.opensolaris.zone"] = "nonglobal"

                pda = pkg.actions.depend.DependencyAction(**attrs)

                if not pda.include_this(excludes):
                        # we're not operating on a nonglobal zone image so we
                        # don't need to fabricate parent zone dependencies
                        return dict()

                if not self.ischild():
                        # we're not a child image so parent dependencies are
                        # irrelevant
                        return dict()

                osnet_incorp = "consolidation/osnet/osnet-incorporation"
                ips_incorp = "consolidation/osnet/ips-incorporation"

                #
                # it's time consuming to walk the catalog looking for packages
                # to dynamically add parent dependencies too.  so to speed
                # things up we'll check if the currently installed osnet and
                # ips incorporations already have parent dependencies.  if
                # they do then this image has already been upgraded to a build
                # where these dependencies are being published so there's no
                # need for us to dynamically add them.
                #
                osnet_has_pdep = False
                ips_has_pdep = False
                cat = self.__img.get_catalog(self.__img.IMG_CATALOG_INSTALLED)
                for (ver, fmris) in cat.fmris_by_version(osnet_incorp):
                        if self.__has_parent_dep(fmris[0], cat, excludes):
                                # osnet incorporation has parent deps
                                osnet_has_pdep = True
                for (ver, fmris) in cat.fmris_by_version(ips_incorp):
                        if self.__has_parent_dep(fmris[0], cat, excludes):
                                # ips incorporation has parent deps
                                ips_has_pdep = True
                if osnet_has_pdep and ips_has_pdep:
                        return dict()

                if not installed_catalog:
                        # search the known catalog
                        cat = self.__img.get_catalog(
                            self.__img.IMG_CATALOG_KNOWN)

                # assume that the osnet and ips incorporations should always
                # have a parent dependencies.
                inc_fmris = set()
                for tgt in [osnet_incorp, ips_incorp]:
                        for (ver, fmris) in cat.fmris_by_version(tgt):
                                for fmri in fmris:
                                        if not self.__has_parent_dep(fmri, cat,
                                            excludes):
                                                inc_fmris |= set([fmri])

                # find the fmris that each osnet/ips incorporation incorporates
                inc_pkgs = set()
                for fmri in inc_fmris:
                        for a in cat.get_entry_actions(fmri,
                            [pkg.catalog.Catalog.DEPENDENCY],
                            excludes=excludes):
                                if (a.name != "depend") or \
                                    (a.attrs["type"] != "incorporate"):
                                        continue

                                # create an fmri for the incorporated package
                                build_release = str(fmri.version.build_release)
                                inc_pkgs |= set([pkg.fmri.PkgFmri(
                                    a.attrs["fmri"],
                                    build_release=build_release)])

                # translate the incorporated package fmris into actual
                # packages in the known catalog
                dep_fmris = set()
                for fmri in inc_pkgs:
                        for (ver, fmris) in cat.fmris_by_version(fmri.pkg_name):
                                if ver == fmri.version or ver.is_successor(
                                    fmri.version, pkg.version.CONSTRAINT_AUTO):
                                        dep_fmris |= set(fmris)

                # all the fmris we want to add dependencies to.
                all_fmris = inc_fmris | dep_fmris

                # remove some unwanted fmris
                rm_fmris = set()
                for pfmri in all_fmris:
                        # eliminate renamed or obsoleted fmris
                        entry = cat.get_entry(pfmri)
                        state = entry["metadata"]["states"]
                        if pkgdefs.PKG_STATE_OBSOLETE in state or \
                            pkgdefs.PKG_STATE_RENAMED in state:
                                rm_fmris |= set([pfmri])
                                continue

                        # eliminate any group packages
                        if pfmri.pkg_name.startswith("group/"):
                                rm_fmris |= set([pfmri])
                                continue

                all_fmris -= rm_fmris

                return dict([(fmri, [pda]) for fmri in all_fmris])


class LinkedImageChild(object):
        """A LinkedImageChild object is used when a parent image wants to
        access a child image.  These accesses may include things like:
        saving/pushing linked image metadata into a child image, syncing or
        auditing a child image, or recursing into a child image to keep it in
        sync with planned changes in the parent image."""

        def __init__(self, li, lin):
                assert isinstance(li, LinkedImage), \
                    "isinstance(%s, LinkedImage)" % type(li)
                assert isinstance(lin, LinkedImageName), \
                    "isinstance(%s, LinkedImageName)" % type(lin)

                # globals
                self.__linked = li
                self.__img = li.image

                # cache properties.
                self.__props = self.__linked.child_props(lin)
                assert self.__props[PROP_NAME] == lin

                try:
                        imgdir = ar.ar_img_prefix(self.child_path)
                except OSError:
                        raise apx.LinkedImageException(
                            lin=lin, child_path_eaccess=self.child_path)

                if not imgdir:
                        raise apx.LinkedImageException(
                            lin=lin, child_bad_img=self.child_path)

                # initialize paths for linked image data files
                self.__path_ppkgs = os.path.join(imgdir, PATH_PPKGS)
                self.__path_prop = os.path.join(imgdir, PATH_PROP)
                self.__path_ppubs = os.path.join(imgdir, PATH_PUBS)
                self.__path_pfacets = os.path.join(imgdir, PATH_PFACETS)

                # initialize a linked image child plugin
                self.__plugin = \
                    pkg.client.linkedimage.p_classes_child[lin.lin_type](self)

                self.__pkg_remote = pkg.client.pkgremote.PkgRemote()
                self.__child_op_rvtuple = None

        @property
        def child_name(self):
                """Get the path associated with a child image."""
                return self.__props[PROP_NAME]

        @property
        def child_path(self):
                """Get the path associated with a child image."""
                return self.__props[PROP_PATH]

        @property
        def child_pimage(self):
                """Get a pointer to the parent image object associated with
                this child."""
                return self.__img

        @staticmethod
        def __push_data(root, path, data, tmp, test):
                """Write data to a child image."""

                # first save our data to a temporary file
                path_tmp = "%s.%s" % (path, global_settings.client_runid)
                save_data(path_tmp, data, root=root)

                # check if we're updating the data
                updated = True

                try:
                        exists = ar.ar_exists(root, path)
                except OSError, e:
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        raise apx._convert_error(e)

                if exists:
                        try:
                                updated = ar.ar_diff(root, path, path_tmp)
                        except OSError, e:
                                # W0212 Access to a protected member
                                # pylint: disable=W0212
                                raise apx._convert_error(e)

                # if we're not actually updating any data, or if we were just
                # doing a test to see if the data has changed, then delete the
                # temporary data file
                if not updated or test:
                        ar.ar_unlink(root, path_tmp)
                        return updated

                if not tmp:
                        # we are updating the real data.
                        try:
                                ar.ar_rename(root, path_tmp, path)
                        except OSError, e:
                                # W0212 Access to a protected member
                                # pylint: disable=W0212
                                raise apx._convert_error(e)

                return True

        def __push_ppkgs(self, ppkgs, tmp=False, test=False):
                """Sync linked image parent constraint data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # save the planned parent packages
                return self.__push_data(self.child_path, self.__path_ppkgs,
                    ppkgs, tmp, test)

        def __push_pfacets(self, pfacets, tmp=False, test=False):
                """Sync linked image parent facet data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # save the planned parent facets
                return self.__push_data(self.child_path, self.__path_pfacets,
                    pfacets, tmp, test)


        def __push_props(self, tmp=False, test=False):
                """Sync linked image properties data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # make a copy of the props we want to push
                props = self.__props.copy()
                assert PROP_PARENT_PATH not in props

                self.__plugin.munge_props(props)

                # delete temporal properties
                props = rm_dict_ent(props, temporal_props)

                return self.__push_data(self.child_path, self.__path_prop,
                    props, tmp, test)

        def __push_ppubs(self, ppubs, tmp=False, test=False):
                """Sync linked image parent publisher data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                return self.__push_data(self.child_path, self.__path_ppubs,
                    ppubs, tmp, test)

        def __syncmd(self, pmd, tmp=False, test=False):
                """Sync linked image data to a child image.

                'tmp' determines if we should read/write to the official
                linked image metadata files, or if we should access temporary
                versions (which have ".<runid>" appended to them."""

                # unpack parent metadata tuple
                ppubs, ppkgs, pfacets = pmd

                ppkgs_updated = self.__push_ppkgs(ppkgs, tmp, test)
                props_updated = self.__push_props(tmp, test)
                pubs_updated = self.__push_ppubs(ppubs, tmp, test)
                pfacets_updated = self.__push_pfacets(pfacets, tmp, test)

                return (props_updated or ppkgs_updated or pubs_updated or
                    pfacets_updated)

        def __child_op_setup_syncmd(self, pmd, ignore_syncmd_nop=True,
            tmp=False, test=False, stage=pkgdefs.API_STAGE_DEFAULT):
                """Prepare to perform an operation on a child image by syncing
                the latest linked image data to that image.  As part of this
                operation, if we discover that the meta data hasn't changed we
                may report back that there is nothing to do (EXIT_NOP).

                'pmd' is a tuple that contains parent metadata that we will
                sync to the child image.  Note this is not all the metadata
                that we will sync, just the set which is common to all
                children.

                'ignore_syncmd_nop' a boolean that indicates if we should
                always recurse into a child even if the linked image meta data
                isn't changing.

                'tmp' a boolean that indicates if we should save the child
                image meta data into temporary files (instead of overwriting
                the persistent meta data files).

                'test' a boolean that indicates we shouldn't save any child
                image meta data, instead we should just test to see if the
                meta data is changing.

                'stage' indicates which stage of execution we should be
                performing on a child image."""

                # we don't update metadata during all stages of operation
                if stage not in [
                    pkgdefs.API_STAGE_DEFAULT, pkgdefs.API_STAGE_PLAN]:
                        return True

                try:
                        updated = self.__syncmd(pmd, tmp=tmp, test=test)
                except apx.LinkedImageException, e:
                        self.__child_op_rvtuple = \
                            LI_RVTuple(e.lix_exitrv, e, None)
                        return False

                if ignore_syncmd_nop:
                        # we successfully updated the metadata
                        return True

                # if the metadata changed then report success
                if updated:
                        return True

                # the metadata didn't change, so this operation is a NOP
                self.__child_op_rvtuple = \
                    LI_RVTuple(pkgdefs.EXIT_NOP, None, None)
                return False

        def __child_setup_sync(self, _pmd, _progtrack, _ignore_syncmd_nop,
            _syncmd_tmp,
            accept=False,
            li_md_only=False,
            li_pkg_updates=True,
            noexecute=False,
            refresh_catalogs=True,
            reject_list=misc.EmptyI,
            show_licenses=False,
            stage=pkgdefs.API_STAGE_DEFAULT,
            update_index=True):
                """Prepare to sync a child image.  This involves updating the
                linked image metadata in the child and then possibly recursing
                into the child to actually update packages.

                For descriptions of parameters please see the descriptions in
                api.py`gen_plan_*"""

                if li_md_only:
                        #
                        # we're not going to recurse into the child image,
                        # we're just going to update its metadata.
                        #
                        # we don't support updating packages in the parent
                        # during attach metadata only sync.
                        #
                        if not self.__child_op_setup_syncmd(_pmd,
                            ignore_syncmd_nop=False,
                            test=noexecute, stage=stage):
                                # the update failed
                                return
                        self.__child_op_rvtuple = \
                            LI_RVTuple(pkgdefs.EXIT_OK, None, None)
                        return

                #
                # first sync the metadata
                #
                # if we're doing this sync as part of an attach, then
                # temporarily sync the metadata since we don't know yet if the
                # attach will succeed.  if the attach doesn't succeed this
                # means we don't have to delete any metadata.  if the attach
                # succeeds the child will make the temporary metadata
                # permanent as part of the commit.
                #
                # we don't support updating packages in the parent
                # during attach.
                #
                if not self.__child_op_setup_syncmd(_pmd,
                    ignore_syncmd_nop=_ignore_syncmd_nop,
                    tmp=_syncmd_tmp, stage=stage):
                        # the update failed or the metadata didn't change
                        return

                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_SYNC,
                    accept=accept,
                    backup_be=None,
                    backup_be_name=None,
                    be_activate=True,
                    be_name=None,
                    li_ignore=None,
                    li_md_only=li_md_only,
                    li_parent_sync=True,
                    li_pkg_updates=li_pkg_updates,
                    li_target_all=False,
                    li_target_list=[],
                    new_be=None,
                    noexecute=noexecute,
                    origins=[],
                    parsable_version=\
                        global_settings.client_output_parsable_version,
                    quiet=global_settings.client_output_quiet,
                    refresh_catalogs=refresh_catalogs,
                    reject_pats=reject_list,
                    show_licenses=show_licenses,
                    stage=stage,
                    update_index=update_index,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_update(self, _pmd, _progtrack, _ignore_syncmd_nop,
            _syncmd_tmp,
            accept=False,
            force=False,
            noexecute=False,
            refresh_catalogs=True,
            reject_list=misc.EmptyI,
            show_licenses=False,
            stage=pkgdefs.API_STAGE_DEFAULT,
            update_index=True):
                """Prepare to update a child image."""

                # first sync the metadata
                if not self.__child_op_setup_syncmd(_pmd,
                    ignore_syncmd_nop=_ignore_syncmd_nop,
                    tmp=_syncmd_tmp, stage=stage):
                        # the update failed or the metadata didn't change
                        return

                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_UPDATE,
                    accept=accept,
                    backup_be=None,
                    backup_be_name=None,
                    be_activate=True,
                    be_name=None,
                    force=force,
                    li_ignore=None,
                    li_parent_sync=True,
                    new_be=None,
                    noexecute=noexecute,
                    origins=[],
                    parsable_version=\
                        global_settings.client_output_parsable_version,
                    quiet=global_settings.client_output_quiet,
                    refresh_catalogs=refresh_catalogs,
                    reject_pats=reject_list,
                    show_licenses=show_licenses,
                    stage=stage,
                    update_index=update_index,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_detach(self, _progtrack, li_md_only=False,
            li_pkg_updates=True, noexecute=False):
                """Prepare to detach a child image."""

                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_DETACH,
                    force=True,
                    li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates,
                    li_target_all=False,
                    li_target_list=[],
                    noexecute=noexecute,
                    quiet=global_settings.client_output_quiet,
                    verbose=global_settings.client_output_verbose)

        def __child_setup_pubcheck(self, _pmd):
                """Prepare to a check if a child's publishers are in sync."""

                # first sync the metadata
                # a pubcheck should never update persistent meta data
                if not self.__child_op_setup_syncmd(_pmd, tmp=True):
                        # the update failed
                        return

                # setup recursion into the child image
                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_PUBCHECK)

        def __child_setup_audit(self, _pmd):
                """Prepare to a child image to see if it's in sync with its
                constraints."""

                # first sync the metadata
                if not self.__child_op_setup_syncmd(_pmd, tmp=True):
                        # the update failed
                        return

                # setup recursion into the child image
                self.__pkg_remote.setup(self.child_path,
                    pkgdefs.PKG_OP_AUDIT_LINKED,
                    li_parent_sync=True,
                    li_target_all=False,
                    li_target_list=[],
                    omit_headers=True,
                    quiet=True)

        def child_op_abort(self):
                """Public interface to abort an operation on a child image."""

                self.__pkg_remote.abort()
                self.__child_op_rvtuple = None

        def child_op_setup(self, _pkg_op, _pmd, _progtrack, _ignore_syncmd_nop,
            _syncmd_tmp, **kwargs):
                """Public interface to setup an operation that we'd like to
                perform on a child image."""

                assert self.__child_op_rvtuple is None

                if _pkg_op == pkgdefs.PKG_OP_AUDIT_LINKED:
                        self.__child_setup_audit(_pmd, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_DETACH:
                        self.__child_setup_detach(_progtrack, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_PUBCHECK:
                        self.__child_setup_pubcheck(_pmd, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_SYNC:
                        self.__child_setup_sync(_pmd, _progtrack,
                            _ignore_syncmd_nop, _syncmd_tmp, **kwargs)
                elif _pkg_op == pkgdefs.PKG_OP_UPDATE:
                        self.__child_setup_update(_pmd, _progtrack,
                            _ignore_syncmd_nop, _syncmd_tmp, **kwargs)
                else:
                        raise RuntimeError(
                            "Unsupported package client op: %s" % _pkg_op)

        def child_op_start(self):
                """Public interface to start an operation on a child image."""

                # if we have a return value this operation is done
                if self.__child_op_rvtuple is not None:
                        return True

                self.__pkg_remote.start()

        def child_op_is_done(self):
                """Public interface to query if an operation on a child image
                is done."""

                # if we have a return value this operation is done
                if self.__child_op_rvtuple is not None:
                        return True

                # make sure there is some data from the child
                return self.__pkg_remote.is_done()

        def child_op_rv(self, pkg_op, expect_plan):
                """Public interface to get the result of an operation on a
                child image.

                'expect_plan' boolean indicating if the child is performing a
                planning operation.  this is needed because if we're running
                in parsable output mode then the child will emit a parsable
                json version of the plan on stdout, and we'll verify it by
                running it through the json parser.
                """

                # if we have a return value this operation is done
                if self.__child_op_rvtuple is not None:
                        rvtuple = self.__child_op_rvtuple
                        self.__child_op_rvtuple = None
                        return (rvtuple, None, None)

                # make sure we're not going to block
                assert self.__pkg_remote.is_done()

                (rv, e, stdout, stderr) = self.__pkg_remote.result()
                if e is not None:
                        rv = pkgdefs.EXIT_OOPS

                # if we got an exception, or a return value other than OK or
                # NOP, then return an exception.
                if e is not None or \
                    rv not in [pkgdefs.EXIT_OK, pkgdefs.EXIT_NOP]:
                        e = apx.LinkedImageException(
                            lin=self.child_name, exitrv=rv,
                            pkg_op_failed=(pkg_op, rv, stdout + stderr, e))
                        rvtuple = LI_RVTuple(rv, e, None)
                        return (rvtuple, stdout, stderr)

                # check for NOP.
                if rv == pkgdefs.EXIT_NOP:
                        assert e is None
                        rvtuple = LI_RVTuple(rv, None, None)
                        return (rvtuple, stdout, stderr)

                if global_settings.client_output_parsable_version is None or \
                    not expect_plan:
                        rvtuple = LI_RVTuple(rv, None, None)
                        return (rvtuple, stdout, stderr)

                # If a plan was created and we're in parsable output mode then
                # parse the plan that should have been displayed to stdout.
                p_dict = None
                try:
                        p_dict = json.loads(stdout)
                except ValueError, e:
                        # JSON raises a subclass of ValueError when it
                        # can't parse a string.

                        e = apx.LinkedImageException(
                            lin=self.child_name,
                            unparsable_output=(pkg_op, stdout + stderr, e))
                        rvtuple = LI_RVTuple(rv, e, None)
                        return (rvtuple, stdout, stderr)

                p_dict["image-name"] = str(self.child_name)
                rvtuple = LI_RVTuple(rv, None, p_dict)
                return (rvtuple, stdout, stderr)

        def fileno(self):
                """Return the progress pipe associated with the PkgRemote
                instance that is operating on a child image."""
                return self.__pkg_remote.fileno()

        def child_init_root(self, old_altroot):
                """Our image path is being updated, so figure out our new
                child image paths.  This interface only gets invoked when:

                - We're doing a packaging operation on a parent image and
                  we've just cloned that parent to create a new BE that we're
                  going to update.  This clone also cloned all the children
                  and so now we need to update our paths to point to the newly
                  created children.

                - We tried to update a cloned image (as described above) and
                  our update failed, hence we're changing paths back to the
                  original images that were the source of the clone."""

                # get the image path without the altroot
                altroot_path = self.__props[PROP_PATH]
                path = rm_altroot_path(altroot_path, old_altroot)

                # update the path with the current altroot
                altroot = self.__linked.altroot()
                path = add_altroot_path(path, altroot)

                # update properties with altroot
                self.__props[PROP_PATH] = path
                self.__props[PROP_ALTROOT] = altroot

                # we don't bother to update update PROP_PARENT_PATH since
                # that is only used when reading constraint data from the
                # parent image, and this interface is only invoked when we're
                # starting or finishing execution of a plan on a cloned image
                # (at which point we have no need to access the parent
                # anymore).


# ---------------------------------------------------------------------------
# Interfaces to obtain linked image metadata from an image
#
def get_pubs(img):
        """Return publisher information for the specified image.

        Publisher information is returned in a sorted list of lists
        of the format:
                <publisher name>, <sticky>

        Where:
                <publisher name> is a string
                <sticky> is a boolean

        The tuples are sorted by publisher rank.
        """

        return [
            [str(p), p.sticky]
            for p in img.get_sorted_publishers(inc_disabled=False)
        ]

def get_packages(img, pd=None):
        """Figure out the current (or planned) list of packages in img."""

        ppkgs = set(img.get_catalog(img.IMG_CATALOG_INSTALLED).fmris())

        # if there's an image plan the we need to update the installed
        # packages based on that plan.
        if pd is not None:
                for src, dst in pd.plan_desc:
                        if src == dst:
                                continue
                        if src:
                                assert src in ppkgs
                                ppkgs -= set([src])
                        if dst:
                                assert dst not in ppkgs
                                ppkgs |= set([dst])

        # paranoia
        return frozenset(ppkgs)

def get_inheritable_facets(img, pd=None):
        """Get Facets from an image that a child should inherit.

        We only want to sync facets which affect packages that have parent
        dependencies on themselves.  In practice this essentially limits us to
        "facet.version-lock.*" facets."""

        # get installed (or planned) parent packages and facets
        ppkgs = get_packages(img, pd=pd)
        facets = img.cfg.facets
        if pd is not None and pd.new_facets is not None:
                facets = pd.new_facets

        # create a packages dictionary indexed by package stem.
        ppkgs_dict = dict([
                (pfmri.pkg_name, pfmri)
                for pfmri in ppkgs
        ])

        #
        # iterate through all installed (or planned) package incorporation
        # dependency actions and find those that are affected by image facets.
        #
        # we don't check for package-wide facets here because they don't do
        # anything.  (ie, facets defined via "set" actions in a package have
        # no effect on other actions within that package.)
        #
        faceted_deps = dict()
        cat = img.get_catalog(img.IMG_CATALOG_KNOWN)
        for pfmri in ppkgs:
                for act in cat.get_entry_actions(pfmri, [cat.DEPENDENCY]):
                        # we're only interested in incorporate dependencies
                        if act.name != "depend" or \
                            act.attrs["type"] != "incorporate":
                                continue

                        # check if any image facets affect this dependency
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        matching_facets = facets._action_match(act)
                        # pylint: enable=W0212
                        if not matching_facets:
                                continue

                        # if all the matching facets are true we don't care
                        # about the match.
                        if set([i[1] for i in matching_facets]) == set([True]):
                                continue

                        # save this set of facets.
                        faceted_deps[act] = matching_facets

        #
        # For each faceted incorporation dependency, check if it affects a
        # package that has parent dependencies on itself.  This is really a
        # best effort in that we don't follow package renames or obsoletions,
        # etc.
        #
        # To limit the number of packages we inspect, we'll try to match the
        # incorporation dependency fmri targets packages by stem to packages
        # which are installed (or planned) within the parent image.  This
        # allows us to quickly get a fully qualified fmri and check against a
        # package for which we have already downloaded a manifest.
        #
        # If we can't match the dependency fmri package stem against packages
        # installed (or planned) in the parent image, we don't bother
        # searching for allowable packages in the catalog, because even if we
        # found them in the catalog and they did have a parent dependency,
        # they'd all still be uninstallable in any children because there
        # would be no way to satisfy the parent dependency.  (as we already
        # stated the package is not installed in the parent.)
        #
        faceted_linked_deps = dict()
        for act in faceted_deps:
                for fmri in act.attrlist("fmri"):
                        pfmri = pkg.fmri.PkgFmri(fmri)
                        pfmri = ppkgs_dict.get(pfmri.pkg_name, None)
                        if pfmri is None:
                                continue

                        # check if this package has a dependency on itself in
                        # its parent image.
                        for act2 in cat.get_entry_actions(pfmri,
                            [cat.DEPENDENCY]):
                                if act2.name != "depend" or \
                                    act2.attrs["type"] != "parent":
                                        continue
                                if pkg.actions.depend.DEPEND_SELF not in \
                                    act2.attrlist("fmri"):
                                        continue
                                faceted_linked_deps[act] = faceted_deps[act]
                                break
        del faceted_deps

        #
        # Create a set of all facets which affect incorporation dependencies
        # on synced packages.
        #
        # Note that we can't limit ourselves to only passing on facets that
        # affect dependencies which have been disabled.  Doing this could lead
        # to incorrect results because facets allow for pattern matching.  So
        # for example say we had the following dependencies on synced
        # packages:
        #
        #    depend type=incorporation fmri=some_synced_pkg1 facet.123456=true
        #    depend type=incorporation fmri=some_synced_pkg2 facet.456789=true
        #
        # and the following image facets:
        #
        #    facet.123456 = True
        #    facet.*456* = False
        #
        # if we only passed through facets which affected disabled packages
        # we'd just pass through "facet.*456*", but this would result in
        # disabling both dependencies above, not just the second dependency.
        #
        pfacets = pkg.facet.Facets()
        for facets in faceted_linked_deps.values():
                for k, v in facets:
                        # W0212 Access to a protected member
                        # pylint: disable=W0212
                        pfacets._set_inherited(k, v)

        return pfacets

# ---------------------------------------------------------------------------
# Utility Functions
#
def save_data(path, data, root="/"):
        """Save JSON encoded linked image metadata to a file."""

        # make sure the directory we're about to save data into exists.
        path_dir = os.path.dirname(path)
        pathtmp = "%s.%d.tmp" % (path, os.getpid())

        try:
                if not ar.ar_exists(root, path_dir):
                        ar.ar_mkdir(root, path_dir, misc.PKG_DIR_MODE)

                # write the output to a temporary file
                fd = ar.ar_open(root, pathtmp, os.O_WRONLY,
                    mode=0644, create=True, truncate=True)
                fobj = os.fdopen(fd, "w")
                json.dump(data, fobj, encoding="utf-8",
                    cls=pkg.client.linkedimage.PkgEncoder)
                fobj.close()

                # atomically create the desired file
                ar.ar_rename(root, pathtmp, path)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

def load_data(path, missing_ok=False):
        """Load JSON encoded linked image metadata from a file."""

        try:
                if missing_ok and not path_exists(path):
                        return None
                fobj = open(path)
                data = json.load(fobj, encoding="utf-8",
                    object_hook=pkg.client.linkedimage.PkgDecoder)
                fobj.close()
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)
        return data


class PkgEncoder(json.JSONEncoder):
        """Utility class used when json encoding linked image metadata."""

        # E0202 An attribute inherited from JSONEncoder hide this method
        # pylint: disable=E0202
        def default(self, obj):
                """Required routine that overrides the default base
                class version.  This routine must serialize 'obj' when
                attempting to save 'obj' json format."""

                if isinstance(obj, (pkg.fmri.PkgFmri,
                    pkg.client.linkedimage.common.LinkedImageName)):
                        return str(obj)

                if isinstance(obj, pkgplan.PkgPlan):
                        return obj.getstate()

                if isinstance(obj, (set, frozenset)):
                        return list(obj)

                return json.JSONEncoder.default(self, obj)


def PkgDecoder(dct):
        """Utility class used when json decoding linked image metadata."""
        # Replace unicode keys/values with strings
        rvdct = {}
        for k, v in dct.iteritems():

                # unicode must die
                if type(k) == unicode:
                        k = k.encode("utf-8")
                if type(v) == unicode:
                        v = v.encode("utf-8")

                # convert boolean strings values back into booleans
                if type(v) == str:
                        if v.lower() == "true":
                                v = True
                        elif v.lower() == "false":
                                v = False

                rvdct[k] = v
        return rvdct

def rm_dict_ent(d, keys):
        """Remove a set of keys from a dictionary."""
        return dict([
                (k, v)
                for k, v in d.iteritems()
                if k not in keys
        ])

def _rterr(li=None, lic=None, lin=None, path=None, err=None,
    bad_cp=None,
    bad_iup=None,
    bad_lin_type=None,
    bad_prop=None,
    missing_props=None,
    multiple_altroots=None,
    saved_temporal_props=None):
        """Oops.  We hit a runtime error.  Die with a nice informative
        message.  Note that runtime errors should never happen and usually
        indicate bugs (or possibly corrupted linked image metadata), so they
        are not localized (just like asserts are not localized)."""

        assert not (li and lic)
        assert not ((lin or path) and li)
        assert not ((lin or path) and lic)
        assert path == None or type(path) == str

        if bad_cp:
                assert err == None
                err = "Invalid linked content policy: %s" % bad_cp
        elif bad_iup:
                assert err == None
                err = "Invalid linked image update policy: %s" % bad_iup
        elif bad_lin_type:
                assert err == None
                err = "Invalid linked image type: %s" % bad_lin_type
        elif bad_prop:
                assert err == None
                err = "Invalid linked property value: %s=%s" % bad_prop
        elif missing_props:
                assert err == None
                err = "Missing required linked properties: %s" % \
                    ", ".join(missing_props)
        elif multiple_altroots:
                assert err == None
                err = "Multiple plugins reported different altroots:"
                for plugin, altroot in multiple_altroots:
                        err += "\n\t%s = %s" % (plugin, altroot)
        elif saved_temporal_props:
                assert err == None
                err = "Found saved temporal linked properties: %s" % \
                    ", ".join(saved_temporal_props)
        else:
                assert err != None

        if li:
                if li.ischild():
                        lin = li.child_name
                path = li.image.root

        if lic:
                lin = lic.child_name
                path = lic.child_path

        err_prefix = "Linked image error: "
        if lin:
                err_prefix = "Linked image (%s) error: " % (str(lin))

        err_suffix = ""
        if path and lin:
                err_suffix = "\nLinked image (%s) path: %s" % (str(lin), path)
        elif path:
                err_suffix = "\nLinked image path: %s" % (path)

        raise RuntimeError(
            "%s: %s%s" % (err_prefix, err, err_suffix))

# ---------------------------------------------------------------------------
# Functions for accessing files in the current root
#
def path_exists(path):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_exists("/", path)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

def path_isdir(path):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_isdir("/", path)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

def path_mkdir(path, mode):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_mkdir("/", path, mode)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

def path_unlink(path, noent_ok=False):
        """Simple wrapper for accessing files in the current root."""

        try:
                return ar.ar_unlink("/", path, noent_ok=noent_ok)
        except OSError, e:
                # W0212 Access to a protected member
                # pylint: disable=W0212
                raise apx._convert_error(e)

# ---------------------------------------------------------------------------
# Functions for managing images which may be in alternate roots
#
def check_altroot_path(path, altroot):
        """Check if 'path' is nested within 'altroot'"""

        assert os.path.isabs(path), "os.path.isabs(%s)" % path
        assert os.path.isabs(altroot), "os.path.isabs(%s)" % altroot

        # make sure both paths have one trailing os.sep.
        altroot = altroot.rstrip(os.sep) + os.sep
        path = path.rstrip(os.sep) + os.sep

        # check for nested or equal paths
        if path.startswith(altroot):
                return True
        return False

def add_altroot_path(path, altroot):
        """Return a path where 'path' is nested within 'altroot'"""

        assert os.path.isabs(path), "os.path.isabs(%s)" % path
        assert os.path.isabs(altroot), "os.path.isabs(%s)" % altroot

        altroot = altroot.rstrip(os.sep) + os.sep
        path = path.lstrip(os.sep)
        altroot_path = altroot + path

        # sanity check
        assert check_altroot_path(altroot_path, altroot), \
            "check_altroot_path(%s, %s)" % (altroot_path, altroot)

        return altroot_path

def rm_altroot_path(path, altroot):
        """Return the relative porting of 'path', which must be nested within
        'altroot'"""

        assert os.path.isabs(path), "not os.path.isabs(%s)" % path
        assert os.path.isabs(altroot), "not os.path.isabs(%s)" % altroot

        assert check_altroot_path(path, altroot), \
            "not check_altroot_path(%s, %s)" % (path, altroot)

        rv = path[len(altroot.rstrip(os.sep)):]
        if rv == "":
                rv = "/"
        assert os.path.isabs(rv)
        return rv

def get_altroot_path(path, path_suffix):
        """Given 'path', and a relative path 'path_suffix' that must match
        the suffix of 'path', return the unmatched prefix of 'path'."""

        assert os.path.isabs(path), "os.path.isabs(%s)" % path
        assert os.path.isabs(path_suffix), "os.path.isabs(%s)" % path_suffix

        # make sure both paths have one trailing os.sep.
        path = path.rstrip(os.sep) + os.sep
        path_suffix = path_suffix.rstrip(os.sep) + os.sep

        i = path.rfind(path_suffix)
        if i <= 0:
                # path and path_suffix are either unrelated or equal
                altroot = os.sep
        else:
                altroot = path[:i]

        # sanity check
        assert check_altroot_path(path, altroot), \
            "check_altroot_path(%s, %s)" % (path, altroot)

        return altroot
