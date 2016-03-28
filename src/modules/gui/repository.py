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
# Copyright (c) 2008, 2011 Oracle and/or its affiliates. All rights reserved.
#

MODIFY_DIALOG_WIDTH_DEFAULT = 580
MODIFY_DIALOG_SSL_WIDTH_DEFAULT = 490

MODIFY_NOTEBOOK_GENERAL_PAGE = 0
MODIFY_NOTEBOOK_CERTIFICATE_PAGE = 1
MODIFY_NOTEBOOK_SIG_POLICY_PAGE = 2

PUBCERT_APPROVED_STR = _("Approved")
PUBCERT_REVOKED_STR = _("Revoked")
PUBCERT_NOTSET_HASH = "HASH-NOTSET" #No L10N required
PUBCERT_NOTAVAILABLE = _("Not available")

import sys
import os
import pango
import datetime
import tempfile
import M2Crypto as m2
import errno
from threading import Thread
from gettext import ngettext

try:
        import gobject
        gobject.threads_init()
        import gtk
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)

import pkg.client.publisher as publisher
import pkg.client.api_errors as api_errors
import pkg.gui.enumerations as enumerations
import pkg.gui.misc as gui_misc
import pkg.gui.progress as progress
from pkg.client import global_settings

logger = global_settings.logger

ERROR_FORMAT = "<span color = \"red\">%s</span>"

class Repository(progress.GuiProgressTracker):
        def __init__(self, parent, image_directory, action = -1,
            webinstall_new = False, main_window = None, gconf = None):
                progress.GuiProgressTracker.__init__(self)
                self.parent = parent
                self.gconf = gconf
                self.action = action
                self.main_window = main_window
                self.api_o = gui_misc.get_api_object(image_directory,
                    self, main_window)
                if self.api_o == None:
                        return
                self.webinstall_new = webinstall_new
                self.progress_stop_thread = False
                self.repository_selection = None
                self.cancel_progress_thread = False
                self.cancel_function = None
                self.is_alias_valid = True
                self.is_url_valid = False
                self.new_pub = None
                self.priority_changes = []
                self.url_err = None
                self.name_error = None
                self.publisher_info = _("e.g. http://pkg.oracle.com/solaris/release")
                self.publishers_list = None
                self.repository_modify_publisher = None
                self.no_changes = 0
                self.pylintstub = None
                builder = gtk.Builder()
                builder.add_from_file(self.parent.gladefile)
                # Dialog reused in the beadmin.py
                self.w_confirmation_dialog =  \
                    builder.get_object("confirmationdialog")
                self.w_confirmation_label = \
                    builder.get_object("confirm_label")
                self.w_confirmation_dialog.set_icon(self.parent.window_icon)
                self.w_confirmation_textview = \
                    builder.get_object("confirmtext")
                self.w_confirm_cancel_btn = builder.get_object("cancel_conf")
                self.w_confirm_ok_btn = builder.get_object("ok_conf")
                confirmbuffer = self.w_confirmation_textview.get_buffer()
                confirmbuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                self.w_confirmation_dialog.set_title(
                    _("Manage Publishers Confirmation"))
                self.w_publishers_treeview = \
                    builder.get_object("publishers_treeview")
                self.w_add_publisher_dialog = \
                    builder.get_object("add_publisher")
                self.w_add_publisher_dialog.set_icon(self.parent.window_icon)
                self.w_add_error_label = \
                    builder.get_object("add_error_label")
                self.w_add_sslerror_label = \
                    builder.get_object("add_sslerror_label")
                self.w_publisher_add_button = \
                    builder.get_object("add_button")
                self.w_publisher_add_cancel_button = \
                    builder.get_object("add_publisher_cancel_button")
                self.w_ssl_box = \
                    builder.get_object("ssl_box")
                self.w_add_publisher_alias = \
                    builder.get_object("add_publisher_alias")
                self.w_add_pub_label = \
                    builder.get_object("add_pub_label")
                self.w_add_pub_instr_label = \
                    builder.get_object("add_pub_instr_label")
                self.w_add_publisher_url = \
                    builder.get_object("add_publisher_url")
                self.w_cert_entry = \
                    builder.get_object("certentry")
                self.w_key_entry = \
                    builder.get_object("keyentry")
                self.w_certbrowse_button = \
                    builder.get_object("certbrowse")
                self.w_keybrowse_button = \
                    builder.get_object("keybrowse")
                self.w_add_pub_help_button = \
                    builder.get_object("add_pub_help")
                self.w_publisher_add_button.set_sensitive(False)
                self.w_add_publisher_comp_dialog = \
                    builder.get_object("add_publisher_complete")
                self.w_add_image = \
                    builder.get_object("add_image")
                self.w_add_publisher_comp_dialog.set_icon(self.parent.window_icon)
                self.w_add_publisher_c_name = \
                    builder.get_object("add_publisher_name_c")
                self.w_add_publisher_c_alias = \
                    builder.get_object("add_publisher_alias_c")
                self.w_add_publisher_c_alias_l = \
                    builder.get_object("add_publisher_alias_l")
                self.w_add_publisher_c_url = \
                    builder.get_object("add_publisher_url_c")
                self.w_add_publisher_c_desc = \
                    builder.get_object("add_publisher_desc_c")
                self.w_add_publisher_c_desc_l = \
                    builder.get_object("add_publisher_desc_l")
                self.w_add_publisher_c_close = \
                    builder.get_object("add_publisher_c_close")
                self.w_registration_box = \
                    builder.get_object("add_registration_box")
                self.w_registration_link = \
                    builder.get_object("registration_button")
                self.w_modify_repository_dialog = \
                    builder.get_object("modify_repository")
                self.w_modify_repository_dialog.set_icon(self.parent.window_icon)
                self.w_modkeybrowse = \
                    builder.get_object("modkeybrowse")
                self.w_modcertbrowse = \
                    builder.get_object("modcertbrowse")
                self.w_addmirror_entry = \
                    builder.get_object("addmirror_entry")
                self.w_addorigin_entry = \
                    builder.get_object("add_repo")
                self.w_addmirror_button = \
                    builder.get_object("addmirror_button")
                self.w_rmmirror_button = \
                    builder.get_object("mirrorremove")
                self.w_addorigin_button = \
                    builder.get_object("pub_add_repo")
                self.w_rmorigin_button = \
                    builder.get_object("pub_remove_repo")
                self.w_modify_pub_alias = \
                    builder.get_object("repositorymodifyalias")
                self.w_repositorymodifyok_button = \
                    builder.get_object("repositorymodifyok")
                self.w_repositorymodifycancel_button = \
                    builder.get_object("repositorymodifycancel")
                self.w_repositorymodifyhelp_button = \
                    builder.get_object("modify_repo_help")
                self.modify_repo_mirrors_treeview = \
                    builder.get_object("modify_repo_mirrors_treeview")
                self.modify_repo_origins_treeview = \
                    builder.get_object("modify_pub_repos_treeview")
                self.w_modmirrerror_label = \
                    builder.get_object("modmirrerror_label")
                self.w_modoriginerror_label = \
                    builder.get_object("modrepoerror_label")
                self.w_modsslerror_label = \
                    builder.get_object("modsslerror_label")
                self.w_repositorymodify_name = \
                    builder.get_object("repository_name_label")
                self.w_repositorymodify_registration_link = \
                    builder.get_object(
                    "repositorymodifyregistrationlinkbutton")
                self.w_repositorymirror_expander = \
                    builder.get_object(
                    "repositorymodifymirrorsexpander")
                self.w_repositorymodify_registration_box = \
                    builder.get_object("modify_registration_box")   
                self.w_repositorymodify_key_entry = \
                    builder.get_object("modkeyentry")   
                self.w_repositorymodify_cert_entry = \
                    builder.get_object("modcertentry")   
                self.w_manage_publishers_dialog = \
                    builder.get_object("manage_publishers")
                self.w_manage_publishers_dialog.set_icon(self.parent.window_icon)
                self.w_manage_publishers_details = \
                    builder.get_object("manage_publishers_details")
                self.w_manage_publishers_details.set_wrap_mode(gtk.WRAP_WORD)
                manage_pub_details_buf =  self.w_manage_publishers_details.get_buffer()
                manage_pub_details_buf.create_tag("level0", weight=pango.WEIGHT_BOLD)
                self.w_manage_add_btn =  builder.get_object("manage_add")
                self.w_manage_ok_btn =  builder.get_object("manage_ok")
                self.w_manage_remove_btn = builder.get_object("manage_remove")
                self.w_manage_modify_btn = \
                    builder.get_object("manage_modify")
                self.w_manage_up_btn = \
                    builder.get_object("manage_move_up")
                self.w_manage_down_btn = \
                    builder.get_object("manage_move_down")
                self.w_manage_cancel_btn = \
                    builder.get_object("manage_cancel")
                self.w_manage_help_btn = \
                    builder.get_object("manage_help")
                    
                self.publishers_apply = \
                    builder.get_object("publishers_apply")
                self.publishers_apply.set_icon(self.parent.window_icon)
                self.publishers_apply_expander = \
                    builder.get_object("apply_expander")
                self.publishers_apply_textview = \
                    builder.get_object("apply_textview")
                applybuffer = self.publishers_apply_textview.get_buffer()
                applybuffer.create_tag("level1", left_margin=30, right_margin=10)
                self.publishers_apply_cancel = \
                    builder.get_object("apply_cancel")
                self.publishers_apply_progress = \
                    builder.get_object("publishers_apply_progress")

                self.w_modify_alias_error_label = builder.get_object(
                        "mod_alias_error_label")
                self.w_pub_cert_treeview = \
                    builder.get_object("pub_certificate_treeview")
                self.w_modify_pub_notebook = builder.get_object(
                        "modify_pub_notebook")
                self.w_pub_cert_details_textview = builder.get_object(
                        "pub_certificate_details_textview")
                manage_pub_cert_details_buf =  \
                        self.w_pub_cert_details_textview.get_buffer()
                manage_pub_cert_details_buf.create_tag("level0",
                    weight=pango.WEIGHT_BOLD)
                manage_pub_cert_details_buf.create_tag("bold",
                    weight=pango.WEIGHT_BOLD)
                manage_pub_cert_details_buf.create_tag("normal",
                    weight=pango.WEIGHT_NORMAL)
                self.w_pub_cert_label = \
                    builder.get_object("mods_pub_label")
                self.w_pub_cert_add_btn =  builder.get_object(
                    "pub_certificate_add_button")
                self.w_pub_cert_remove_btn =  builder.get_object(
                    "pub_certificate_remove_button")
                self.w_pub_cert_revoke_btn =  builder.get_object(
                    "pub_certificate_revoke_button")
                self.w_pub_cert_reinstate_btn =  builder.get_object(
                    "pub_certificate_reinstate_button")


                self.w_pub_sig_ignored_radiobutton =  builder.get_object(
                    "sig_ignored_radiobutton")
                self.w_pub_sig_optional_radiobutton =  builder.get_object(
                    "sig_optional_but_valid_radiobutton")
                self.w_pub_sig_valid_radiobutton =  builder.get_object(
                    "sig_valid_radiobutton")
                self.w_pub_sig_name_radiobutton =  builder.get_object(
                    "sig_name_radiobutton")
                self.w_pub_sig_name_entry =  builder.get_object(
                    "sig_name_entry")
                self.w_pub_sig_view_globpol_button =  builder.get_object(
                    "sig_view_globpol_button")
                self.w_pub_sig_cert_names_vbox =  builder.get_object(
                    "sig_cert_names_vbox")

                checkmark_icon = gui_misc.get_icon(
                    self.parent.icon_theme, "pm-check", 24)

                self.w_add_image.set_from_pixbuf(checkmark_icon)

                self.__setup_signals()

                self.publishers_list = self.__get_publishers_liststore()
                self.__init_pubs_tree_view(self.publishers_list)
                self.__init_mirrors_tree_view(self.modify_repo_mirrors_treeview)
                self.__init_origins_tree_view(self.modify_repo_origins_treeview)

                self.pub_cert_list = self.__get_pub_cert_liststore()
                self.orig_pub_cert_added_dict = {}  # Orig Pub Certs added to model:
                                                    # - key/val: [ips-hash] = status
                self.all_pub_cert_added_dict = {}   # New/ Orig Pub Certs added to model
                                                    # - key/val: [sha-hash] = ips-hash
                self.removed_orig_pub_cert_dict = {}# Removed Orig Pub Certs from model
                                                    # - key/val: [sha-hash] = ips-hash
                self.orig_sig_policy = {}
                self.pub_certs_setup = False
                
                if self.action == enumerations.ADD_PUBLISHER:
                        gui_misc.set_modal_and_transient(self.w_add_publisher_dialog, 
                            self.main_window)
                        self.__on_manage_add_clicked(None)
                        return
                elif self.action == enumerations.MANAGE_PUBLISHERS:
                        gui_misc.set_modal_and_transient(self.w_manage_publishers_dialog,
                            self.main_window)
                        gui_misc.set_modal_and_transient(self.w_confirmation_dialog,
                            self.w_manage_publishers_dialog)
                        self.__prepare_publisher_list()
                        publisher_selection = self.w_publishers_treeview.get_selection()
                        publisher_selection.set_mode(gtk.SELECTION_SINGLE)
                        publisher_selection.connect("changed",
                            self.__on_publisher_selection_changed, None)
                        mirrors_selection = \
                            self.modify_repo_mirrors_treeview.get_selection()
                        mirrors_selection.set_mode(gtk.SELECTION_SINGLE)
                        mirrors_selection.connect("changed",
                            self.__on_mirror_selection_changed, None)
                        origins_selection = \
                            self.modify_repo_origins_treeview.get_selection()
                        origins_selection.set_mode(gtk.SELECTION_SINGLE)
                        origins_selection.connect("changed",
                            self.__on_origin_selection_changed, None)

                        gui_misc.set_modal_and_transient(self.w_add_publisher_dialog,
                            self.w_manage_publishers_dialog)
                        self.__init_pub_cert_tree_view(self.pub_cert_list)
                        self.w_manage_publishers_dialog.show_all()
                        return


        def __setup_signals(self):
                signals_table = [
                    (self.w_add_publisher_dialog, "delete_event",
                     self.__on_add_publisher_delete_event),
                    (self.w_add_publisher_url, "changed",
                     self.__on_publisherurl_changed),
                    (self.w_add_publisher_url, "activate",
                     self.__on_add_publisher_add_clicked),
                    (self.w_add_publisher_alias, "changed",
                     self.__on_publisheralias_changed),
                    (self.w_add_publisher_alias, "activate",
                     self.__on_add_publisher_add_clicked),
                    (self.w_publisher_add_button, "clicked",
                     self.__on_add_publisher_add_clicked),
                    (self.w_key_entry, "changed", self.__on_keyentry_changed),
                    (self.w_cert_entry, "changed", self.__on_certentry_changed),
                    (self.w_publisher_add_cancel_button, "clicked",
                     self.__on_add_publisher_cancel_clicked),
                    (self.w_keybrowse_button, "clicked",
                     self.__on_keybrowse_clicked),
                    (self.w_certbrowse_button, "clicked",
                     self.__on_certbrowse_clicked),
                    (self.w_add_pub_help_button, "clicked",
                     self.__on_add_pub_help_clicked),

                    (self.w_add_publisher_comp_dialog, "delete_event", 
                     self.__on_add_publisher_complete_delete_event),
                    (self.w_add_publisher_c_close, "clicked", 
                     self.__on_add_publisher_c_close_clicked),

                    (self.w_manage_publishers_dialog, "delete_event", 
                     self.__on_manage_publishers_delete_event),
                    (self.w_manage_add_btn, "clicked", 
                     self.__on_manage_add_clicked),
                    (self.w_manage_modify_btn, "clicked", 
                     self.__on_manage_modify_clicked),
                    (self.w_manage_remove_btn, "clicked", 
                     self.__on_manage_remove_clicked),
                    (self.w_manage_up_btn, "clicked", 
                     self.__on_manage_move_up_clicked),
                    (self.w_manage_down_btn, "clicked", 
                     self.__on_manage_move_down_clicked),
                    (self.w_manage_cancel_btn, "clicked", 
                     self.__on_manage_cancel_clicked),
                    (self.w_manage_ok_btn, "clicked", 
                     self.__on_manage_ok_clicked),
                    (self.w_manage_help_btn, "clicked", 
                     self.__on_manage_help_clicked),

                    (self.w_modify_repository_dialog, "delete_event", 
                     self.__on_modifydialog_delete_event),
                    (self.w_modify_pub_alias, "changed",
                     self.__on_modify_pub_alias_changed),
                    (self.w_modkeybrowse, "clicked", 
                     self.__on_modkeybrowse_clicked),
                    (self.w_modcertbrowse, "clicked", 
                     self.__on_modcertbrowse_clicked),
                    (self.w_addmirror_entry, "changed", 
                     self.__on_addmirror_entry_changed),
                    (self.w_addorigin_entry, "changed", 
                     self.__on_addorigin_entry_changed),
                    (self.w_addmirror_button, "clicked", 
                     self.__on_addmirror_button_clicked),
                    (self.w_addorigin_button, "clicked", 
                     self.__on_addorigin_button_clicked),
                    (self.w_rmmirror_button, "clicked", 
                     self.__on_rmmirror_button_clicked),
                    (self.w_rmorigin_button, "clicked", 
                     self.__on_rmorigin_button_clicked),
                    (self.w_repositorymodify_key_entry, "changed", 
                     self.__on_modcertkeyentry_changed),
                    (self.w_repositorymodify_cert_entry, "changed", 
                     self.__on_modcertkeyentry_changed),
                    (self.w_repositorymodifyok_button, "clicked",
                     self.__on_repositorymodifyok_clicked),
                    (self.w_repositorymodifycancel_button, "clicked",
                     self.__on_repositorymodifycancel_clicked),
                    (self.w_repositorymodifyhelp_button, "clicked",
                     self.__on_modify_repo_help_clicked),

                    (self.w_confirmation_dialog, "delete_event",
                        self.__delete_widget_handler_hide),
                    (self.w_confirm_cancel_btn, "clicked", 
                        self.__on_cancel_conf_clicked),
                    (self.w_confirm_ok_btn, "clicked", 
                        self.__on_ok_conf_clicked),

                    (self.publishers_apply, "delete_event",
                     self.__on_publishers_apply_delete_event),
                    (self.publishers_apply_cancel, "clicked",
                     self.__on_apply_cancel_clicked),

                    (self.w_pub_cert_add_btn, "clicked",
                        self.__on_pub_cert_add_clicked),
                    (self.w_pub_cert_remove_btn, "clicked",
                        self.__on_pub_cert_remove_clicked),
                    (self.w_pub_cert_revoke_btn, "clicked",
                        self.__on_pub_cert_revoke_clicked),
                    (self.w_pub_cert_reinstate_btn, "clicked",
                        self.__on_pub_cert_reinstate_clicked),
                    (self.w_modify_pub_notebook, "switch_page",
                     self.__on_notebook_change),

                    (self.w_pub_sig_ignored_radiobutton, "toggled",
                        self.__on_pub_sig_radiobutton_toggled),
                    (self.w_pub_sig_optional_radiobutton, "toggled",
                        self.__on_pub_sig_radiobutton_toggled),
                    (self.w_pub_sig_valid_radiobutton, "toggled",
                        self.__on_pub_sig_radiobutton_toggled),
                    (self.w_pub_sig_name_radiobutton, "toggled",
                        self.__on_pub_sig_radiobutton_toggled),
                    (self.w_pub_sig_view_globpol_button, "clicked",
                        self.__on_pub_sig_view_globpol_clicked),
                    ]
                for widget, signal_name, callback in signals_table:
                        widget.connect(signal_name, callback)

        def __on_pub_sig_radiobutton_toggled(self, widget):
                self.w_pub_sig_cert_names_vbox.set_sensitive(
                    self.w_pub_sig_name_radiobutton.get_active())

        def __on_pub_sig_view_globpol_clicked(self, widget):
                #Preferences Dialog is modal so no need to hide the Modify Dialog
                self.parent.preferences.show_signature_policy()
        
        def __update_pub_sig_policy_prop(self, set_props):
                errors = []
                try:
                        pub = self.repository_modify_publisher
                        if pub != None:
                                pub.update_props(set_props=set_props)
                except api_errors.ApiException, e:
                        errors.append(("", e))
                return errors

        def __update_pub_sig_policy(self):
                errors = []
                orig = self.orig_sig_policy
                if not orig:
                        return errors
                ignore = self.w_pub_sig_ignored_radiobutton.get_active()
                verify = self.w_pub_sig_optional_radiobutton.get_active()
                req_sigs = self.w_pub_sig_valid_radiobutton.get_active()
                req_names = self.w_pub_sig_name_radiobutton.get_active()
                names = gui_misc.fetch_signature_policy_names_from_textfield(
                    self.w_pub_sig_name_entry.get_text())
                set_props = gui_misc.setup_signature_policy_properties(ignore,
                    verify, req_sigs, req_names, names, orig)
                if len(set_props) > 0:
                        errors = self.__update_pub_sig_policy_prop(set_props)
                return errors
        
        def __prepare_pub_signature_policy(self):
                if self.orig_sig_policy:
                        return

                sig_policy = self.__fetch_pub_signature_policy()
                self.orig_sig_policy = sig_policy
                self.w_pub_sig_ignored_radiobutton.set_active(
                    sig_policy[gui_misc.SIG_POLICY_IGNORE])
                self.w_pub_sig_optional_radiobutton.set_active(
                    sig_policy[gui_misc.SIG_POLICY_VERIFY])
                self.w_pub_sig_valid_radiobutton.set_active(
                    sig_policy[gui_misc.SIG_POLICY_REQUIRE_SIGNATURES])
                self.w_pub_sig_cert_names_vbox.set_sensitive(False)

                if sig_policy[gui_misc.SIG_POLICY_REQUIRE_NAMES]:
                        self.w_pub_sig_name_radiobutton.set_active(True)
                        self.w_pub_sig_cert_names_vbox.set_sensitive(True)

                names = sig_policy[gui_misc.PROP_SIGNATURE_REQUIRED_NAMES]
                gui_misc.set_signature_policy_names_for_textfield(
                    self.w_pub_sig_name_entry, names)

        def __fetch_pub_signature_policy(self):
                pub = self.repository_modify_publisher
                prop_sig_pol = pub.signature_policy.name
                prop_sig_req_names = None
                if gui_misc.PROP_SIGNATURE_REQUIRED_NAMES in pub.properties:
                        prop_sig_req_names = \
                                pub.properties[gui_misc.PROP_SIGNATURE_REQUIRED_NAMES]
                return gui_misc.create_sig_policy_from_property(
                    prop_sig_pol, prop_sig_req_names)

        def __on_notebook_change(self, widget, event, pagenum):
                if pagenum == MODIFY_NOTEBOOK_CERTIFICATE_PAGE:
                        gobject.idle_add(self.__prepare_pub_certs)
                elif pagenum == MODIFY_NOTEBOOK_SIG_POLICY_PAGE:
                        gobject.idle_add(self.__prepare_pub_signature_policy)

        @staticmethod
        def __get_pub_cert_liststore():
                return gtk.ListStore(
                        gobject.TYPE_STRING,   # enumerations.PUBCERT_ORGANIZATION
                        gobject.TYPE_STRING,   # enumerations.PUBCERT_NAME
                        gobject.TYPE_STRING,   # enumerations.PUBCERT_STATUS
                        gobject.TYPE_STRING,   # enumerations.PUBCERT_IPSHASH
                        gobject.TYPE_STRING,   # enumerations.PUBCERT_PATH
                        gobject.TYPE_PYOBJECT, # enumerations.PUBCERT_XCERT_OBJ
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBCERT_NEW
                        )

        @staticmethod
        def __sort_func(treemodel, iter1, iter2, column):
                col_val1 = treemodel.get_value(iter1, column)
                col_val2 = treemodel.get_value(iter2, column)
                ret = cmp(col_val1, col_val2)
                if ret != 0:
                        return ret
                if column == enumerations.PUBCERT_ORGANIZATION:
                        name1 = treemodel.get_value(iter1,
                            enumerations.PUBCERT_NAME)
                        name2 = treemodel.get_value(iter2,
                            enumerations.PUBCERT_NAME)
                        ret = cmp(name1, name2)
                elif column == enumerations.PUBCERT_NAME:
                        org1 = treemodel.get_value(iter1,
                            enumerations.PUBCERT_ORGANIZATION)
                        org2 = treemodel.get_value(iter2,
                            enumerations.PUBCERT_ORGANIZATION)
                        ret = cmp(org1, org2)
                return ret

        def __init_pub_cert_tree_view(self, pub_cert_list):
                pub_cert_sort_model = gtk.TreeModelSort(pub_cert_list)
                pub_cert_sort_model.set_sort_column_id(enumerations.PUBCERT_ORGANIZATION,
                    gtk.SORT_ASCENDING)

                pub_cert_sort_model.set_sort_func(enumerations.PUBCERT_ORGANIZATION,
                    self.__sort_func,
                    enumerations.PUBCERT_ORGANIZATION)
                pub_cert_sort_model.set_sort_func(enumerations.PUBCERT_NAME,
                    self.__sort_func,
                    enumerations.PUBCERT_NAME)

                # Organization column - sort using custom __sort_func()
                org_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Organization"),
                    org_renderer,  text = enumerations.PUBCERT_ORGANIZATION)
                column.set_expand(False)
                column.set_sort_column_id(enumerations.PUBCERT_ORGANIZATION)
                column.set_sort_indicator(True)
                column.set_resizable(True)
                self.w_pub_cert_treeview.append_column(column)

                # Name column - sort using custom __sort_func()
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Name"),
                    name_renderer,  text = enumerations.PUBCERT_NAME)
                column.set_expand(True)
                column.set_sort_column_id(enumerations.PUBCERT_NAME)
                column.set_sort_indicator(True)
                column.set_resizable(True)
                self.w_pub_cert_treeview.append_column(column)

                # Status column
                status_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Status"),
                    status_renderer,  text = enumerations.PUBCERT_STATUS)
                column.set_expand(False)
                column.set_sort_column_id(enumerations.PUBCERT_STATUS)
                self.w_pub_cert_treeview.append_column(column)

                self.w_pub_cert_treeview.get_selection().connect('changed',
                    self.__on_pub_cert_treeview_changed)
                self.w_pub_cert_treeview.set_model(pub_cert_sort_model)

        @staticmethod
        def __get_pub_display_name(pub):
                display_name = ""
                if not pub:
                        return display_name

                name = pub.prefix
                alias = pub.alias
                use_name = False
                use_alias = False
                if len(name) > 0:
                        use_name = True
                if alias and len(alias) > 0 and alias != name:
                        use_alias = True

                if use_name and not use_alias:
                        display_name = name
                elif use_name and use_alias:
                        display_name = "%s (%s)" % (name, alias)
                return display_name

        def __prepare_pub_certs(self):
                if self.pub_certs_setup:
                        return

                pub = self.repository_modify_publisher
                if not pub:
                        return
                sorted_model = self.w_pub_cert_treeview.get_model()
                selection = self.w_pub_cert_treeview.get_selection()
                selected_rows = selection.get_selected_rows()
                self.w_pub_cert_treeview.set_model(None)
                if not sorted_model:
                        return
                model = sorted_model.get_model()
                if not model:
                        return
                model.clear()

                self.orig_pub_cert_added_dict.clear() 
                self.all_pub_cert_added_dict.clear() 
                self.removed_orig_pub_cert_dict.clear() 

                pub_display_name = self.__get_pub_display_name(pub)
                if pub_display_name != "":
                        self.w_pub_cert_label.set_markup(
                            _("<b>Certificates for publisher %s</b>") % pub_display_name)
                else:
                        self.w_pub_cert_label.set_markup(
                            _("<b>Publisher certificates</b>"))

                for h in pub.approved_ca_certs:
                        self.__add_cert_to_model(model,
                            pub.get_cert_by_hash(h), h, PUBCERT_APPROVED_STR)
                for h in pub.revoked_ca_certs:
                        self.__add_cert_to_model(model,
                            pub.get_cert_by_hash(h), h, PUBCERT_REVOKED_STR)

                self.w_pub_cert_treeview.set_model(sorted_model)
                if len(pub.revoked_ca_certs) == 0 and len(pub.approved_ca_certs) == 0:
                        self.__set_empty_pub_cert()
                        self.pub_certs_setup = True
                        return

                sel_path = (0,)
                if len(selected_rows) > 1 and len(selected_rows[1]) > 0:
                        sel_path = selected_rows[1][0]
                self.__set_pub_cert_selection(sorted_model, sel_path)
                self.pub_certs_setup = True
                
        def __add_cert_to_model(self, model, cert, ips_hash, status, path = "",
            scroll_to=False, new=False):
                pub = self.repository_modify_publisher
                if not cert or not pub:
                        return
                i = cert.get_subject()
                organization = PUBCERT_NOTAVAILABLE
                if len(i.get_entries_by_nid(i.nid["O"])) > 0:
                        organization = i.get_entries_by_nid(
                            i.nid["O"])[0].get_data().as_text()
                name = PUBCERT_NOTAVAILABLE
                if len(i.get_entries_by_nid(i.nid["CN"])) > 0:
                        name = i.get_entries_by_nid(
                            i.nid["CN"])[0].get_data().as_text()
                if self.all_pub_cert_added_dict.has_key(cert.get_fingerprint('sha1')):
                        err = _("The publisher certificate:\n  %s\n"
                            "has already been added.") % \
                            self.__get_cert_display_name(cert)
                        gui_misc.error_occurred(None, err,
                            _("Modify Publisher - %s") % self.__get_pub_display_name(pub),
                            gtk.MESSAGE_INFO)
                        return

                self.all_pub_cert_added_dict[cert.get_fingerprint('sha1')] = ips_hash
                itr = model.append(
                    [organization, name, status, ips_hash, path, cert, new])
                if not new:
                        self.orig_pub_cert_added_dict[ips_hash] = status

                if scroll_to:
                        path = model.get_path(itr)
                        sorted_model = self.w_pub_cert_treeview.get_model()
                        if not sorted_model:
                                return
                        sorted_path = sorted_model.convert_child_path_to_path(path)
                        self.w_pub_cert_treeview.scroll_to_cell(sorted_path)
                        selection = self.w_pub_cert_treeview.get_selection()
                        selection.select_path(sorted_path)

        def __on_pub_cert_treeview_changed(self, treeselection):
                selection = treeselection.get_selected_rows()
                pathlist = selection[1]
                if not pathlist or len(pathlist) == 0:
                        return
                sorted_model = self.w_pub_cert_treeview.get_model()
                if not sorted_model:
                        return
                model = sorted_model.get_model()
                path = pathlist[0]
                child_path = sorted_model.convert_path_to_child_path(path)
                self.__enable_disable_pub_cert_buttons(model, child_path)
                self.__set_pub_cert_details(model, child_path)

        def __enable_disable_pub_cert_buttons(self, model, path):
                if not model or not path:
                        return
                itr = model.get_iter(path)
                status = model.get_value(itr, enumerations.PUBCERT_STATUS)
                new = model.get_value(itr, enumerations.PUBCERT_NEW)

                if status == PUBCERT_APPROVED_STR:
                        self.w_pub_cert_revoke_btn.set_sensitive(True)
                        self.w_pub_cert_reinstate_btn.set_sensitive(False)
                else:
                        self.w_pub_cert_revoke_btn.set_sensitive(False)
                        self.w_pub_cert_reinstate_btn.set_sensitive(True)
                if new:
                        self.w_pub_cert_revoke_btn.set_sensitive(False)
                        self.w_pub_cert_reinstate_btn.set_sensitive(False)
                self.w_pub_cert_remove_btn.set_sensitive(True)

        def __set_pub_cert_details(self, model, path):
                itr = model.get_iter(path)
                ips_hash = model.get_value(itr, enumerations.PUBCERT_IPSHASH)
                cert = model.get_value(itr, enumerations.PUBCERT_XCERT_OBJ)
                new = model.get_value(itr, enumerations.PUBCERT_NEW)
                if not cert:
                        return
                details_buffer = self.w_pub_cert_details_textview.get_buffer()
                details_buffer.set_text("")
                itr = details_buffer.get_end_iter()

                labs = {}
                labs["issued_to"] = _("Issued To:")
                labs["common_name_to"] = gui_misc.PUBCERT_COMMON_NAME
                labs["org_to"] = gui_misc.PUBCERT_ORGANIZATION
                labs["org_unit_to"] = gui_misc.PUBCERT_ORGANIZATIONAL_UNIT
                labs["issued_by"] = _("Issued By:")
                labs["common_name_by"] = _("  Common Name (CN):")
                labs["org_by"] = gui_misc.PUBCERT_ORGANIZATION
                labs["org_unit_by"] = gui_misc.PUBCERT_ORGANIZATIONAL_UNIT
                labs["validity"] = _("Validity:")
                labs["issued_on"] = _("  Issued On:")
                labs["fingerprints"] = _("Fingerprints:")
                labs["sha1"] = _("  SHA1:")
                labs["md5"] = _("  MD5:")
                labs["ips"] = _("  IPS:")

                text = {}
                text["issued_to"] = ""
                text["common_name_to"] = ""
                text["org_to"] = ""
                text["org_unit_to"] = ""
                text["issued_by"] = ""
                text["common_name_by"] = ""
                text["org_by"] = ""
                text["org_unit_by"] = ""
                text["validity"] = ""
                text["issued_on"] = ""
                text["fingerprints"] = ""
                text["sha1"] = ""
                text["md5"] = ""
                text["ips"] = ""

                self._set_cert_issuer(text, cert.get_subject(), "to")
                self._set_cert_issuer(text, cert.get_issuer(), "by")

                eo = cert.get_not_after().get_datetime().date().isoformat()
                today = datetime.datetime.today().date().isoformat()
                validity_str = _("Validity:")
                #TBD: may have an issue here in some locales if Validity string
                #is very long then would only need one \t.
                if eo < today:
                        validity_str += _("\t\t EXPIRED")
                labs["validity"] = validity_str

                io_str = cert.get_not_before().get_datetime().date().strftime("%x")
                eo_str = cert.get_not_after().get_datetime().date().strftime("%x")
                labs["issued_on"] += " " + io_str
                text["issued_on"] = _("Expires On: %s") % eo_str

                sha = cert.get_fingerprint('sha1')
                md5 = cert.get_fingerprint('md5')
                text["sha1"] = sha.lower()
                text["md5"] = md5.lower()
                text["ips"] = ips_hash.lower()

                added = False
                reinstated = False
                if new:
                        if ips_hash == PUBCERT_NOTSET_HASH:
                                added = True
                                reinstated = False
                        else:
                                reinstated = True
                                added = False

                gui_misc.set_pub_cert_details_text(labs, text,
                    self.w_pub_cert_details_textview, added, reinstated)

        @staticmethod
        def _set_cert_issuer(text, issuer, itype):
                if len(issuer.get_entries_by_nid(issuer.nid["CN"])) > 0:
                        text["common_name_" + itype] = issuer.get_entries_by_nid(
                                issuer.nid["CN"])[0].get_data().as_text()
                if len(issuer.get_entries_by_nid(issuer.nid["O"])) > 0:
                        text["org_" + itype] = issuer.get_entries_by_nid(
                                issuer.nid["O"])[0].get_data().as_text()
                if len(issuer.get_entries_by_nid(issuer.nid["OU"])) > 0:
                        text["org_unit_" + itype] = issuer.get_entries_by_nid(
                                issuer.nid["OU"])[0].get_data().as_text()
                else:
                        text["org_unit_" + itype] = PUBCERT_NOTAVAILABLE

        def __get_pub_cert_filename(self, title, path = None):
                if path == None or path == "":
                        path = tempfile.gettempdir()
                filename = None
                chooser = gtk.FileChooserDialog(title,
                    self.w_manage_publishers_dialog,
                    gtk.FILE_CHOOSER_ACTION_OPEN,
                    (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OK, gtk.RESPONSE_OK))

                file_filter = gtk.FileFilter()
                file_filter.set_name(_("Certificate Files"))
                file_filter.add_pattern("*.pem")
                chooser.add_filter(file_filter)
                chooser.set_current_folder(path)

                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        filename = chooser.get_filename()
                chooser.destroy()

                if filename != None:
                        info = os.path.split(filename)
                        self.gconf.last_add_pubcert_path = info[0]
                return filename

        def __on_pub_cert_add_clicked(self, widget):
                filename = self.__get_pub_cert_filename(
                    _("Add Publisher Certificate"),
                    self.gconf.last_add_pubcert_path)
                if filename == None:
                        return
                try:
                        cert = self.__get_new_cert(filename)
                        sha = cert.get_fingerprint('sha1')
                        ips_hash = PUBCERT_NOTSET_HASH
                        status = PUBCERT_APPROVED_STR
                        new = True
                        #Restore orig cert if it was already added but just removed
                        if self.removed_orig_pub_cert_dict.has_key(sha):
                                ips_hash = self.removed_orig_pub_cert_dict[sha]
                                status = self.orig_pub_cert_added_dict[ips_hash]
                                filename = ""
                                new = False
                                del self.removed_orig_pub_cert_dict[sha]
                        sorted_model = self.w_pub_cert_treeview.get_model()
                        if not sorted_model:
                                return
                        model = sorted_model.get_model()
                        self.__add_cert_to_model(model, cert, ips_hash, status,
                            path=filename, scroll_to=True, new=new) 
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return

        @staticmethod
        def __get_new_cert(filename):
                cert = None
                try:
                        with open(filename, "rb") as fh:
                                s = fh.read()
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                raise api_errors.MissingFileArgumentException(
                                    filename)
                        elif e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    filename)
                        raise api_errors.ApiException(e)
                try:
                        cert = m2.X509.load_cert_string(s)
                except m2.X509.X509Error, e:
                        raise api_errors.BadFileFormat(_("The file:\n"
                            " %s\nwas expected to be a PEM certificate but it "
                            "could not be read.") % filename)
                return cert

        def __on_pub_cert_reinstate_clicked(self, widget):
                itr, sorted_model = self.__get_selected_pub_cert_itr_model()
                if not itr or not sorted_model:
                        return
                model = sorted_model.get_model()
                child_itr = sorted_model.convert_iter_to_child_iter(None, itr)

                ips_hash = model.get_value(child_itr, enumerations.PUBCERT_IPSHASH)
                orig_status = ""
                if self.orig_pub_cert_added_dict.has_key(ips_hash):
                        orig_status = self.orig_pub_cert_added_dict[ips_hash]
                else:
                        #Should not be able to reinstate new cert, only existing ones
                        return
                #Originally approved so just reset as there is nothing to do
                if orig_status == PUBCERT_APPROVED_STR:
                        model.set_value(child_itr,
                            enumerations.PUBCERT_STATUS,
                            PUBCERT_APPROVED_STR)
                        self.__set_pub_cert_details(model,
                            model.get_path(child_itr))
                        self.__enable_disable_pub_cert_buttons(model,
                            model.get_path(child_itr))
                        return

                filename = self.__get_pub_cert_filename(
                    _("Reinstate Publisher Certificate"),
                    self.gconf.last_add_pubcert_path)
                if filename == None:
                        return

                #Check the old cert and new ones match according to the sha fingerprint
                cert = model.get_value(child_itr, enumerations.PUBCERT_XCERT_OBJ)
                new_cert = self.__get_new_cert(filename)
                if cert == None or new_cert == None:
                        #Must have exisitng cert and new one to reinstate
                        return
                orig_sha = cert.get_fingerprint('sha1')
                new_sha = new_cert.get_fingerprint('sha1')
                if orig_sha != new_sha:
                        pub = self.repository_modify_publisher
                        if not pub:
                                return
                        gui_misc.error_occurred(None,
                            _("To reinstate the publisher certificate:\n  %s\n"
                            "the original certificate file must be selected.") %
                            self.__get_cert_display_name(cert),
                            _("Modify Publisher - %s") % self.__get_pub_display_name(pub),
                            gtk.MESSAGE_INFO)
                        return
                #Update model of existing cert which is to be reinstated by
                #re-adding the cert as new
                model.set_value(child_itr, enumerations.PUBCERT_STATUS,
                    PUBCERT_APPROVED_STR)
                model.set_value(child_itr, enumerations.PUBCERT_PATH, filename)
                model.set_value(child_itr, enumerations.PUBCERT_XCERT_OBJ, new_cert)
                model.set_value(child_itr, enumerations.PUBCERT_NEW, True)
                self.__set_pub_cert_details(model, model.get_path(child_itr))
                self.__enable_disable_pub_cert_buttons(model,
                    model.get_path(child_itr))

        @staticmethod
        def __get_cert_display_name(cert):
                cert_display_name = ""
                if cert == None:
                        return cert_display_name
                issuer = cert.get_subject()
                cn = "-"
                org = "-"
                ou = "-"
                if len(issuer.get_entries_by_nid(issuer.nid["CN"])) > 0:
                        cn = issuer.get_entries_by_nid(
                                issuer.nid["CN"])[0].get_data().as_text()
                if len(issuer.get_entries_by_nid(issuer.nid["O"])) > 0:
                        org = issuer.get_entries_by_nid(
                                issuer.nid["O"])[0].get_data().as_text()
                if len(issuer.get_entries_by_nid(issuer.nid["OU"])) > 0:
                        ou = issuer.get_entries_by_nid(
                                issuer.nid["OU"])[0].get_data().as_text()
                else:
                        ou = PUBCERT_NOTAVAILABLE

                if ou != PUBCERT_NOTAVAILABLE:
                        cert_display_name =  \
                                "%s (CN) %s (O) %s (OU)" % (cn, org, ou) #No l10n required
                else:
                        cert_display_name =  "%s (CN) %s (O)" % (cn, org)#No l10n required
                return cert_display_name

        def __on_pub_cert_revoke_clicked(self, widget):
                selection = self.w_pub_cert_treeview.get_selection()
                if not selection:
                        return
                selected_rows = selection.get_selected_rows()
                if not selected_rows or len(selected_rows) < 2:
                        return
                pathlist = selected_rows[1]
                if not pathlist or len(pathlist) == 0:
                        return
                path = pathlist[0]
                self.__revoked(None, path)


        def __revoked(self, cell, sorted_path):
                sorted_model = self.w_pub_cert_treeview.get_model()
                if not sorted_model:
                        return
                model = sorted_model.get_model()
                path = sorted_model.convert_path_to_child_path(sorted_path)
                itr = model.get_iter(path)
                if not itr:
                        return
                status = model.get_value(itr, enumerations.PUBCERT_STATUS)
                if status == PUBCERT_APPROVED_STR:
                        model.set_value(itr, enumerations.PUBCERT_STATUS,
                            PUBCERT_REVOKED_STR)
                        self.__enable_disable_pub_cert_buttons(model, path)
                        self.__set_pub_cert_details(model, path)

        def __on_pub_cert_remove_clicked(self, widget):
                itr, sorted_model = self.__get_selected_pub_cert_itr_model()
                if not itr or not sorted_model:
                        return
                sel_path = sorted_model.get_path(itr)
                model = sorted_model.get_model()
                child_itr = sorted_model.convert_iter_to_child_iter(None, itr)

                cert = model.get_value(child_itr, enumerations.PUBCERT_XCERT_OBJ)
                if self.all_pub_cert_added_dict.has_key(cert.get_fingerprint('sha1')):
                        del self.all_pub_cert_added_dict[cert.get_fingerprint('sha1')]

                new = model.get_value(child_itr, enumerations.PUBCERT_NEW)
                if not new:
                        sha = cert.get_fingerprint('sha1')
                        ips_hash = model.get_value(child_itr,
                            enumerations.PUBCERT_IPSHASH)
                        self.removed_orig_pub_cert_dict[sha] = ips_hash

                model.remove(child_itr)
                self.__set_pub_cert_selection(sorted_model, sel_path)

        def __set_pub_cert_selection(self, sorted_model, sel_path):
                len_smodel = len(sorted_model)
                if len_smodel == 0:
                        self.__set_empty_pub_cert()
                        return
                if len_smodel <= sel_path[0]:
                        sel_path = (len_smodel - 1,)
                if sel_path[0] < 0:
                        sel_path = (0,)

                self.w_pub_cert_treeview.scroll_to_cell(sel_path)
                selection = self.w_pub_cert_treeview.get_selection()
                selection.select_path(sel_path)

        def __set_empty_pub_cert(self):
                details_buffer = self.w_pub_cert_details_textview.get_buffer()
                details_buffer.set_text("")
                self.w_pub_cert_remove_btn.set_sensitive(False)
                self.w_pub_cert_revoke_btn.set_sensitive(False)
                self.w_pub_cert_reinstate_btn.set_sensitive(False)
                
        def __get_selected_pub_cert_itr_model(self):
                return self.__get_fitr_model_from_tree(self.w_pub_cert_treeview)

        def __update_pub_certs(self):
                errors = []
                sorted_model = self.w_pub_cert_treeview.get_model()
                if not sorted_model:
                        return errors
                model = sorted_model.get_model()
                if not model:
                        return errors

                updated_pub_cert_dict = {}
                add_pub_cert_dict = {}
                iter_next = sorted_model.get_iter_first()
                while iter_next != None:
                        itr = sorted_model.convert_iter_to_child_iter(None, iter_next)
                        ips_hash = model.get_value(itr, enumerations.PUBCERT_IPSHASH)
                        status = model.get_value(itr, enumerations.PUBCERT_STATUS)
                        path = model.get_value(itr, enumerations.PUBCERT_PATH)
                        new = model.get_value(itr, enumerations.PUBCERT_NEW)
                        #Both new and reinstated certs treated as new and to be added
                        if new:
                                add_pub_cert_dict[path] = True
                        else:
                                updated_pub_cert_dict[ips_hash] = status
                        iter_next = sorted_model.iter_next(iter_next)
                for ips_hash, status in self.orig_pub_cert_added_dict.items():
                        if not updated_pub_cert_dict.has_key(ips_hash):
                                errors += self.__remove_pub_cert_for_publisher(ips_hash)
                        elif status != updated_pub_cert_dict[ips_hash] and \
                                updated_pub_cert_dict[ips_hash] == PUBCERT_REVOKED_STR:
                                errors += self.__revoke_pub_cert_for_publisher(ips_hash)
                # Add and reinstate pub certs for publisher
                for path in add_pub_cert_dict.keys():
                        errors += self.__add_pub_cert_to_publisher(path)

                return errors

        def __add_pub_cert_to_publisher(self, path):
                errors = []
                try:
                        with open(path, "rb") as fh:
                                s = fh.read()
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                errors.append(("",
                                    api_errors.MissingFileArgumentException(path)))
                        elif e.errno == errno.EACCES:
                                errors.append(("", api_errors.PermissionsException(path)))
                        else:
                                errors.append(("", e))
                try:
                        pub = self.repository_modify_publisher
                        if pub != None:
                                pub.approve_ca_cert(s)
                except api_errors.ApiException, e:
                        errors.append(("", e))
                return errors

        def __revoke_pub_cert_for_publisher(self, ips_hash):
                errors = []
                try:
                        pub = self.repository_modify_publisher
                        if pub != None:
                                pub.revoke_ca_cert(ips_hash)
                except api_errors.ApiException, e:
                        errors.append(("", e))
                return errors

        def __remove_pub_cert_for_publisher(self, ips_hash):
                errors = []
                try:
                        pub = self.repository_modify_publisher
                        if pub != None:
                                pub.unset_ca_cert(ips_hash)
                except api_errors.ApiException, e:
                        errors.append(("", e))
                return errors

        def __init_pubs_tree_view(self, publishers_list):
                publishers_list_filter = publishers_list.filter_new()
                publishers_list_sort = gtk.TreeModelSort(publishers_list_filter)
                publishers_list_sort.set_sort_column_id(
                    enumerations.PUBLISHER_PRIORITY_CHANGED, gtk.SORT_ASCENDING)
                # Name column
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Publisher"),
                    name_renderer,  text = enumerations.PUBLISHER_NAME)
                column.set_expand(True)
                self.w_publishers_treeview.append_column(column)
                # Alias column
                alias_renderer = gtk.CellRendererText()
                alias_renderer.set_property("ellipsize", pango.ELLIPSIZE_END)
                column = gtk.TreeViewColumn(_("Alias"),
                    alias_renderer, text = enumerations.PUBLISHER_ALIAS)
                column.set_expand(True)
                self.w_publishers_treeview.append_column(column)
                # Enabled column
                toggle_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Enabled"),
                    toggle_renderer, active = enumerations.PUBLISHER_ENABLED)
                toggle_renderer.set_property("activatable", True)
                column.set_expand(False)
                toggle_renderer.connect('toggled', self.__enable_disable)
                column.set_cell_data_func(toggle_renderer, 
                    self.__toggle_data_function, None)
                self.w_publishers_treeview.append_column(column)
                # Sticky column
                toggle_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Sticky"),
                    toggle_renderer, active = enumerations.PUBLISHER_STICKY)
                toggle_renderer.set_property("activatable", True)
                column.set_expand(False)
                toggle_renderer.connect('toggled', self.__sticky_unsticky)
                column.set_cell_data_func(toggle_renderer, 
                    self.__toggle_data_function, None)
                self.w_publishers_treeview.append_column(column)
                publishers_list_filter.set_visible_func(self.__publishers_filter)
                self.w_publishers_treeview.set_model(publishers_list_sort)

        def __prepare_publisher_list(self, restore_changes = False):
                sorted_model = self.w_publishers_treeview.get_model()
                selection = self.w_publishers_treeview.get_selection()
                selected_rows = selection.get_selected_rows()
                self.w_publishers_treeview.set_model(None)
                try:
                        pubs = self.api_o.get_publishers(duplicate=True)
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return
                if not sorted_model:
                        return
                filtered_model = sorted_model.get_model()
                model = filtered_model.get_model()

                if restore_changes == False:
                        self.no_changes = 0
                        self.priority_changes = []
                        model.clear()

                        j = 0
                        for pub in pubs:
                                name = pub.prefix
                                alias = pub.alias
                                # BUG: alias should be either "None" or None.
                                # in the list it's "None", but when adding pub it's None
                                if not alias or len(alias) == 0 or alias == "None":
                                        alias = name
                                publisher_row = [j, j, name, alias, not pub.disabled,
                                    pub.sticky, pub, False, False, False]
                                model.insert(j, publisher_row)
                                j += 1
                else:
                        j = 0
                        for publisher_row in model:
                                pub = pubs[j]
                                name = pub.prefix
                                alias = pub.alias
                                if not alias or len(alias) == 0 or alias == "None":
                                        alias = name
                                publisher_row[enumerations.PUBLISHER_ALIAS] = alias
                                publisher_row[enumerations.PUBLISHER_OBJECT] = pub
                                j += 1
                        # We handle here the case where a publisher was added
                        if self.new_pub:
                                pub = self.new_pub
                                name = pub.prefix
                                alias = pub.alias
                                if not alias or len(alias) == 0 or alias == "None":
                                        alias = name
                                publisher_row = [j, j, name, alias, not pub.disabled,
                                    pub.sticky, pub, False, False, False]
                                model.insert(j, publisher_row)

                self.w_publishers_treeview.set_model(sorted_model)
                if len(sorted_model) == 0:
                        self.__set_empty_pub_list()

                if restore_changes:
                        if self.new_pub:
                                self.__select_last_publisher()
                                self.new_pub = None
                        else:
                        # We do have gtk.SELECTION_SINGLE mode, so if exists, we are
                        # interested only in the first selected path. 
                                if len(selected_rows) > 1 and len(selected_rows[1]) > 0:
                                        self.w_publishers_treeview.scroll_to_cell(
                                            selected_rows[1][0])
                                        selection.select_path(selected_rows[1][0])

        def __set_empty_pub_list(self):
                details_buffer = self.w_manage_publishers_details.get_buffer()
                details_buffer.set_text("")
                self.w_manage_modify_btn.set_sensitive(False)
                self.w_manage_remove_btn.set_sensitive(False)
                self.w_manage_up_btn.set_sensitive(False)
                self.w_manage_down_btn.set_sensitive(False)

        def __select_last_publisher(self):
                sorted_model = self.w_publishers_treeview.get_model()
                itr = sorted_model.get_iter_first()
                next_itr = sorted_model.iter_next(itr) 
                while next_itr != None:
                        itr = next_itr
                        next_itr = sorted_model.iter_next(itr) 
                path = sorted_model.get_path(itr)
                self.w_publishers_treeview.scroll_to_cell(path)
                self.w_publishers_treeview.get_selection().select_path(path)

        def __validate_url(self, url_widget, w_ssl_key = None, w_ssl_cert = None):
                self.__validate_url_generic(url_widget, self.w_add_error_label, 
                    self.w_publisher_add_button, self.is_alias_valid,
                    w_ssl_label=self.w_add_sslerror_label,
                    w_ssl_key=w_ssl_key, w_ssl_cert=w_ssl_cert)

        def __validate_url_generic(self, w_url_text, w_error_label, w_action_button,
                alias_valid = False, function = None, w_ssl_label = None, 
                w_ssl_key = None, w_ssl_cert = None):
                ssl_key = None
                ssl_cert = None
                ssl_error = None
                ssl_valid = True
                url = w_url_text.get_text()
                self.is_url_valid, self.url_err = self.__is_url_valid(url)
                if not self.webinstall_new:
                        self.__reset_error_label()
                if w_ssl_label:
                        w_ssl_label.set_sensitive(False)
                        w_ssl_label.show()
                valid_url = False
                valid_func = True
                if self.is_url_valid:
                        if alias_valid:
                                valid_url = True
                        else:
                                if self.name_error != None:
                                        self.__show_error_label_with_format(w_error_label,
                                            self.name_error)
                else:
                        if self.url_err != None:
                                self.__show_error_label_with_format(w_error_label,
                                    self.url_err)
                if w_ssl_key != None and w_ssl_cert != None:
                        if w_ssl_key:
                                ssl_key = w_ssl_key.get_text()
                        if w_ssl_cert:
                                ssl_cert = w_ssl_cert.get_text()
                        ssl_valid, ssl_error = self.__validate_ssl_key_cert(url, ssl_key,
                            ssl_cert, ignore_ssl_check_for_not_https=True)
                        self.__update_repository_dialog_width(ssl_error)
                        if ssl_error != None and w_ssl_label:
                                self.__show_error_label_with_format(w_ssl_label,
                                    ssl_error)
                        elif w_ssl_label:
                                w_ssl_label.hide()
                if function != None:
                        valid_func = function()
                w_action_button.set_sensitive(valid_url and valid_func and ssl_valid)

        def __validate_alias_addpub(self, ok_btn, name_widget, url_widget, error_label,
            function = None):
                valid_btn = False
                valid_func = True
                name = name_widget.get_text() 
                self.is_alias_valid = self.__is_alias_valid(name)
                self.__reset_error_label()
                if self.is_alias_valid:
                        if (self.is_url_valid):
                                valid_btn = True
                        else:
                                if self.url_err == None:
                                        self.__validate_url(url_widget,
                                            w_ssl_key=self.w_key_entry,
                                            w_ssl_cert=self.w_cert_entry)
                                if self.url_err != None:
                                        self.__show_error_label_with_format(error_label,
                                            self.url_err)
                else:
                        if self.name_error != None:
                                self.__show_error_label_with_format(error_label,
                                            self.name_error)
                if function != None:
                        valid_func = function()
                ok_btn.set_sensitive(valid_btn and valid_func)

        def __is_alias_valid(self, name):
                self.name_error = None
                if len(name) == 0:
                        return True
                try:
                        publisher.Publisher(prefix=name)
                except api_errors.BadPublisherPrefix, e:
                        self.name_error = _("Alias contains invalid characters")
                        return False
                try:
                        self.api_o.get_publisher(prefix=name)
                        self.name_error = _("Alias already in use")
                        return False
                except api_errors.UnknownPublisher, e:
                        return True
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return False

        def __get_selected_publisher_itr_model(self):
                itr, sorted_model = self.__get_fitr_model_from_tree(
                    self.w_publishers_treeview)
                if itr == None or sorted_model == None:
                        return (None, None)
                sorted_path = sorted_model.get_path(itr)
                filter_path = sorted_model.convert_path_to_child_path(sorted_path)
                filter_model = sorted_model.get_model()
                path = filter_model.convert_path_to_child_path(filter_path)
                model = filter_model.get_model()
                itr = model.get_iter(path)
                return (itr, model)

        def __get_selected_mirror_itr_model(self):
                return self.__get_fitr_model_from_tree(\
                    self.modify_repo_mirrors_treeview)

        def __get_selected_origin_itr_model(self):
                return self.__get_fitr_model_from_tree(\
                    self.modify_repo_origins_treeview)

        def __modify_publisher_dialog(self, pub):
                self.orig_sig_policy = {}
                self.pub_certs_setup = False

                gui_misc.set_modal_and_transient(self.w_modify_repository_dialog,
                    self.w_manage_publishers_dialog)
                try:
                        self.repository_modify_publisher = self.api_o.get_publisher(
                            prefix=pub.prefix, alias=pub.prefix, duplicate=True)
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return                
                updated_modify_repository = self.__update_modify_repository_dialog(True,
                    True, True, True)
                    
                self.w_modify_repository_dialog.set_size_request(
                    MODIFY_DIALOG_WIDTH_DEFAULT, -1)

                if updated_modify_repository:
                        self.w_modify_repository_dialog.set_title(
                            _("Modify Publisher - %s") %
                            self.__get_pub_display_name(pub))
                        self.w_modify_repository_dialog.show_all()

                pagenum = self.w_modify_pub_notebook.get_current_page()
                if pagenum == MODIFY_NOTEBOOK_CERTIFICATE_PAGE:
                        gobject.idle_add(self.__prepare_pub_certs)
                elif pagenum == MODIFY_NOTEBOOK_SIG_POLICY_PAGE:
                        gobject.idle_add(self.__prepare_pub_signature_policy)

        def __update_repository_dialog_width(self, ssl_error):
                if ssl_error == None:
                        self.w_modify_repository_dialog.set_size_request(
                            MODIFY_DIALOG_WIDTH_DEFAULT, -1)
                        return

                style = self.w_repositorymodify_name.get_style()
                font_size_in_pango_unit = style.font_desc.get_size()
                font_size_in_pixel = font_size_in_pango_unit / pango.SCALE 
                ssl_error_len = len(unicode(ssl_error)) * font_size_in_pixel
                if ssl_error_len > MODIFY_DIALOG_SSL_WIDTH_DEFAULT:
                        new_dialog_width = ssl_error_len * \
                                (float(MODIFY_DIALOG_WIDTH_DEFAULT)/
                                    MODIFY_DIALOG_SSL_WIDTH_DEFAULT)
                        self.w_modify_repository_dialog.set_size_request(
                            int(new_dialog_width), -1)
                else:
                        self.w_modify_repository_dialog.set_size_request(
                            MODIFY_DIALOG_WIDTH_DEFAULT, -1)

        def __update_modify_repository_dialog(self, update_alias=False, 
            update_mirrors=False, update_origins=False, update_ssl=False):
                if not self.repository_modify_publisher:
                        return False
                pub = self.repository_modify_publisher
                selected_repo = pub.repository
                prefix = ""
                ssl_cert = ""
                ssl_key = ""

                if pub.prefix and len(pub.prefix) > 0:
                        prefix = pub.prefix
                self.w_repositorymodify_name.set_text(prefix)

                if update_alias:
                        alias = ""
                        if pub.alias and len(pub.alias) > 0 \
                            and pub.alias != "None":
                                alias = pub.alias
                        self.w_modify_pub_alias.set_text(alias)

                if update_mirrors or update_ssl:
                        if update_mirrors:
                                insert_count = 0
                                mirrors_list = self.__get_mirrors_origins_liststore()
                        for mirror in selected_repo.mirrors:
                                if mirror.ssl_cert:
                                        ssl_cert = mirror.ssl_cert
                                if mirror.ssl_key:
                                        ssl_key = mirror.ssl_key
                                if update_mirrors:
                                        mirror_uri = [mirror.uri]
                                        mirrors_list.insert(insert_count, mirror_uri)
                                        insert_count += 1
                        if update_mirrors:
                                self.modify_repo_mirrors_treeview.set_model(mirrors_list)
                                if len(selected_repo.mirrors) > 0:
                                        self.w_repositorymirror_expander.set_expanded(
                                            True)
                                else:
                                        self.w_repositorymirror_expander.set_expanded(
                                            False)

                if update_origins or update_ssl:
                        if update_origins:
                                insert_count = 0
                                origins_list = self.__get_mirrors_origins_liststore()
                        for origin in selected_repo.origins:
                                if origin.ssl_cert:
                                        ssl_cert = origin.ssl_cert
                                if origin.ssl_key:
                                        ssl_key = origin.ssl_key
                                if update_origins:
                                        origin_uri = [origin.uri]
                                        origins_list.insert(insert_count, origin_uri)
                                        insert_count += 1
                        if update_origins:
                                self.modify_repo_origins_treeview.set_model(origins_list)

                reg_uri = self.__get_registration_uri(selected_repo)
                if reg_uri != None:
                        self.w_repositorymodify_registration_link.set_uri(
                            reg_uri)
                        self.w_repositorymodify_registration_box.show()
                else:
                        self.w_repositorymodify_registration_box.hide()

                if update_ssl:
                        self.w_repositorymodify_cert_entry.set_text(ssl_cert)
                        self.w_repositorymodify_key_entry.set_text(ssl_key)
                return True

        def __add_mirror(self, new_mirror):
                pub = self.repository_modify_publisher
                repo = pub.repository
                try:
                        repo.add_mirror(new_mirror)
                        self.w_addmirror_entry.set_text("")
                except api_errors.ApiException, e:
                        self.__show_errors([(pub, e)])
                self.__update_modify_repository_dialog(update_mirrors=True)

        def __rm_mirror(self):
                itr, model = self.__get_selected_mirror_itr_model()
                remove_mirror = None
                if itr and model:
                        remove_mirror = model.get_value(itr, 0)
                pub = self.repository_modify_publisher
                repo = pub.repository
                try:
                        repo.remove_mirror(remove_mirror)
                except api_errors.ApiException, e:
                        self.__show_errors([(pub, e)])
                self.__update_modify_repository_dialog(update_mirrors=True)

        def __add_origin(self, new_origin):
                pub = self.repository_modify_publisher
                repo = pub.repository
                try:
                        repo.add_origin(new_origin)
                        self.w_addorigin_entry.set_text("")
                except api_errors.ApiException, e:
                        self.__show_errors([(pub, e)])
                self.__update_modify_repository_dialog(update_origins=True)

        def __rm_origin(self):
                itr, model = self.__get_selected_origin_itr_model()
                remove_origin = None
                if itr and model:
                        remove_origin = model.get_value(itr, 0)
                pub = self.repository_modify_publisher
                repo = pub.repository
                try:
                        repo.remove_origin(remove_origin)
                except api_errors.ApiException, e:
                        self.__show_errors([(pub, e)])
                self.__update_modify_repository_dialog(update_origins=True)

        def __sticky_unsticky(self, cell, sorted_path):
                sorted_model = self.w_publishers_treeview.get_model()
                filtered_path = sorted_model.convert_path_to_child_path(sorted_path)
                filtered_model = sorted_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                model = filtered_model.get_model()
                itr = model.get_iter(path)
                if itr == None:
                        return
                pub = model.get_value(itr, enumerations.PUBLISHER_OBJECT)
                if pub.sys_pub:
                        return
                is_sticky = model.get_value(itr, enumerations.PUBLISHER_STICKY)
                changed = model.get_value(itr, enumerations.PUBLISHER_STICKY_CHANGED)
                model.set_value(itr, enumerations.PUBLISHER_STICKY, not is_sticky)
                model.set_value(itr, enumerations.PUBLISHER_STICKY_CHANGED, not changed)

        def __enable_disable(self, cell, sorted_path):
                sorted_model = self.w_publishers_treeview.get_model()
                filtered_path = sorted_model.convert_path_to_child_path(sorted_path)
                filtered_model = sorted_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                model = filtered_model.get_model()
                itr = model.get_iter(path)
                if itr == None:
                        self.w_manage_modify_btn.set_sensitive(False)
                        self.w_manage_remove_btn.set_sensitive(False)
                        self.w_manage_up_btn.set_sensitive(False)
                        self.w_manage_down_btn.set_sensitive(False)
                        return
                pub = model.get_value(itr, enumerations.PUBLISHER_OBJECT)
                if pub.sys_pub:
                        return
                enabled = model.get_value(itr, enumerations.PUBLISHER_ENABLED)
                changed = model.get_value(itr, enumerations.PUBLISHER_ENABLE_CHANGED)
                model.set_value(itr, enumerations.PUBLISHER_ENABLED, not enabled)
                model.set_value(itr, enumerations.PUBLISHER_ENABLE_CHANGED, not changed)
                self.__enable_disable_updown_btn(itr, model)

        @staticmethod
        def __is_at_least_one_entry(treeview):
                model = treeview.get_model()
                if len(model) >= 1:
                        return True
                return False

        def __enable_disable_remove_modify_btn(self, itr, model):
                if itr == None:
                        self.w_manage_modify_btn.set_sensitive(False)
                        self.w_manage_remove_btn.set_sensitive(False)
                        self.w_manage_up_btn.set_sensitive(False)
                        self.w_manage_down_btn.set_sensitive(False)
                        return
                remove_val = False
                modify_val = False
                if self.__is_at_least_one_entry(self.w_publishers_treeview):
                        remove_val = True
                        modify_val = True
                        pub = model.get_value(itr,
                                enumerations.PUBLISHER_OBJECT)
                        if pub.sys_pub:
                                remove_val = False
                                modify_val = False
                self.w_manage_modify_btn.set_sensitive(modify_val)
                self.w_manage_remove_btn.set_sensitive(remove_val)

        def __enable_disable_updown_btn(self, itr, model):
                up_enabled = True
                down_enabled = True
                sorted_size = len(self.w_publishers_treeview.get_model())

                if itr:
                        current_priority = model.get_value(itr,
                            enumerations.PUBLISHER_PRIORITY_CHANGED)
                        is_sys_pub = model.get_value(itr,
                            enumerations.PUBLISHER_OBJECT).sys_pub
                        next_sys_pub = False
                        prev_sys_pub = False
                        path = model.get_path(itr)
                        next_itr = model.iter_next(itr)
                        if next_itr:
                                next_pub = model.get_value(next_itr,
                                    enumerations.PUBLISHER_OBJECT)
                                if next_pub.sys_pub:
                                        next_sys_pub = True
                        if path[0] > 0:
                                prev_path = (path[0] - 1,)
                                prev_itr = model.get_iter(prev_path)
                                prev_pub = model.get_value(prev_itr,
                                    enumerations.PUBLISHER_OBJECT)
                                if prev_pub.sys_pub:
                                        prev_sys_pub = True
             
                        if current_priority == sorted_size - 1:
                                down_enabled = False
                        elif current_priority == 0:
                                up_enabled = False

                        if sorted_size == 1:
                                up_enabled = False
                                down_enabled = False
                        else:
                                if next_sys_pub or is_sys_pub:
                                        down_enabled = False 
                                if prev_sys_pub or is_sys_pub:
                                        up_enabled = False 
                self.w_manage_up_btn.set_sensitive(up_enabled)
                self.w_manage_down_btn.set_sensitive(down_enabled)

        def __do_add_repository(self, alias=None, url=None, ssl_key=None, ssl_cert=None,
            pub=None):
                self.publishers_apply.set_title(_("Adding Publisher"))
                if self.webinstall_new:
                        self.__run_with_prog_in_thread(self.__add_repository,
                            self.main_window, self.__stop, None, None,  ssl_key,
                            ssl_cert, self.repository_modify_publisher)
                else:
                        self.__run_with_prog_in_thread(self.__add_repository,
                            self.w_add_publisher_dialog, self.__stop, alias,
                            url, ssl_key, ssl_cert, pub)

        def __stop(self):
                if self.cancel_progress_thread == False:
                        self.__update_details_text(_("Canceling...\n"))
                        self.cancel_progress_thread = True
                        self.publishers_apply_cancel.set_sensitive(False)

        def __add_repository(self, alias=None, origin_url=None, ssl_key=None, 
            ssl_cert=None, pub=None):
                errors = []
                if pub == None:
                        if self.__check_publisher_exists(self.api_o, alias, 
                                origin_url):
                                self.progress_stop_thread = True
                                return
                        pub, repo, new_pub = self.__setup_publisher_from_uri(
                            alias, origin_url, ssl_key, ssl_cert)
                        if pub == None:
                                self.progress_stop_thread = True
                                return
                else:
                        repo = pub.repository
                        new_pub = True
                        name = pub.prefix
                errors_ssl = self.__update_ssl_creds(pub, repo, ssl_cert, ssl_key)
                errors_update = []
                try:
                        errors_update = self.__update_publisher(pub,
                            new_publisher=new_pub)
                except api_errors.UnknownRepositoryPublishers, e:
                        if len(e.known) > 0:
                                pub, repo, new_pub = self.__get_or_create_pub_with_url(
                                    self.api_o, e.known[0], origin_url)
                                if new_pub:
                                        errors_ssl = self.__update_ssl_creds(pub, repo,
                                            ssl_cert, ssl_key)
                                        pub.alias = name
                                        errors_update = self.__update_publisher(pub,
                                            new_publisher=new_pub,
                                            raise_unknownpubex=False)
                                else:
                                        self.progress_stop_thread = True
                                        return
                        else:
                                errors_update.append((pub, e))
                errors += errors_ssl
                errors += errors_update
                if self.cancel_progress_thread:
                        try:
                                self.__g_update_details_text(
                                    _("Removing publisher %s\n") % name)
                                self.api_o.remove_publisher(prefix=name,
                                    alias=name)
                                self.__g_update_details_text(
                                    _("Publisher %s succesfully removed\n") % name)
                        except api_errors.ApiException, e:
                                errors.append((pub, e))
                        self.progress_stop_thread = True
                else:
                        self.progress_stop_thread = True
                        if len(errors) > 0:
                                gobject.idle_add(self.__show_errors, errors)
                        elif not self.webinstall_new:
                                gobject.idle_add(self.__afteradd_confirmation, pub)
                                self.progress_stop_thread = True
                                gobject.idle_add(
                                   self.__g_on_add_publisher_delete_event,
                                   self.w_add_publisher_dialog, None)
                        elif self.webinstall_new:
                                gobject.idle_add(
                                   self.__g_on_add_publisher_delete_event,
                                   self.w_add_publisher_dialog, None)
                                gobject.idle_add(self.parent.reload_packages)

        def __update_publisher(self, pub, new_publisher=False, raise_unknownpubex=True):
                errors = []
                try:
                        if new_publisher:
                                self.__g_update_details_text(
                                    _("Adding publisher %s\n") % pub.prefix)
                                self.api_o.add_publisher(pub)
                                self.no_changes += 1
                        else:
                                self.__g_update_details_text(
                                    _("Updating publisher %s\n") % pub.prefix)
                                self.api_o.update_publisher(pub)
                                self.no_changes += 1
                        if new_publisher:
                                self.__g_update_details_text(
                                    _("Publisher %s succesfully added\n") % pub.prefix)
                        else:
                                self.__g_update_details_text(
                                    _("Publisher %s succesfully updated\n") % pub.prefix)
                except api_errors.UnknownRepositoryPublishers, e:
                        if raise_unknownpubex:
                                raise e
                        else:
                                errors.append((pub, e))
                except api_errors.ApiException, e:
                        errors.append((pub, e))
                return errors

        def __afteradd_confirmation(self, pub):
                self.new_pub = pub
                repo = pub.repository
                origin = repo.origins[0]
                # Descriptions not available at the moment
                self.w_add_publisher_c_desc.hide()
                self.w_add_publisher_c_desc_l.hide()
                self.w_add_publisher_c_name.set_text(pub.prefix)
                if pub.alias and len(pub.alias) > 0:
                        self.w_add_publisher_c_alias.set_text(pub.alias)
                else:
                        self.w_add_publisher_c_alias.hide()
                        self.w_add_publisher_c_alias_l.hide()
                self.w_add_publisher_c_url.set_text(origin.uri)
                self.w_add_publisher_comp_dialog.show()

        def __prepare_confirmation_dialog(self):
                disable = ""
                enable = ""
                sticky = ""
                unsticky = ""
                delete = ""
                priority_change = ""
                disable_no = 0
                enable_no = 0
                sticky_no = 0
                unsticky_no = 0
                delete_no = 0
                not_removed = []
                removed_priorities = []
                priority_changed = []
                for row in self.publishers_list:
                        pub_name = row[enumerations.PUBLISHER_NAME]
                        if row[enumerations.PUBLISHER_REMOVED]:
                                delete += "\t" + pub_name + "\n"
                                delete_no += 1
                                removed_priorities.append(
                                    row[enumerations.PUBLISHER_PRIORITY])
                        else:
                                if row[enumerations.PUBLISHER_ENABLE_CHANGED]:
                                        to_enable = row[enumerations.PUBLISHER_ENABLED]
                                        if not to_enable:
                                                disable += "\t" + pub_name + "\n"
                                                disable_no += 1
                                        else:
                                                enable += "\t" + pub_name + "\n"
                                                enable_no += 1
                                if row[enumerations.PUBLISHER_STICKY_CHANGED]:
                                        to_sticky = row[enumerations.PUBLISHER_STICKY]
                                        if not to_sticky:
                                                unsticky += "\t" + pub_name + "\n"
                                                unsticky_no += 1
                                        else:
                                                sticky += "\t" + pub_name + "\n"
                                                sticky_no += 1
                                not_removed.append(row)

                for pub in not_removed:
                        if not self.__check_if_ignore(pub, removed_priorities):
                                pub_name = pub[enumerations.PUBLISHER_NAME]
                                pri = pub[enumerations.PUBLISHER_PRIORITY_CHANGED]
                                priority_changed.append([pri, pub_name])

                if disable_no == 0 and enable_no == 0 and delete_no == 0 and \
                    sticky_no == 0 and unsticky_no == 0 and \
                    len(priority_changed) == 0:
                        self.__on_manage_cancel_clicked(None)
                        return

                priority_changed.sort()
                for pri, pub_name in priority_changed:
                        priority_change += "\t" + str(pri+1) + \
                            " - " + pub_name + "\n"

                textbuf = self.w_confirmation_textview.get_buffer()
                textbuf.set_text("")
                textiter = textbuf.get_end_iter()

                disable_text = ngettext("Disable Publisher:\n",
		    "Disable Publishers:\n", disable_no)
                enable_text = ngettext("Enable Publisher:\n",
		    "Enable Publishers:\n", enable_no)
                delete_text = ngettext("Remove Publisher:\n",
		    "Remove Publishers:\n", delete_no)
                sticky_text = ngettext("Set sticky Publisher:\n",
		    "Set sticky Publishers:\n", delete_no)
                unsticky_text = ngettext("Unset sticky Publisher:\n",
		    "Unset sticky Publishers:\n", delete_no)
                priority_text = _("Change Priorities:\n")

                confirm_no = delete_no + enable_no + disable_no + sticky_no + \
                    unsticky_no
                confirm_text = ngettext("Apply the following change:",
		    "Apply the following changes:", confirm_no)

                self.w_confirmation_label.set_markup("<b>" + confirm_text + "</b>")

                if len(delete) > 0:
                        textbuf.insert_with_tags_by_name(textiter,
                            delete_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            delete)
                if len(disable) > 0:
                        if len(delete) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")
                        textbuf.insert_with_tags_by_name(textiter,
                            disable_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            disable)
                if len(enable) > 0:
                        if len(delete) > 0 or len(disable) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")
                        textbuf.insert_with_tags_by_name(textiter,
                            enable_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            enable)
                if len(sticky) > 0:
                        if len(delete) > 0 or len(disable) > 0 or len(enable) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")
                        textbuf.insert_with_tags_by_name(textiter,
                            sticky_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            sticky)
                if len(unsticky) > 0:
                        if len(delete) > 0 or len(disable) > 0 or \
                            len(enable) > 0 or len(sticky) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")
                        textbuf.insert_with_tags_by_name(textiter,
                            unsticky_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            unsticky)
                if len(priority_change) > 0:
                        if len(delete) > 0 or len(disable) or len(enable) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")
                        textbuf.insert_with_tags_by_name(textiter,
                            priority_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            priority_change)

                self.w_confirm_cancel_btn.grab_focus()
                self.w_confirmation_dialog.show_all()

        def __proceed_enable_disable(self, pub_names, to_enable):
                errors = []

                gobject.idle_add(self.publishers_apply_expander.set_expanded, True)
                for name in pub_names.keys():
                        try:
                                pub = self.api_o.get_publisher(name,
                                    duplicate = True)
                                if pub.disabled == (not to_enable):
                                        continue
                                pub.disabled = not to_enable
                                self.no_changes += 1
                                enable_text = _("Disabling")
                                if to_enable:
                                        enable_text = _("Enabling")

                                details_text = \
                                        _("%(enable)s publisher %(name)s\n")
                                self.__g_update_details_text(details_text %
                                    {"enable" : enable_text, "name" : name})
                                self.api_o.update_publisher(pub)
                        except api_errors.ApiException, e:
                                errors.append(pub, e)
                self.progress_stop_thread = True
                gobject.idle_add(self.publishers_apply_expander.set_expanded, False)
                if len(errors) > 0:
                        gobject.idle_add(self.__show_errors, errors)
                else:
                        gobject.idle_add(self.parent.reload_packages, False)

        def __proceed_after_confirmation(self):
                errors = []

                image_lock_err = False
                for row in self.priority_changes:
                        try:
                                if row[1] == None or row[2] == None:
                                        continue
                                pub1 = self.api_o.get_publisher(row[1],
                                    duplicate=True)
                                pub2 = self.api_o.get_publisher(row[2],
                                    duplicate=True)
                                if row[0] == enumerations.PUBLISHER_MOVE_BEFORE:
                                        self.api_o.update_publisher(pub1,
                                            search_before=pub2.prefix)
                                else:
                                        self.api_o.update_publisher(pub1,
                                            search_after=pub2.prefix)
                                self.no_changes += 1
                                self.__g_update_details_text(
                                    _("Changing priority for publisher %s\n")
                                    % row[1])
                        except api_errors.ImageLockedError, e:
                                self.no_changes = 0
                                if not image_lock_err:
                                        errors.append((row[1], e))
                                        image_lock_err = True
                        except api_errors.ApiException, e:
                                errors.append((row[1], e))

                for row in self.publishers_list:
                        name = row[enumerations.PUBLISHER_NAME]
                        try:
                                if row[enumerations.PUBLISHER_REMOVED]:
                                        self.no_changes += 1
                                        self.__g_update_details_text(
                                            _("Removing publisher %s\n") % name)
                                        self.api_o.remove_publisher(prefix=name,
                                            alias=name)
                                        self.__g_update_details_text(
                                            _("Publisher %s succesfully removed\n")
                                            % name)
                                elif row[enumerations.PUBLISHER_ENABLE_CHANGED] or \
                                    row[enumerations.PUBLISHER_STICKY_CHANGED]:
                                        self.__do_changes_for_row(row, name)
                        except api_errors.ImageLockedError, e:
                                self.no_changes = 0
                                if not image_lock_err:
                                        errors.append(
                                            (row[enumerations.PUBLISHER_OBJECT], e))
                                        image_lock_err = True
                        except api_errors.ApiException, e:
                                errors.append((row[enumerations.PUBLISHER_OBJECT], e))
                self.progress_stop_thread = True
                if len(errors) > 0:
                        gobject.idle_add(self.__show_errors, errors)
                else:
                        gobject.idle_add(self.__after_confirmation)

        def __do_changes_for_row(self, row, name):
                pub = self.api_o.get_publisher(name, duplicate = True)
                if row[enumerations.PUBLISHER_ENABLE_CHANGED]:
                        to_enable = row[enumerations.PUBLISHER_ENABLED]
                        pub.disabled = not to_enable
                if row[enumerations.PUBLISHER_STICKY_CHANGED]:
                        sticky = row[enumerations.PUBLISHER_STICKY]
                        pub.sticky = sticky
                self.no_changes += 1
                update_text = _("Updating")
                details_text = _("%(update)s publisher %(name)s\n")
                self.__g_update_details_text(details_text % 
                    {"update" : update_text, "name" : name})
                self.api_o.update_publisher(pub)

        def __after_confirmation(self):
                self.__on_manage_publishers_delete_event(
                    self.w_manage_publishers_dialog, None)
                return False

        def __proceed_modifyrepo_ok(self):
                errors = []
                alias = self.w_modify_pub_alias.get_text()
                ssl_key = self.w_repositorymodify_key_entry.get_text()
                ssl_cert = self.w_repositorymodify_cert_entry.get_text()
                pub = self.repository_modify_publisher
                repo = pub.repository
                missing_ssl = False
                try:
                        prefix = pub.prefix
                        mirrors = repo.mirrors
                        origins = repo.origins
                        self.api_o.reset()
                        self.repository_modify_publisher = self.api_o.get_publisher(
                            prefix=prefix, alias=prefix, duplicate=True)
                        pub = self.repository_modify_publisher
                        repo = pub.repository
                        repo.mirrors = mirrors
                        repo.origins = origins
                        if pub.alias != alias:
                                pub.alias = alias
                        errors += self.__update_ssl_creds(pub, repo, ssl_cert, ssl_key)
                        errors += self.__update_pub_certs()
                        errors += self.__update_pub_sig_policy()
                        errors += self.__update_publisher(pub, new_publisher=False)
                except api_errors.ApiException, e:
                        errors.append((pub, e))
                self.progress_stop_thread = True
                if len(errors) > 0:
                        missing_ssl = self.__is_missing_ssl_creds(pub, ssl_key, ssl_cert)
                        gobject.idle_add(self.__show_errors, errors, missing_ssl)
                else:
                        gobject.idle_add(self.__g_delete_widget_handler_hide,
                            self.w_modify_repository_dialog, None)
                        if self.action == enumerations.MANAGE_PUBLISHERS:
                                gobject.idle_add(self.__prepare_publisher_list, True)
                                self.no_changes += 1

        @staticmethod
        def __is_missing_ssl_creds(pub, ssl_key, ssl_cert):
                repo = pub.repository
                if ssl_key and len(ssl_key) > 0 and ssl_cert and len(ssl_cert) > 0:
                        return False
                for uri in repo.origins:
                        print uri
                        if uri.scheme in publisher.SSL_SCHEMES:
                                return True
                for uri in repo.mirrors:
                        if uri.scheme in publisher.SSL_SCHEMES:
                                return True
                return False

        def __run_with_prog_in_thread(self, func, parent_window = None,
            cancel_func = None, *f_args):
                self.progress_stop_thread = False
                self.cancel_progress_thread = False
                if cancel_func == None:
                        self.publishers_apply_cancel.set_sensitive(False)
                else:
                        self.publishers_apply_cancel.set_sensitive(True)
                gui_misc.set_modal_and_transient(self.publishers_apply, parent_window)
                self.publishers_apply_textview.get_buffer().set_text("")
                self.publishers_apply.show_all()
                self.cancel_function = cancel_func
                gobject.timeout_add(100, self.__progress_pulse)
                Thread(target = func, args = f_args).start()

        def __progress_pulse(self):
                if not self.progress_stop_thread:
                        self.publishers_apply_progress.pulse()
                        return True
                else:
                        self.publishers_apply.hide()
                        return False

        def __g_update_details_text(self, text, *tags):
                gobject.idle_add(self.__update_details_text, text, *tags)

        def __update_details_text(self, text, *tags):
                buf = self.publishers_apply_textview.get_buffer()
                textiter = buf.get_end_iter()
                if tags:
                        buf.insert_with_tags_by_name(textiter, text, *tags)
                else:
                        buf.insert(textiter, text)
                self.publishers_apply_textview.scroll_to_iter(textiter, 0.0)

        # Signal handlers
        def __on_publisher_selection_changed(self, selection, widget):
                itr, model = self.__get_selected_publisher_itr_model()
                if itr and model:
                        self.__enable_disable_updown_btn(itr, model)
                        self.__enable_disable_remove_modify_btn(itr, model)
                        self.__update_publisher_details(
                            model.get_value(itr, enumerations.PUBLISHER_OBJECT),
                            self.w_manage_publishers_details)

        def __on_mirror_selection_changed(self, selection, widget):
                model_itr = selection.get_selected()
                if model_itr[1]:
                        self.w_rmmirror_button.set_sensitive(True)
                else:
                        self.w_rmmirror_button.set_sensitive(False)

        def __on_origin_selection_changed(self, selection, widget):
                model_itr = selection.get_selected()
                if model_itr[1] and \
                    self.__is_at_least_one_entry(self.modify_repo_origins_treeview):
                        self.w_rmorigin_button.set_sensitive(True)
                else:
                        self.w_rmorigin_button.set_sensitive(False)

        def __g_on_add_publisher_delete_event(self, widget, event):
                self.__on_add_publisher_delete_event(widget, event)
                return False
                
        def __on_add_publisher_delete_event(self, widget, event):
                self.w_add_publisher_url.set_text("")
                self.w_add_publisher_alias.set_text("")
                self.__delete_widget_handler_hide(widget, event)
                return True

        def __on_add_publisher_complete_delete_event(self, widget, event):
                if self.no_changes > 0:
                        self.parent.reload_packages()
                        if self.action == enumerations.MANAGE_PUBLISHERS:
                                self.__prepare_publisher_list(True)
                self.__delete_widget_handler_hide(widget, event)
                return True

        def __on_publisherurl_changed(self, widget):
                url = widget.get_text()
                if self.__is_ssl_scheme(url):
                        self.w_ssl_box.show()
                else:
                        self.w_ssl_box.hide()
                self.__validate_url(widget,
                    w_ssl_key=self.w_key_entry, w_ssl_cert=self.w_cert_entry)

        def __on_certentry_changed(self, widget):
                self.__validate_url_generic(self.w_add_publisher_url,
                    self.w_add_error_label, self.w_publisher_add_button,
                    self.is_alias_valid, w_ssl_label=self.w_add_sslerror_label,
                    w_ssl_key=self.w_key_entry, w_ssl_cert=widget)

        def __on_keyentry_changed(self, widget):
                self.__validate_url_generic(self.w_add_publisher_url,
                    self.w_add_error_label, self.w_publisher_add_button,
                    self.is_alias_valid, w_ssl_label=self.w_add_sslerror_label,
                    w_ssl_key=widget, w_ssl_cert=self.w_cert_entry)

        def __on_modcertkeyentry_changed(self, widget):
                self.__on_addorigin_entry_changed(None)
                self.__on_addmirror_entry_changed(None)
                ssl_key = self.w_repositorymodify_key_entry.get_text()
                ssl_cert = self.w_repositorymodify_cert_entry.get_text()
                ssl_valid, ssl_error = self.__validate_ssl_key_cert(None,
                    ssl_key, ssl_cert)
                self.__update_repository_dialog_width(ssl_error)
                self.w_repositorymodifyok_button.set_sensitive(True)
                if ssl_valid == False and (len(ssl_key) > 0 or len(ssl_cert) > 0):
                        self.w_repositorymodifyok_button.set_sensitive(False)
                        if ssl_error != None:
                                self.__show_error_label_with_format(
                                    self.w_modsslerror_label, ssl_error)
                        else:
                                self.w_modsslerror_label.set_text("")
                        return
                self.w_modsslerror_label.set_text("")

        def __on_addmirror_entry_changed(self, widget):
                uri_list_model = self.modify_repo_mirrors_treeview.get_model()
                self.__validate_mirror_origin_url(self.w_addmirror_entry.get_text(),
                    self.w_addmirror_button, self.w_modmirrerror_label, uri_list_model)

        def __on_addorigin_entry_changed(self, widget):
                uri_list_model = self.modify_repo_origins_treeview.get_model()
                self.__validate_mirror_origin_url(self.w_addorigin_entry.get_text(),
                    self.w_addorigin_button, self.w_modoriginerror_label, uri_list_model)

        def __validate_mirror_origin_url(self, url, add_button, error_label,
            uri_list_model):
                url_error = None
                is_url_valid, url_error = self.__is_url_valid(url)
                add_button.set_sensitive(False)
                error_label.set_sensitive(False)
                error_label.set_markup(self.publisher_info)
                if len(url) <= 4:
                        if is_url_valid == False and url_error != None:
                                self.__show_error_label_with_format(
                                    error_label, url_error)
                        return

                for uri_row in uri_list_model:
                        origin_url = uri_row[0].strip("/")
                        if origin_url.strip("/") == url.strip("/"):
                                url_error = _("URI already added")
                                self.__show_error_label_with_format(
                                            error_label, url_error)
                                return

                if is_url_valid == False:
                        if url_error != None:
                                self.__show_error_label_with_format(error_label,
                                    url_error)
                        return
                add_button.set_sensitive(True)

        def __is_ssl_specified(self):
                ssl_key = self.w_repositorymodify_key_entry.get_text()
                ssl_cert = self.w_repositorymodify_cert_entry.get_text()
                if len(ssl_key) > 0 or len(ssl_cert) > 0:
                        return True
                return False

        def __on_publisheralias_changed(self, widget):
                error_label = self.w_add_error_label
                url_widget = self.w_add_publisher_url
                ok_btn = self.w_publisher_add_button
                self.__validate_alias_addpub(ok_btn, widget, url_widget, error_label)

        def __on_modify_pub_alias_changed(self, widget):
                error_label = self.w_modify_alias_error_label
                ok_btn = self.w_repositorymodifyok_button
                name = widget.get_text()
                self.is_alias_valid = self.__is_alias_valid(name)
                if not self.is_alias_valid and self.name_error != None:
                        self.__show_error_label_with_format(error_label,
                                    self.name_error)
                        ok_btn.set_sensitive(False)
                else:
                        error_label.set_text("")
                        ok_btn.set_sensitive(True)

        def __on_add_publisher_add_clicked(self, widget):
                if self.w_publisher_add_button.get_property('sensitive') == 0:
                        return
                alias = self.w_add_publisher_alias.get_text()
                if len(alias) == 0:
                        alias = None
                url = self.w_add_publisher_url.get_text()
                ssl_key = self.w_key_entry.get_text()
                ssl_cert = self.w_cert_entry.get_text()
                if not self.__is_ssl_scheme(url) or not \
                    (ssl_key and ssl_cert and os.path.isfile(ssl_cert) and
                    os.path.isfile(ssl_key)):
                        ssl_key = None
                        ssl_cert = None
                self.__do_add_repository(alias, url, ssl_key, ssl_cert)

        def __on_apply_cancel_clicked(self, widget):
                if self.cancel_function:
                        self.cancel_function()

        def __on_add_publisher_cancel_clicked(self, widget):
                self.__on_add_publisher_delete_event(
                    self.w_add_publisher_dialog, None)

        def __on_modkeybrowse_clicked(self, widget):
                self.__keybrowse(self.w_modify_repository_dialog,
                    self.w_repositorymodify_key_entry,
                    self.w_repositorymodify_cert_entry)

        def __on_modcertbrowse_clicked(self, widget):
                self.__certbrowse(self.w_modify_repository_dialog,
                    self.w_repositorymodify_cert_entry)

        def __on_keybrowse_clicked(self, widget):
                self.__keybrowse(self.w_add_publisher_dialog,
                    self.w_key_entry, self.w_cert_entry)

        def __on_certbrowse_clicked(self, widget):
                self.__certbrowse(self.w_add_publisher_dialog,
                    self.w_cert_entry)

        def __on_add_publisher_c_close_clicked(self, widget):
                self.__on_add_publisher_complete_delete_event(
                    self.w_add_publisher_comp_dialog, None)

        def __on_manage_publishers_delete_event(self, widget, event):
                self.__delete_widget_handler_hide(widget, event)
                if self.no_changes > 0:
                        self.parent.reload_packages()
                return True

        def __g_delete_widget_handler_hide(self, widget, event):
                self.__delete_widget_handler_hide(widget, event)
                return False

        def __on_manage_add_clicked(self, widget):
                self.w_add_publisher_url.grab_focus()
                self.w_registration_box.hide()
                self.__reset_error_label()
                self.w_add_publisher_dialog.show_all()

        def __reset_error_label(self):
                self.w_add_error_label.set_markup(self.publisher_info)
                self.w_add_error_label.set_sensitive(False)
                self.w_add_error_label.show()

        def __on_manage_modify_clicked(self, widget):
                itr, model = self.__get_selected_publisher_itr_model()
                if itr and model:
                        pub = model.get_value(itr, enumerations.PUBLISHER_OBJECT)
                        self.__modify_publisher_dialog(pub)

        def __on_manage_remove_clicked(self, widget):
                itr, model = self.__get_selected_publisher_itr_model()
                tsel = self.w_publishers_treeview.get_selection()
                selection = tsel.get_selected()
                sel_itr = selection[1]
                sorted_model = selection[0]
                sorted_path = sorted_model.get_path(sel_itr)
                if itr and model:
                        current_priority = model.get_value(itr, 
                            enumerations.PUBLISHER_PRIORITY_CHANGED)
                        model.set_value(itr, enumerations.PUBLISHER_REMOVED, True)
                        for element in model:
                                if element[enumerations.PUBLISHER_PRIORITY_CHANGED] > \
                                    current_priority:
                                        element[
                                            enumerations.PUBLISHER_PRIORITY_CHANGED] -= 1
                        tsel.select_path(sorted_path)
                        if not tsel.path_is_selected(sorted_path):
                                row = sorted_path[0]-1
                                if row >= 0:
                                        tsel.select_path((row,))
                if len(sorted_model) == 0:
                        self.__set_empty_pub_list()

        def __on_manage_move_up_clicked(self, widget):
                before_name = None
                itr, model = self.__get_selected_publisher_itr_model()
                current_priority = model.get_value(itr,
                            enumerations.PUBLISHER_PRIORITY_CHANGED)
                current_name = model.get_value(itr, enumerations.PUBLISHER_NAME)
                for element in model:
                        if current_priority == \
                            element[enumerations.PUBLISHER_PRIORITY_CHANGED]:
                                element[
                                    enumerations.PUBLISHER_PRIORITY_CHANGED] -= 1
                        elif element[enumerations.PUBLISHER_PRIORITY_CHANGED] \
                            == current_priority - 1 :
                                before_name = element[enumerations.PUBLISHER_NAME]
                                element[
                                    enumerations.PUBLISHER_PRIORITY_CHANGED] += 1
                self.priority_changes.append([enumerations.PUBLISHER_MOVE_BEFORE,
                    current_name, before_name])
                self.__enable_disable_updown_btn(itr, model)
                self.__move_to_cursor()

        def __move_to_cursor(self):
                itr, model = self.__get_fitr_model_from_tree(self.w_publishers_treeview)
                if itr and model:
                        path = model.get_path(itr)
                        self.w_publishers_treeview.scroll_to_cell(path)

        def __on_manage_move_down_clicked(self, widget):
                after_name = None
                itr, model = self.__get_selected_publisher_itr_model()
                current_priority = model.get_value(itr,
                            enumerations.PUBLISHER_PRIORITY_CHANGED)
                current_name = model.get_value(itr, enumerations.PUBLISHER_NAME)
                for element in model:
                        if current_priority == \
                            element[enumerations.PUBLISHER_PRIORITY_CHANGED]:
                                element[
                                    enumerations.PUBLISHER_PRIORITY_CHANGED] += 1
                        elif element[enumerations.PUBLISHER_PRIORITY_CHANGED] \
                            == current_priority + 1 :
                                after_name = element[enumerations.PUBLISHER_NAME]
                                element[
                                    enumerations.PUBLISHER_PRIORITY_CHANGED] -= 1
                self.priority_changes.append([enumerations.PUBLISHER_MOVE_AFTER,
                    current_name, after_name])
                self.__enable_disable_updown_btn(itr, model)
                self.__move_to_cursor()

        def __on_manage_cancel_clicked(self, widget):
                self.__on_manage_publishers_delete_event(
                    self.w_manage_publishers_dialog, None)

        def __on_manage_ok_clicked(self, widget):
                self.__prepare_confirmation_dialog()

        def __on_publishers_apply_delete_event(self, widget, event):
                self.__on_apply_cancel_clicked(None)
                return True

        def __on_addmirror_button_clicked(self, widget):
                if self.w_addmirror_button.get_property('sensitive') == 0:
                        return
                new_mirror = self.w_addmirror_entry.get_text()
                self.__add_mirror(new_mirror)

        def __on_addorigin_button_clicked(self, widget):
                if self.w_addorigin_button.get_property('sensitive') == 0:
                        return
                new_origin = self.w_addorigin_entry.get_text()
                self.__add_origin(new_origin)

        def __on_rmmirror_button_clicked(self, widget):
                self.__rm_mirror()

        def __on_rmorigin_button_clicked(self, widget):
                self.__rm_origin()
                
        def __on_repositorymodifyok_clicked(self, widget):
                pub = self.repository_modify_publisher
                if pub == None:
                        return
                error_dialog_title = _("Modify Publisher - %s") % \
                        self.__get_pub_display_name(pub)
                text = self.w_pub_sig_name_entry.get_text()
                req_names = self.w_pub_sig_name_radiobutton.get_active()
                if not gui_misc.check_sig_required_names_policy(text,
                    req_names, error_dialog_title):
                        return

                self.publishers_apply.set_title(_("Applying Changes"))
                self.__run_with_prog_in_thread(self.__proceed_modifyrepo_ok)

        def __on_modifydialog_delete_event(self, widget, event):
                if self.w_repositorymodifyok_button.get_sensitive():
                        self.__on_repositorymodifyok_clicked(None)
                elif not self.is_alias_valid and self.name_error:
                        pub = self.repository_modify_publisher
                        gui_misc.error_occurred(None, self.name_error,
                            _("Modify Publisher - %s") %
                            self.__get_pub_display_name(pub),
                            gtk.MESSAGE_INFO)
                return True
                
        def __on_repositorymodifycancel_clicked(self, widget):
                self.__delete_widget_handler_hide(
                    self.w_modify_repository_dialog, None)

        def __on_cancel_conf_clicked(self, widget):
                self.__delete_widget_handler_hide(
                    self.w_confirmation_dialog, None)

        def __on_ok_conf_clicked(self, widget):
                self.w_confirmation_dialog.hide()
                self.publishers_apply.set_title(_("Applying Changes"))
                self.__run_with_prog_in_thread(self.__proceed_after_confirmation,
                    self.w_manage_publishers_dialog)

#-----------------------------------------------------------------------------#
# Static Methods
#-----------------------------------------------------------------------------#
        @staticmethod
        def __check_if_ignore(pub, removed_list):
                """If we remove a publisher from our model, the priorities of
                   subsequent publishers  are decremented. We need to ignore the
                   priority changes caused solely by publisher(s) removal.
                   This function returns True if the priority change for a publisher
                   is due to publisher(s) removal or False otherwise.""" 
                priority_sum = 0
                priority = pub[enumerations.PUBLISHER_PRIORITY]
                priority_changed = pub[enumerations.PUBLISHER_PRIORITY_CHANGED]
                for num in removed_list:
                        if num < priority:
                                priority_sum += 1
                return (priority == priority_changed + priority_sum)

        @staticmethod
        def __on_add_pub_help_clicked(widget):
                gui_misc.display_help("add-publisher")

        @staticmethod
        def __on_manage_help_clicked(widget):
                gui_misc.display_help("manage-publisher")

        def __on_modify_repo_help_clicked(self, widget):
                pagenum = self.w_modify_pub_notebook.get_current_page()
                if pagenum == MODIFY_NOTEBOOK_GENERAL_PAGE:
                        tag = "modify-publisher"
                elif pagenum == MODIFY_NOTEBOOK_CERTIFICATE_PAGE:
                        tag = "manage-certs"
                else:
                        tag = "pub-sig-policy"
                gui_misc.display_help(tag)

        @staticmethod
        def __update_publisher_details(pub, details_view):
                if pub == None:
                        return
                details_buffer = details_view.get_buffer()
                details_buffer.set_text("")
                uri_itr = details_buffer.get_start_iter()
                repo = pub.repository
                num = len(repo.origins)
                if pub.sys_pub:
                        details_buffer.insert_with_tags_by_name(uri_itr,
                            _("System Publisher"),
                            "level0")
                        sys_pub_str = _("Cannot be modified or removed.")
                        details_buffer.insert(uri_itr, "\n%s\n" % sys_pub_str)
                origin_txt = ngettext("Origin:\n", "Origins:\n", num)
                details_buffer.insert_with_tags_by_name(uri_itr,
                    origin_txt, "level0")
                uri_itr = details_buffer.get_end_iter()
                for origin in repo.origins:
                        details_buffer.insert(uri_itr, "%s\n" % str(origin))

        def __show_errors(self, errors, missing_ssl = False):
                error_msg = ""
                crerr = ""
                msg_type = gtk.MESSAGE_ERROR
                framework_error = False

                msg_title = _("Publisher Error")
                for err in errors:
                        if isinstance(err[1], api_errors.CatalogRefreshException):
                                res = gui_misc.get_catalogrefresh_exception_msg(err[1])
                                crerr = res[0]
                                framework_error = res[1]
                                logger.error(crerr)
                                gui_misc.notify_log_error(self.parent)
                        else:
                                error_msg += str(err[1])
                                error_msg += "\n\n"
                # If the only error is a CatalogRefreshException, which we
                # normally just log but do not display to the user, then
                # display it to the user.
                if error_msg == "":
                        error_msg = crerr
                        error_msg += "\n"
                        if framework_error and missing_ssl:
                                error_msg += _("Note: this may may be the result "
                                             "of specifying a https Origin, "
                                             "but no SSL key and certificate.\n")
                elif missing_ssl:
                        error_msg += _("Note: this error may be the result of "
                                     "specifing a https URI, "
                                     "but no SSL key and certificate.\n")
                if error_msg != "":
                        gui_misc.error_occurred(None, error_msg, msg_title, msg_type)

        @staticmethod
        def __keybrowse(w_parent, key_entry, cert_entry):
                chooser =  gtk.FileChooserDialog(
                    title=_("Specify SSL Key File"),
                    parent = w_parent,
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                chooser.set_transient_for(w_parent)
                chooser.set_modal(True)
                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        key = chooser.get_filename()
                        key_entry.set_text(key)
                        cert = key.replace("key", "certificate")
                        if key != cert and \
                            cert_entry.get_text() == "":
                                if os.path.isfile(cert):
                                        cert_entry.set_text(cert)
                chooser.destroy()

        @staticmethod
        def __certbrowse(w_parent, cert_entry):
                chooser =  gtk.FileChooserDialog(
                    title=_("Specify SSL Certificate File"),
                    parent = w_parent,
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                chooser.set_transient_for(w_parent)
                chooser.set_modal(True)
                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        cert_entry.set_text(
                            chooser.get_filename())
                chooser.destroy()

        @staticmethod
        def __delete_widget_handler_hide(widget, event):
                widget.hide()
                return True

        def __check_publisher_exists(self, api_o, name, origin_url):
                try:
                        pub = api_o.get_publisher(prefix=name, alias=name,
                            duplicate=True)
                        raise URIExistingPublisher(origin_url, pub)
                except api_errors.UnknownPublisher:
                        return False
                except api_errors.ApiException, e:
                        gobject.idle_add(self.__show_errors, [(name, e)])
                        return True

        def __setup_publisher_from_uri(self, alias, origin_url, ssl_key, ssl_cert):
                try:
                        self.api_o.reset()
                        repo = publisher.RepositoryURI(origin_url,
                            ssl_key = ssl_key, ssl_cert = ssl_cert)
                        pubs = self.api_o.get_publisherdata(repo=repo)
                        if not pubs:
                                raise NoPublishersForURI(origin_url)
                        src_pub = sorted(pubs)[0]
                        #For now only handling single Pub per Origin
                        if len(pubs) > 1:
                                if self.webinstall_new:
                                        client_name = _("Web Install")
                                else:
                                        client_name = _("Package Manager")
                                user_image_root = ""
                                if self.parent.image_directory != "/":
                                        user_image_root = "-R " + \
                                                self.parent.image_directory + " "
                                logger.warning(
                                _("Origin URI: %(origin_url)s"
                                "\nhas %(number_pubs)d publishers associated with it.\n"
                                "%(client_name)s will attempt to add the first "
                                "publisher, %(pub_name)s.\n"
                                "To add the remaining publishers use the command:\n"
                                "'pkg %(user_image_root)sset-publisher "
                                "-p %(origin_url)s'") %
                                {"origin_url": origin_url,
                                "number_pubs": len(pubs),
                                "client_name": client_name,
                                "pub_name": src_pub.prefix,
                                "user_image_root": user_image_root,
                                })
                                if not self.webinstall_new:
                                        gui_misc.notify_log_warning(self.parent)
                        src_repo = src_pub.repository
                        add_origins = []
                        if not src_repo or not src_repo.origins:
                                add_origins.append(origin_url)
                        repo = src_pub.repository
                        if not repo:
                                repo = publisher.Repository()
                                src_pub.repository = repo
                        for url in add_origins:
                                repo.add_origin(url)
                        return (src_pub, repo, True)
                except api_errors.ApiException, e:
                        if  self.__is_ssl_scheme(origin_url) and \
                            ((not ssl_key or len(ssl_key) == 0) or \
                            (not ssl_cert or len(ssl_cert) == 0)) and \
                            gui_misc.is_frameworkerror(e):
                                ssl_missing = True
                        else:
                                ssl_missing = False
                        gobject.idle_add(self.__show_errors, [(alias, e)], ssl_missing)
                        return (None, None, False)

        def __get_or_create_pub_with_url(self, api_o, name, origin_url):
                new_pub = False
                repo = None
                pub = None
                try:
                        pub = api_o.get_publisher(prefix=name, alias=name,
                            duplicate=True)
                        raise URIExistingPublisher(origin_url, pub)
                except api_errors.UnknownPublisher:
                        repo = publisher.Repository()
                        # We need to specify a name when creating a publisher
                        # object. It does not matter if it is wrong as the
                        # __update_publisher() call in __add_repository() will
                        # fail and it is dealt with there.
                        if name == None:
                                name = "None"
                        pub = publisher.Publisher(name, repository=repo)
                        new_pub = True
                        # This part is copied from "def publisher_set(img, args)"
                        # from the client.py as the publisher API is not ready yet.
                        if not repo.origins:
                                repo.add_origin(origin_url)
                                origin = repo.origins[0]
                        else:
                                origin = repo.origins[0]
                                origin.uri = origin_url
                except api_errors.ApiException, e:
                        gobject.idle_add(self.__show_errors, [(name, e)])
                return (pub, repo, new_pub)

        @staticmethod
        def __update_ssl_creds(pub, repo, ssl_cert, ssl_key):
                errors = []
                # Assume the user wanted to update the ssl_cert or ssl_key
                # information for *all* of the currently selected
                # repository's origins and mirrors.
                try:
                        for uri in repo.origins:
                                if uri.scheme not in publisher.SSL_SCHEMES:
                                        continue
                                uri.ssl_cert = ssl_cert
                                uri.ssl_key = ssl_key
                        for uri in repo.mirrors:
                                if uri.scheme not in publisher.SSL_SCHEMES:
                                        continue
                                uri.ssl_cert = ssl_cert
                                uri.ssl_key = ssl_key
                except api_errors.ApiException, e:
                        errors.append((pub, e))
                return errors

        @staticmethod
        def __get_fitr_model_from_tree(treeview):
                tsel = treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr == None:
                        return (None, None)
                model = selection[0]
                return (itr, model)

        @staticmethod
        def __show_error_label_with_format(w_label, error_string):
                error_str = ERROR_FORMAT % error_string
                w_label.set_markup(error_str)
                w_label.set_sensitive(True)
                w_label.show()

        def __is_url_valid(self, url):
                url_error = None
                if len(url) == 0:
                        return False, url_error
                try:
                        publisher.RepositoryURI(url)
                        return True, url_error
                except api_errors.PublisherError:
                        # Check whether the user has started typing a valid URL.
                        # If he has we do not display an error message.
                        valid_start = False
                        for val in publisher.SUPPORTED_SCHEMES:
                                check_str = "%s://" % val
                                if check_str.startswith(url):
                                        valid_start = True
                                        break 
                        if valid_start:
                                url_error = None
                        else:
                                url_error = _("URI is not valid")
                        return False, url_error
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return False, url_error

        def __validate_ssl_key_cert(self, origin_url, ssl_key, ssl_cert, 
            ignore_ssl_check_for_not_https = False):
                '''The SSL Cert and SSL Key may be valid and contain no error'''
                ssl_error = None
                ssl_valid = True
                if origin_url and not self.__is_ssl_scheme(origin_url):
                        if ignore_ssl_check_for_not_https:
                                return ssl_valid, ssl_error
                        if (ssl_key != None and len(ssl_key) != 0) or \
                            (ssl_cert != None and len(ssl_cert) != 0):
                                ssl_error = _("SSL should not be specified")
                                ssl_valid = False
                        elif (ssl_key == None or len(ssl_key) == 0) or \
                            (ssl_cert == None or len(ssl_cert) == 0):
                                ssl_valid = True
                elif origin_url == None or self.__is_ssl_scheme(origin_url):
                        if (ssl_key == None or len(ssl_key) == 0) or \
                            (ssl_cert == None or len(ssl_cert) == 0):
                        # Key and Cert need not be specified 
                                ssl_valid = True
                        elif not os.path.isfile(ssl_key):
                                ssl_error = _("SSL Key not found at specified location")
                                ssl_valid = False
                        elif not os.path.isfile(ssl_cert):
                                ssl_error = \
                                    _("SSL Certificate not found at specified location")
                                ssl_valid = False
                return ssl_valid, ssl_error

        @staticmethod
        def __is_ssl_scheme(uri):
                ret_val = False
                for val in publisher.SSL_SCHEMES:
                        if uri.startswith(val):
                                ret_val = True
                                break 
                return ret_val 

        @staticmethod
        def __init_mirrors_tree_view(treeview):
                # URI column - 0
                uri_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Mirror URI"),
                    uri_renderer,  text = 0)
                column.set_expand(True)
                treeview.append_column(column)

        @staticmethod
        def __init_origins_tree_view(treeview):
                # URI column - 0
                uri_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Origin URI"),
                    uri_renderer,  text = 0)
                column.set_expand(True)
                treeview.append_column(column)

        @staticmethod
        def __get_publishers_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,      # enumerations.PUBLISHER_PRIORITY
                        gobject.TYPE_INT,      # enumerations.PUBLISHER_PRIORITY_CHANGED
                        gobject.TYPE_STRING,   # enumerations.PUBLISHER_NAME
                        gobject.TYPE_STRING,   # enumerations.PUBLISHER_ALIAS
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBLISHER_ENABLED
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBLISHER_STICKY
                        gobject.TYPE_PYOBJECT, # enumerations.PUBLISHER_OBJECT
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBLISHER_ENABLE_CHANGED
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBLISHER_STICKY_CHANGED
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBLISHER_REMOVED
                        )

        @staticmethod
        def __get_mirrors_origins_liststore():
                return gtk.ListStore(
                        gobject.TYPE_STRING,      # name
                        )

        @staticmethod
        def __publishers_filter(model, itr):
                return not model.get_value(itr, enumerations.PUBLISHER_REMOVED)

        @staticmethod
        def __toggle_data_function(column, renderer, model, itr, data):
                if itr:
                        # Do not allow to remove the publisher if it is a system
                        # publisher
                        val = True
                        pub = model.get_value(itr,
                            enumerations.PUBLISHER_OBJECT)
                        if pub.sys_pub:
                                val = False
                        renderer.set_property("sensitive", val)

        @staticmethod
        def __get_registration_uri(repo):
                #TBD: Change Publisher API to return an RegistrationURI or a String
                # but not either.
                # Currently RegistrationURI is coming back with a trailing / this should
                # be removed.
                if repo == None:
                        return None
                if repo.registration_uri == None:
                        return None
                ret_uri = None
                if isinstance(repo.registration_uri, str):
                        if len(repo.registration_uri) > 0:
                                ret_uri = repo.registration_uri.strip("/")
                elif isinstance(repo.registration_uri, publisher.RepositoryURI):
                        uri = repo.registration_uri.uri
                        if uri != None and len(uri) > 0:
                                ret_uri = uri.strip("/")
                return ret_uri

#-----------------------------------------------------------------------------#
# Public Methods
#-----------------------------------------------------------------------------#
        def webinstall_new_pub(self, parent, pub = None):
                if pub == None:
                        return
                self.repository_modify_publisher = pub
                repo = pub.repository
                origin_uri = ""
                if repo != None and repo.origins != None and len(repo.origins) > 0:
                        origin_uri = repo.origins[0].uri
                if origin_uri != None and self.__is_ssl_scheme(origin_uri):
                        gui_misc.set_modal_and_transient(self.w_add_publisher_dialog, 
                            parent)
                        self.main_window = self.w_add_publisher_dialog
                        self.__on_manage_add_clicked(None)
                        self.w_add_publisher_url.set_text(origin_uri)
                        self.w_add_publisher_alias.set_text(pub.alias)
                        self.w_add_pub_label.hide()
                        self.w_add_pub_instr_label.hide()
                        self.w_add_publisher_url.set_sensitive(False)
                        self.w_add_publisher_alias.set_sensitive(False)
                        reg_uri = self.__get_registration_uri(repo)
                        if reg_uri == None or len(reg_uri) == 0:
                                reg_uri = origin_uri
                        self.w_registration_link.set_uri(reg_uri)
                        self.w_registration_box.show()
                        self.w_ssl_box.show()
                        self.__validate_url(self.w_add_publisher_url,
                            w_ssl_key=self.w_key_entry, w_ssl_cert=self.w_cert_entry)
                        self.w_add_error_label.hide()
                else:
                        self.main_window = parent
                        self.w_ssl_box.hide()
                        self.__do_add_repository()

        def webinstall_enable_disable_pubs(self, parent, pub_names, to_enable):
                if pub_names == None:
                        return
                num = len(pub_names)
                if to_enable:
                        msg = ngettext("Enabling Publisher", "Enabling Publishers", num)
                else:
                        msg = ngettext("Disabling Publisher", "Disabling Publishers", num)
                self.publishers_apply.set_title(msg)

                self.__run_with_prog_in_thread(self.__proceed_enable_disable,
                    parent, None, pub_names, to_enable)

        def update_label_text(self, markup_text):
                self.__g_update_details_text(markup_text)

        def update_details_text(self, text, *tags):
                self.__g_update_details_text(text, *tags)

        def update_progress(self, current_progress, total_progress):
                pass

        def start_bouncing_progress(self):
                pass

        def is_progress_bouncing(self):
                self.pylintstub = self
                return True

        def stop_bouncing_progress(self):
                pass

        def display_download_info(self):
                pass

        def display_phase_info(self, phase_name, cur_n, goal_n):
                pass

        def reset_label_text_after_delay(self):
                pass

class URIExistingPublisher(api_errors.ApiException):
        def __init__(self, uri, pub):
                api_errors.ApiException.__init__(self)
                self.uri = uri
                self.pub = pub

        def __str__(self):
                return _("The URI '%(uri)s' points to a publisher "
                    "'%(publisher)s' which already exists "
                    "on the system.") % { "uri": self.uri,
                    "publisher": self.pub }

class NoPublishersForURI(api_errors.ApiException):
        def __init__(self, uri):
                api_errors.ApiException.__init__(self)
                self.uri = uri

        def __str__(self):
                return _("There are no publishers associated with the URI "
                   "'%s'.") % self.uri
