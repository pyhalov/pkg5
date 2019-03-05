#!/usr/bin/python
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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

# The portable module provide access to methods that require operating system-
# specific implementations. The module initialization logic selects the right
# implementation the module is loaded.  The module methods then
# delegate to the implementation class object. 
#
# The documentation for the methods is provided in this module.  To support
# another operating system, each of these methods must be implemented by the
# class for that operating system even if it is effectively a no-op. 
#
# The module and class must be named using os_[impl], where
# [impl] corresponds to the OS distro, name, or type of OS
# the class implements.  For example, to add specific support
# for mandrake linux (above and beyond existing support for
# generic unix), one would create os_mandrake.py.
#           
# The following high-level groups of methods are defined in this module:
#                
#   - Platform Attribute Methods: These methods give access to
#     attributes of the underlying platform not available through
#     existing python libraries.  For example, the list of implemented
#     ISAs of a given platform.
#              
#   - Account access: Retrieval of account information (users and
#     groups), in some cases for dormant, relocated OS images.
#             
#   - Miscellaneous filesystem operations: common operations that
#     differ in implementation or are only available on a subset
#     of OS or filesystem implementations, such as chown() or rename().  

# This module exports the methods defined below.  They are defined here as 
# not implemented to avoid pylint errors.  The included OS-specific module 
# redefines the methods with an OS-specific implementation.

# Platform Methods
# ----------------
def get_isainfo():
        """ Return the information for the OS's supported ISAs.
        This can be a list or a single string."""
        raise NotImplementedError

def get_release():
        """ Return the information for the OS's release version.  This
        must be a dot-separated set of integers (i.e. no alphabetic
        or punctuation)."""
        raise NotImplementedError
        
def get_platform():
        """ Return a string representing the current hardware model
        information, e.g. "i86pc"."""
        raise NotImplementedError

def get_file_type(actions):
        """ Return a list containing the file type for each file in paths."""
        raise NotImplementedError

# Account access
# --------------
def get_group_by_name(name, dirpath, use_file):
        """ Return the group ID for a group name.
        If use_file is true, an OS-specific file from within the file tree
        rooted by dirpath will be consulted, if it exists. Otherwise, the 
        group ID is retrieved from the operating system.
        Exceptions:        
            KeyError if the specified group does not exist"""
        raise NotImplementedError

def get_user_by_name(name, dirpath, use_file):
        """ Return the user ID for a user name.
        If use_file is true, an OS-specific file from within the file tree
        rooted by dirpath will be consulted, if it exists. Otherwise, the 
        user ID is retrieved from the operating system.
        Exceptions:
            KeyError if the specified group does not exist"""
        raise NotImplementedError

def get_name_by_gid(gid, dirpath, use_file):
        """ Return the group name for a group ID.
        If use_file is true, an OS-specific file from within the file tree
        rooted by dirpath will be consulted, if it exists. Otherwise, the 
        group name is retrieved from the operating system.
        Exceptions:
            KeyError if the specified group does not exist"""
        raise NotImplementedError

def get_name_by_uid(uid, dirpath, use_file):
        """ Return the user name for a user ID.
        If use_file is true, an OS-specific file from within the file tree
        rooted by dirpath will be consulted, if it exists. Otherwise, the 
        user name is retrieved from the operating system.
        Exceptions:
            KeyError if the specified group does not exist"""
        raise NotImplementedError

def get_usernames_by_gid(gid, dirpath):
        """ Return all user names associated with a group ID.
        The user name is first retrieved from an OS-specific file rooted
        by dirpath. If failed, try to retrieve it from the operating system."""
        raise NotImplementedError

def is_admin():
        """ Return true if the invoking user has administrative
        privileges on the current runtime OS (e.g. are they the
        root user?)."""
        raise NotImplementedError

def get_userid():
        """ Return a string representing the invoking user's id.  To be used
        for display purposes only!"""
        raise NotImplementedError

def get_username():
        """ Return a string representing the invoking user's username.  To be
        used for display purposes only!"""
        raise NotImplementedError


# Miscellaneous filesystem operations
# -----------------------------------
def chown(path, owner, group):
        """ Change ownership of a file in an OS-specific way.
        The owner and group ownership information should be applied to
        the given file, if applicable on the current runtime OS.
        Exceptions:        
            EnvironmentError (or subclass) if the path does not exist
            or ownership cannot be changed"""
        raise NotImplementedError

def rename(src, dst):
        """ Change the name of the given file, using the most
        appropriate method for the OS.
        Exceptions:
            OSError (or subclass) if the source path does not exist
            EnvironmentError if the rename fails."""
        raise NotImplementedError

def link(src, dst):
        """ Link the src to the dst if supported, otherwise copy
        Exceptions:
           OSError (or subclass) if the source path does not exist or the link
           or copy files"""
        raise NotImplementedError

def remove(path):
        """ Remove the given file in an OS-specific way
        Exceptions:
           OSError (or subclass) if the source path does not exist or 
           the file cannot be removed"""
        raise NotImplementedError

def copyfile(src, dst):
        """ Copy the contents of the file named src to a file named dst.
        If dst already exists, it will be replaced. src and dst are
        path names given as strings.
        This is similar to python's shutil.copyfile() except that
        the intention is to deal with platform specifics, such as
        copying metadata associated with the file (e.g. Resource
        forks on Mac OS X).
        Exceptions: IOError if the destination location is not writable"""
        raise NotImplementedError

def split_path(path):
        """ Splits a path and gives back the components of the path.  
        This is intended to hide platform-specific details about splitting
        a path into its components.  This interface is similar to
        os.path.split() except that the entire path is split, not just
        the head/tail.

        For platforms where there are additional components (like
        a windows drive letter), these should be discarded before
        performing the split."""
        raise NotImplementedError

def get_root(path):
        """ Returns the 'root' of the given path.  
        This should include any and all components of a path up to the first
        non-platform-specific component.  For example, on Windows,
        it should include the drive letter prefix.

        This is intended to be used when constructing or deconstructing
        paths, where the root of the filesystem is significant (and
        often leads to ambiguity in cross-platform code)."""
        raise NotImplementedError

def assert_mode(path, mode):
        """ Checks that the file identified by path has the given mode to
        the extent possible by the host operating system.  Otherwise raises
        an AssertionError where the mode attribute of the assertion is the 
        mode of the file."""
        raise NotImplementedError

def fsetattr(path, attrs):
        """ Set system attributes for file specified by 'path'. 'attrs' can be
        a list of verbose system attributes or a string containing a sequence of
        short options."""
        raise NotImplementedError

def fgetattr(path, compact=False):
        """ Get system attributes for file specified by 'path'. If 'compact' is
        True, it returns a string of short attribute options, otherwise a list
        of verbose attributes."""
        raise NotImplementedError

def get_sysattr_dict():
        """ Returns a dictionary containing all supported system attributes. The
        keys of the dict are verbose attributes, the values short options."""
        raise NotImplementedError

# File type constants
# -------------------
ELF, EXEC, UNFOUND, SMF_MANIFEST = range(0, 4)

# String to be used for an action attribute created for the internal use of
# dependency analysis.
PD_LOCAL_PATH = "pkg.internal.depend.localpath"
PD_PROTO_DIR = "pkg.internal.depend.protodir"
PD_PROTO_DIR_LIST = "pkg.internal.depend.protodirlist"

# A String to be used for an action attribute created for pkgdepend, indicating
# module or run paths that can be used to specify the paths that it should use
# when searching for dependencies on given files.  For example setting the
# elf runpath for elf binaries, or $PYTHONPATH (or sys.path) for python modules.
PD_RUN_PATH = "pkg.depend.runpath"

# A string used as a component of the pkg.depend.runpath value as a special
# token to determine where to insert the runpath that pkgdepend automatically
# generates.
PD_DEFAULT_RUNPATH = "$PKGDEPEND_RUNPATH"

# A String used for an action attribute to allow pkgdepend to bypass generation
# of dependencies against a given filename, eg. don't try to generate a
# dependency on dtracestubs from platform/i86pc/kernel/amd64/unix
PD_BYPASS_GENERATE = "pkg.depend.bypass-generate"

import platform
from . import util as os_util

osname = os_util.get_canonical_os_name()
ostype = os_util.get_canonical_os_type()

fragments = [osname, ostype]
for fragment in fragments:
        modname = 'os_' + fragment

        # try the most-specific module name first (e.g. os_suse),
        # then try the more generic OS Name module (e.g. os_linux),
        # then the OS type module (e.g. os_unix)        
        try:
                exec('from .{0} import *'.format(modname))
                break
        except ImportError:
                pass
else:
        raise ImportError(
            "cannot find portable implementation class for os " + str(fragments))
