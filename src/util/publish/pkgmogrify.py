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
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
import getopt
import gettext
import locale
import os
import re
import shlex
import six
import sys
import traceback
import warnings

import pkg.actions
import pkg.misc as misc
from pkg.misc import PipeError
from pkg.client.pkgdefs import EXIT_OK, EXIT_OOPS, EXIT_BADOPT, EXIT_PARTIAL

macros  = {}
includes = []
appends  = []
transforms = []
printinfo = []


def usage(errmsg="", exitcode=EXIT_BADOPT):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if errmsg:
                print("pkgmogrify: {0}".format(errmsg), file=sys.stderr)

        print(_("""\
Usage:
        pkgmogrify [-vi] [-I includedir ...] [-D macro=value ...]
            [-O outputfile] [-P printfile] [inputfile ...]"""))
        sys.exit(exitcode)

def add_transform(transform, filename, lineno):
        """This routine adds a transform tuple to the list used
        to process actions."""

        # strip off transform
        s = transform[10:]
        # make error messages familiar
        transform = "<" + transform + ">"

        try:
                index = s.index("->")
        except ValueError:
                raise RuntimeError(_("Missing -> in transform"))
        matching = s[0:index].strip().split()
        types = [a for a in matching if "=" not in a]
        attrdict = pkg.actions.attrsfromstr(" ".join([a for a in matching if "=" in a]))

        for a in attrdict:
                try:
                        attrdict[a] = re.compile(attrdict[a])
                except re.error as e:
                        raise RuntimeError(
                            _("transform ({transform}) has regexp error "
                            "({err}) in matching clause"
                            ).format(transform=transform, err=e))

        op = s[index+2:].strip().split(None, 1)

        # use closures to encapsulate desired operation

        if op[0] == "drop":
                if len(op) > 1:
                        raise RuntimeError(
                            _("transform ({0}) has 'drop' operation syntax error"
                            ).format(transform))
                operation = lambda a, m, p, f, l: None

        elif op[0] == "set":
                try:
                        attr, value = shlex.split(op[1])
                except ValueError:
                        raise RuntimeError(
                            _("transform ({0}) has 'set' operation syntax error"
                            ).format(transform))
                def set_func(action, matches, pkg_attrs, filename, lineno):
                        newattr = substitute_values(attr, action, matches,
                            pkg_attrs, filename, lineno)
                        newval = substitute_values(value, action, matches,
                            pkg_attrs, filename, lineno)
                        if newattr == "action.hash":
                                if hasattr(action, "hash"):
                                        action.hash = newval
                        else:
                                action.attrs[newattr] = newval
                        return action
                operation = set_func

        elif op[0] == "default":
                try:
                        attr, value = shlex.split(op[1])
                except ValueError:
                        raise RuntimeError(
                            _("transform ({0}) has 'default' operation syntax error"
                            ).format(transform))

                def default_func(action, matches, pkg_attrs, filename, lineno):
                        newattr = substitute_values(attr, action, matches,
                            pkg_attrs, filename, lineno)
                        if newattr not in action.attrs:
                                newval = substitute_values(value, action,
                                    matches, pkg_attrs, filename, lineno)
                                action.attrs[newattr] = newval
                        return action
                operation = default_func

        elif op[0] == "abort":
                if len(op) > 1:
                        raise RuntimeError(_("transform ({0}) has 'abort' "
                            "operation syntax error").format(transform))

                def abort_func(action, matches, pkg_attrs, filename, lineno):
                        sys.exit(0)

                operation = abort_func

        elif op[0] == "exit":
                exitval = 0
                msg = None

                if len(op) == 2:
                        args = op[1].split(None, 1)
                        try:
                                exitval = int(args[0])
                        except ValueError:
                                raise RuntimeError(_("transform ({0}) has 'exit' "
                                    "operation syntax error: illegal exit value").format(
                                    transform))
                        if len(args) == 2:
                                msg = args[1]

                def exit_func(action, matches, pkg_attrs, filename, lineno):
                        if msg:
                                newmsg = substitute_values(msg, action,
                                    matches, pkg_attrs, filename, lineno,
                                    quote=True)
                                print(newmsg, file=sys.stderr)
                        sys.exit(exitval)

                operation = exit_func

        elif op[0] == "add":
                try:
                        attr, value = shlex.split(op[1])
                except ValueError:
                        raise RuntimeError(
                            _("transform ({0}) has 'add' operation syntax error"
                            ).format(transform))

                def add_func(action, matches, pkg_attrs, filename, lineno):
                        newattr = substitute_values(attr, action, matches,
                            pkg_attrs, filename, lineno)
                        newval = substitute_values(value, action, matches,
                            pkg_attrs, filename, lineno)
                        if newattr in action.attrs:
                                av = action.attrs[newattr]
                                if isinstance(av, list):
                                        action.attrs[newattr].append(newval)
                                else:
                                        action.attrs[newattr] = [ av, newval ]
                        else:
                                action.attrs[newattr] = newval
                        return action
                operation = add_func

        elif op[0] == "edit":
                if len(op) < 2:
                        raise RuntimeError(
                            _("transform ({0}) has 'edit' operation syntax error"
                            ).format(transform))

                args = shlex.split(op[1])
                if len(args) not in [2, 3]:
                        raise RuntimeError(
                            _("transform ({0}) has 'edit' operation syntax error"
                            ).format(transform))
                attr = args[0]

                # Run args[1] (the regexp) through substitute_values() with a
                # bunch of bogus values to see whether it triggers certain
                # exceptions.  If it does, then substitution would have
                # occurred, and we can't compile the regex now, but wait until
                # we can correctly run substitute_values().
                try:
                        substitute_values(args[1], None, [], None, None, None)
                        regexp = re.compile(args[1])
                except (AttributeError, RuntimeError):
                        regexp = args[1]
                except re.error as e:
                        raise RuntimeError(
                            _("transform ({transform}) has 'edit' operation "
                            "with malformed regexp ({err})").format(
                            transform=transform, err=e))

                if len(args) == 3:
                        replace = args[2]
                else:
                        replace = ""

                def replace_func(action, matches, pkg_attrs, filename, lineno):
                        newattr = substitute_values(attr, action, matches,
                            pkg_attrs, filename, lineno)
                        newrep = substitute_values(replace, action, matches,
                            pkg_attrs, filename, lineno)
                        val = attrval_as_list(action.attrs, newattr)

                        if not val:
                                return action

                        # It's now appropriate to compile the regexp, if there
                        # are substitutions to be made.  So do the substitution
                        # and compile the result.
                        if isinstance(regexp, six.string_types):
                                rx = re.compile(substitute_values(regexp,
                                    action, matches, pkg_attrs, filename, lineno))
                        else:
                                rx = regexp

                        try:
                                action.attrs[newattr] = [
                                    rx.sub(newrep, v)
                                    for v in val
                                ]
                        except re.error as e:
                                raise RuntimeError(
                                    _("transform ({transform}) has edit "
                                    "operation with replacement string regexp "
                                    "error {err}").format(
                                    transform=transform, err=e))
                        return action

                operation = replace_func

        elif op[0] == "delete":
                if len(op) < 2:
                        raise RuntimeError(
                            _("transform ({0}) has 'delete' operation syntax error"
                            ).format(transform))

                args = shlex.split(op[1])
                if len(args) != 2:
                        raise RuntimeError(
                            _("transform ({0}) has 'delete' operation syntax error"
                            ).format(transform))
                attr = args[0]

                try:
                        regexp = re.compile(args[1])
                except re.error as e:
                        raise RuntimeError(
                            _("transform ({transform}) has 'delete' operation"
                            "with malformed regexp ({err})").format(
                            transform=transform, err=e))

                def delete_func(action, matches, pkg_attrs, filename, lineno):
                        val = attrval_as_list(action.attrs, attr)
                        if not val:
                                return action
                        try:
                                new_val = [
                                    v
                                    for v in val
                                    if not regexp.search(v)
                                ]

                                if new_val:
                                        action.attrs[attr] = new_val
                                else:
                                        del action.attrs[attr]
                        except re.error as e:
                                raise RuntimeError(
                                    _("transform ({transform}) has delete "
                                    "operation with replacement string regexp "
                                    "error {err}").format(
                                    transform=transform, err=e))
                        return action

                operation = delete_func

        elif op[0] == "print":
                if len(op) > 2:
                        raise RuntimeError(_("transform ({0}) has 'print' "
                            "operation syntax error").format(transform))

                if len(op) == 1:
                        msg = ""
                else:
                        msg = op[1]

                def print_func(action, matches, pkg_attrs, filename, lineno):
                        newmsg = substitute_values(msg, action, matches,
                            pkg_attrs, filename, lineno, quote=True)

                        printinfo.append("{0}".format(newmsg))
                        return action

                operation = print_func

        elif op[0] == "emit":
                if len(op) > 2:
                        raise RuntimeError(_("transform ({0}) has 'emit' "
                            "operation syntax error").format(transform))

                if len(op) == 1:
                        msg = ""
                else:
                        msg = op[1]

                def emit_func(action, matches, pkg_attrs, filename, lineno):
                        newmsg = substitute_values(msg, action, matches,
                            pkg_attrs, filename, lineno, quote=True)

                        if not newmsg.strip() or newmsg.strip()[0] == "#":
                                return (newmsg, action)
                        try:
                                return (pkg.actions.fromstr(newmsg), action)
                        except (pkg.actions.MalformedActionError,
                            pkg.actions.UnknownActionError,
                            pkg.actions.InvalidActionError) as e:
                                raise RuntimeError(e)

                operation = emit_func

        else:
                raise RuntimeError(_("unknown transform operation '{0}'").format(op[0]))

        transforms.append((types, attrdict, operation, filename, lineno, transform))

def substitute_values(msg, action, matches, pkg_attrs, filename=None, lineno=None, quote=False):
        """Substitute tokens in messages which can be expanded to the action's
        attribute values."""

        newmsg = ""
        prevend = 0
        for i in re.finditer("%\((.+?)\)|%\{(.+?)\}", msg):
                m = i.string[slice(*i.span())]
                assert m[1] in "({"
                if m[1] == "(":
                        group = 1
                elif m[1] == "{":
                        group = 2
                d = {}
                if ";" in i.group(group):
                        attrname, args = i.group(group).split(";", 1)
                        tokstream = shlex.shlex(args)
                        for tok in tokstream:
                                if tok == ";":
                                        tok = tokstream.get_token()
                                eq = tokstream.get_token()
                                if eq == "" or eq == ";":
                                        val = True
                                else:
                                        assert(eq == "=")
                                        val = tokstream.get_token()
                                        if ('"', '"') == (val[0], val[-1]):
                                                val = val[1:-1]
                                        elif ("'", "'") == (val[0], val[-1]):
                                                val = val[1:-1]
                                d[tok] = val
                else:
                        attrname = i.group(group)

                d.setdefault("quote", quote)

                if d.get("noquote", None):
                        d["quote"] = False

                if group == 2:
                        attr = pkg_attrs.get(attrname, d.get("notfound", None))
                        if attr and len(attr) == 1:
                                attr = attr[0]
                else:
                        if attrname == "pkg.manifest.lineno":
                                attr = str(lineno)
                        elif attrname == "pkg.manifest.filename":
                                attr = str(filename)
                        elif attrname == "action.hash":
                                attr = getattr(action, "hash",
                                    d.get("notfound", None))
                        elif attrname == "action.key":
                                attr = action.attrs.get(action.key_attr,
                                    d.get("notfound", None))
                        elif attrname == "action.name":
                                attr = action.name
                        else:
                                attr = action.attrs.get(attrname,
                                    d.get("notfound", None))

                if attr is None:
                        raise RuntimeError(_("attribute '{0}' not found").format(
                            attrname))

                def q(s):
                        if " " in s or "'" in s or "\"" in s or s == "":
                                if "\"" not in s:
                                        return '"{0}"'.format(s)
                                elif "'" not in s:
                                        return "'{0}'".format(s)
                                else:
                                        return '"{0}"'.format(s.replace("\"", "\\\""))
                        else:
                                return s

                if not d["quote"]:
                        q = lambda x: x

                if isinstance(attr, six.string_types):
                        newmsg += msg[prevend:i.start()] + \
                            d.get("prefix", "") + q(attr) + d.get("suffix", "")
                else:
                        newmsg += msg[prevend:i.start()] + \
                            d.get("sep", " ").join([
                                d.get("prefix", "") + q(v) + d.get("suffix", "")
                                for v in attr
                            ])
                prevend = i.end()

        newmsg += msg[prevend:]

        # Now see if there are any backreferences to match groups
        msg = newmsg
        newmsg = ""
        prevend = 0
        backrefs = sum((
            group
            for group in (
                match.groups()
                for match in matches
                if match.groups()
            )
        ), (None,))
        for i in re.finditer(r"%<\d>", msg):
                ref = int(i.string[slice(*i.span())][2:-1])

                if ref == 0 or ref > len(backrefs) - 1:
                        raise RuntimeError(_("no match group {group:d} "
                            "(max {maxgroups:d})").format(
                            group=ref, maxgroups=len(backrefs) - 1))
                if backrefs[ref] is None:
                        raise RuntimeError(_("Error\nInvalid backreference: "
                            "%<{ref}> refers to an unmatched string"
                            ).format(ref=ref))
                newmsg += msg[prevend:i.start()] + backrefs[ref]
                prevend = i.end()

        newmsg += msg[prevend:]
        return newmsg

def attrval_as_list(attrdict, key):
        """Return specified attribute as list;
        an empty list if no such attribute exists"""
        if key not in attrdict:
                return []
        val = attrdict[key]
        if not isinstance(val, list):
                val = [val]
        return val

class PkgAction(pkg.actions.generic.Action):
        name = "pkg"
        def __init__(self, attrs):
                self.attrs = attrs

def apply_transforms(action, pkg_attrs, verbose, act_filename, act_lineno):
        """Apply all transforms to action, returning modified action
        or None if action is dropped"""
        comments = []
        newactions = []
        if verbose:
                comments.append("#  Action: {0}".format(action))
        for types, attrdict, operation, filename, lineno, transform in transforms:
                if action is None:
                        action = PkgAction(pkg_attrs)
                # skip if types are specified and none match
                if types and action.name not in types:
                        continue
                # skip if some attrs don't exist
                if set(attrdict.keys()) - set(action.attrs.keys()):
                        continue

                # Check to make sure all matching attrs actually match.  The
                # order is effectively arbitrary, since they come from a dict.
                matches = [
                    attrdict[key].match(attrval)
                    for key in attrdict
                    for attrval in attrval_as_list(action.attrs, key)
                ]

                if not all(matches):
                        continue

                s = transform[11:transform.index("->")]
                # Map each pattern to its position in the original match string.
                matchorder = {}
                for attr, match in six.iteritems(attrdict):
                        # Attributes might be quoted even if they don't need it,
                        # and lead to a mis-match.  These three patterns are all
                        # safe to try.  If we fail to find the match expression,
                        # it's probably because it used different quoting rules
                        # than the action code does, or from these three rules.
                        # It might very well be okay, so we go ahead, but these
                        # oddly quoted patterns will sort at the beginning, and
                        # backref matching may be off.
                        matchorder[match.pattern] = -1
                        for qs in ("{0}={1}", "{0}=\"{1}\"", "{0}='{1}'"):
                                pos = s.find(qs.format(attr, match.pattern))
                                if pos != -1:
                                        matchorder[match.pattern] = pos
                                        break

                # Then sort the matches list by those positions.
                matches.sort(key=lambda x: matchorder[x.re.pattern])

                # time to apply transform operation
                try:
                        if verbose:
                                orig_attrs = action.attrs.copy()
                        action = operation(action, matches, pkg_attrs,
                            act_filename, act_lineno)
                except RuntimeError as e:
                        raise RuntimeError("Transform specified in file {0}, line {1} reports {2}".format(
                            filename, lineno, e))
                if isinstance(action, tuple):
                        newactions.append(action[0])
                        action = action[1]
                if verbose:
                        if not action or \
                            not isinstance(action, six.string_types) and \
                            orig_attrs != action.attrs:
                                comments.append("# Applied: {0} (file {1} line {2})".format(
                                    transform, filename, lineno))
                                comments.append("#  Result: {0}".format(action))
                if not action or isinstance(action, six.string_types):
                        break

        # Any newly-created actions need to have the transforms applied, too.
        newnewactions = []
        for act in newactions:
                if not isinstance(act, six.string_types):
                        c, al = apply_transforms(act, pkg_attrs, verbose,
                            act_filename, act_lineno)
                        if c:
                                comments.append(c)
                        newnewactions += [a for a in al if a is not None]
                else:
                        newnewactions.append(act)

        if len(comments) == 1:
                comments = []

        if action and action.name != "pkg":
                return (comments, [action] + newnewactions)
        else:
                return (comments, [None] + newnewactions)


def searching_open(filename, try_cwd=False):
        """ implement include hierarchy """

        if filename.startswith("/") or try_cwd == True and \
            os.path.exists(filename):
                try:
                        return filename, open(filename)
                except IOError as e:
                        raise RuntimeError(_("Cannot open file: {0}").format(e))

        for i in includes:
                f = os.path.join(i, filename)
                if os.path.exists(f):
                        try:
                                return f, open(f)
                        except IOError as e:
                                raise RuntimeError(_("Cannot open file: {0}").format(e))

        raise RuntimeError(_("File not found: \'{0}\'").format(filename))

def apply_macros(s):
        """Apply macro subs defined on command line... keep applying
        macros until no translations are found."""
        while s and "$(" in s:
                for key in macros.keys():
                        if key in s:
                                value = macros[key]
                                s = s.replace(key, value)
                                break # look for more substitutions
                else:
                        break # no more substitutable tokens
        return s

def read_file(tp, ignoreincludes):
        """ return the lines in the file as a list of
        tuples containing (line, filename, line number);
        handle continuation and <include "path">"""
        ret = []
        filename, f = tp

        accumulate = ""
        for lineno, line in enumerate(f):
                lineno = lineno + 1 # number from 1
                line = line.strip()
                if not line: # preserve blanks
                        ret.append((line, filename, lineno))
                        continue
                if line.endswith("\\"):
                        accumulate += line[0:-1]
                        continue
                elif accumulate:
                        line = accumulate + line
                        accumulate = ""

                if line:
                        line = apply_macros(line)

                line = line.strip()

                if not line:
                        continue

                try:
                        if line.startswith("<") and line.endswith(">"):
                                if line.startswith("<include"):
                                        if not ignoreincludes:
                                                line = line[1:-1]
                                                line = line[7:].strip()
                                                line = line.strip('"')
                                                ret.extend(read_file(
                                                    searching_open(line),
                                                    ignoreincludes))
                                        else:
                                                ret.append((line, filename, lineno))
                                elif line.startswith("<transform"):
                                        line = line[1:-1]
                                        add_transform(line, filename, lineno)
                                else:
                                        raise RuntimeError(_("unknown command {0}").format(
                                                line))
                        else:
                                ret.append((line, filename, lineno))
                except RuntimeError as e:
                        error(_("File {file}, line {line:d}: {exception}").format(
                            file=filename,
                            line=lineno,
                            exception=e),
                            exitcode=None)
                        raise RuntimeError("<included from>")

        return ret

def error(text, exitcode=EXIT_OOPS):
        """Emit an error message prefixed by the command name """

        print("pkgmogrify: {0}".format(text), file=sys.stderr)
        if exitcode != None:
                sys.exit(exitcode)

def main_func():
        outfilename = None
        printfilename = None
        verbose = False
        ignoreincludes = False

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "ivD:I:O:P:?", ["help"])
                for opt, arg in opts:
                        if opt == "-D":
                                if "=" not in arg:
                                        error(_("macros must be of form name=value"))
                                a = arg.split("=", 1)
                                if a[0] == "":
                                        error(_("macros must be of form name=value"))
                                macros.update([("$({0})".format(a[0]), a[1])])
                        if opt == "-i":
                                ignoreincludes = True
                        if opt == "-I":
                                includes.append(arg)
                        if opt == "-O":
                                outfilename = arg
                        if opt == "-P":
                                printfilename = arg
                        if opt == "-v":
                                verbose = True
                        if opt in ("--help", "-?"):
                                usage(exitcode=EXIT_OK)

        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))

        try:
                if pargs:
                        infiles = [ searching_open(f, try_cwd=True) for f in pargs ]
                else:
                        infiles =  [("<stdin>", sys.stdin)]

                lines = []
        except RuntimeError as e:
                error(_("Error processing input arguments: {0}").format(e))
        try:
                for f in infiles:
                        lines.extend(read_file(f, ignoreincludes))
                        lines.append((None, f[0], None))
        except RuntimeError as e:
                sys.exit(EXIT_OOPS)

        output = []

        pkg_attrs = {}
        for line, filename, lineno in lines:
                if line is None:
                        if "pkg.fmri" in pkg_attrs:
                                comment, a = apply_transforms(None, pkg_attrs,
                                    verbose, filename, lineno)
                                output.append((comment, a, None))
                        pkg_attrs = {}
                        continue

                if not line or line.startswith("#") or line.startswith("<"):
                        output.append(([line], [], None))
                        continue

                if line.startswith("$("): #prepended unexpanded macro
                        # doesn't handle nested macros
                        eom = line.index(")") + 1
                        prepended_macro = line[0:eom]
                        line = line[eom:]
                else:
                        prepended_macro = None

                try:
                        act = pkg.actions.fromstr(line)
                except (pkg.actions.MalformedActionError,
                    pkg.actions.UnknownActionError,
                    pkg.actions.InvalidActionError) as e:
                        error("File {0} line {1:d}: {2}".format(filename, lineno, e))
                try:
                        if act.name == "set":
                                name = act.attrs["name"]
                                value = act.attrs["value"]
                                if isinstance(value, six.string_types):
                                        pkg_attrs.setdefault(name, []).append(value)
                                else:
                                        pkg_attrs.setdefault(name, []).extend(value)
                        comment, a = apply_transforms(act, pkg_attrs, verbose,
                            filename, lineno)
                        output.append((comment, a, prepended_macro))
                except RuntimeError as e:
                        error("File {0} line {1:d}: {2}".format(filename, lineno, e))

        try:
                if printfilename == None:
                        printfile = sys.stdout
                else:
                        printfile = open(printfilename, "w")

                for p in printinfo:
                        print("{0}".format(p), file=printfile)

        except IOError as e:
                error(_("Cannot write extra data {0}").format(e))

        try:
                if outfilename == None:
                        outfile = sys.stdout
                else:
                        outfile = open(outfilename, "w")

                emitted = set()
                for comment, actionlist, prepended_macro in output:
                        if comment:
                                for l in comment:
                                        print("{0}".format(l), file=outfile)

                        for i, action in enumerate(actionlist):
                                if action is None:
                                        continue
                                if prepended_macro is None:
                                        s = "{0}".format(action)
                                else:
                                        s = "{0}{1}".format(prepended_macro, action)
                                # The first action is the original action and
                                # should be printed; later actions are all
                                # emitted and should only be printed if not
                                # duplicates.
                                if i == 0:
                                        print(s, file=outfile)
                                elif s not in emitted:
                                        print(s, file=outfile)
                                        emitted.add(s)
        except IOError as e:
                error(_("Cannot write output {0}").format(e))

        return 0

if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())
        misc.set_fd_limits(printer=error)

        # Make all warnings be errors.
        warnings.simplefilter('error')

        try:
                exit_code = main_func()
        except (PipeError, KeyboardInterrupt):
                exit_code = EXIT_OOPS
        except SystemExit as __e:
                exit_code = __e
        except Exception as __e:
                traceback.print_exc()
                error(misc.get_traceback_message(), exitcode=None)
                exit_code = 99

        sys.exit(exit_code)
