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
# Copyright (c) 2008, 2012, Oracle and/or its affiliates. All rights reserved.
#

DEFAULT_CONFIRMATION_WIDTH = 550        # Width & height of single confirmation
DEFAULT_CONFIRMATION_HEIGHT = 200       # frame. The confirmation dialog may
                                        # consist of frames for packages to be 
                                        # installed, removed or updated.
DISPLAY_DELAY = 200                     # Delay before updating GUI when 
                                        # displaying download or phase info
RESET_PACKAGE_DELAY = 2000              # Delay before label text is reset
                                        # Also used to reset window text during install
DIALOG_DEFAULT_WIDTH = 450              # Default Width of Progress Dialog
DIALOG_EXPANDED_DETAILS_HEIGHT = 462    # Height of Progress Dialog when Details expanded
DIALOG_INSTALL_COLLAPSED_HEIGHT = 242   # Heights of progress dialog when Details
                                        # collapsed for install, remove and done stages
DIALOG_REMOVE_COLLAPSED_HEIGHT = 220
DIALOG_DONE_COLLAPSED_HEIGHT = 126

DIALOG_UM_EXTRA_HEIGHT = 60             # Extra height needed when in UM mode
DIALOG_RELEASE_NOTE_OFFSET = 34         # Additional space required if displaying
                                        # Release notes link below Details
import errno
import os
import sys
import time
import pango
import datetime
import traceback
from gettext import ngettext
from threading import Thread
from threading import Condition
try:
        import gobject
        import gtk
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)

import pkg.gui.progress as progress
import pkg.misc as misc
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.gui.beadmin as beadm
import pkg.gui.uarenamebe as uarenamebe
import pkg.gui.misc as gui_misc
import pkg.gui.enumerations as enumerations
import pkg.gui.pmgconf as pmgconf
from pkg.client import global_settings

logger = global_settings.logger
debug = False

class InstallUpdate(progress.GuiProgressTracker):
        def __init__(self, list_of_packages, parent, image_directory,
            action = -1, parent_name = "", pkg_list = None, main_window = None,
            icon_confirm_dialog = None, title = None, web_install = False,
            confirmation_list = None, show_confirmation = False, api_lock = None,
            gconf = None, facets = None):
                if action == -1:
                        return
                self.gconf = gconf
                progress.GuiProgressTracker.__init__(self, indent=True)
                if self.gconf == None:
                        self.gconf = pmgconf.PMGConf()
                self.retry = False
                self.web_install = web_install
                self.web_updates_list = None
                self.web_install_all_installed = False
                self.parent = parent
                self.api_lock = api_lock
                self.facets = facets
                self.api_o = gui_misc.get_api_object(image_directory,
                    self, main_window)
                if self.api_o == None:
                        return
                self.parent_name = parent_name
                self.confirmation_list = confirmation_list
                if confirmation_list == None:
                        self.confirmation_list = []
                self.show_confirmation = show_confirmation
                if main_window == None:
                        self.top_level = True
                else:
                        self.top_level = False
                self.ipkg_ipkgui_list = pkg_list
                self.icon_confirm_dialog = icon_confirm_dialog
                self.title = title
                self.w_main_window = main_window
                if self.icon_confirm_dialog == None and self.w_main_window != None:
                        self.icon_confirm_dialog = self.w_main_window.get_icon()

                gladefile = os.path.join(self.parent.application_dir,
                    "usr/share/package-manager/packagemanager.ui")
                builder = gtk.Builder()
                builder.add_from_file(gladefile)
                self.w_dialog = builder.get_object("createplandialog")
                self.original_title = None
                if self.w_main_window:
                        self.original_title = self.w_main_window.get_title()
                if self.top_level:
                        globals()["DIALOG_INSTALL_COLLAPSED_HEIGHT"] = \
                                DIALOG_INSTALL_COLLAPSED_HEIGHT + DIALOG_UM_EXTRA_HEIGHT
                        globals()["DIALOG_DONE_COLLAPSED_HEIGHT"] = \
                                DIALOG_DONE_COLLAPSED_HEIGHT + DIALOG_UM_EXTRA_HEIGHT
                        self.w_dialog.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_NORMAL)
                        self.w_dialog.set_icon(self.icon_confirm_dialog)
                        self.w_main_window = self.w_dialog
                        self.original_title = _("Update Manager")
                        w_icon_um = builder.get_object("icon_um")
                        w_icon_um.set_from_pixbuf(self.icon_confirm_dialog)
                else:
                        um_vbox = builder.get_object("um_title_vbox")
                        um_vbox.set_property("visible", False)

                self.license_cv = Condition()
                self.list_of_packages = list_of_packages
                self.accept_license_done = False
                self.action = action
                self.canceling = False
                self.current_stage_name = None
                self.ip = None
                self.ips_update = False
                self.operations_done = False
                self.operations_done_ex = False
                self.prev_ind_phase = None
                self.reboot_needed = False
                self.uarenamebe_o = None
                self.label_text = None
                self.prev_pkg = None
                self.prev_prog = -1
                self.prog = 0
                self.progress_stop_timer_running = False
                self.pylint_stub = None
                self.reset_id = 0
                self.reset_window_id = 0
                self.display_download_id = 0
                self.update_progress_id = 0
                self.stages = {
                          1:[_("Preparing..."), _("Preparation")],
                          2:[_("Downloading..."), _("Download")],
                          3:[_("Installing..."), _("Install")],
                         }
                self.current_stage_label_done = self.stages[1][1]
                self.stop_progress_bouncing = False
                self.stopped_bouncing_progress = True
                self.update_list = {}

                self.w_confirm_dialog = builder.get_object("confirmdialog")
                self.w_install_expander = \
                    builder.get_object("install_expander")
                self.w_install_frame = \
                    builder.get_object("install_frame")
                self.w_install_treeview = \
                    builder.get_object("install_treeview")
                self.w_update_expander = \
                    builder.get_object("update_expander")
                self.w_update_frame = \
                    builder.get_object("update_frame")
                self.w_update_treeview = \
                    builder.get_object("update_treeview")
                self.w_remove_expander = \
                    builder.get_object("remove_expander")
                self.w_remove_frame = \
                    builder.get_object("frame3")
                self.w_remove_treeview = \
                    builder.get_object("remove_treeview")
                self.w_confirm_ok_button =  \
                    builder.get_object("confirm_ok_button")
                self.w_confirm_cancel_button =  \
                    builder.get_object("confirm_cancel_button")
                self.w_confirm_label =  \
                    builder.get_object("confirmdialog_confirm_label")
                self.w_confirm_donotshow =  \
                    builder.get_object("confirm_donotshow")

                self.w_confirm_dialog.set_icon(self.icon_confirm_dialog)
                gui_misc.set_modal_and_transient(self.w_confirm_dialog,
                    self.w_main_window)

                self.w_expander = builder.get_object("details_expander")
                self.w_cancel_button = builder.get_object("cancelcreateplan")
                self.w_help_button = builder.get_object("helpcreateplan")
                if self.top_level:
                        self.w_help_button.set_property("visible", True)
                else:
                        self.w_help_button.set_property("visible", False)

                self.w_close_button = builder.get_object("closecreateplan")
                self.w_release_notes = builder.get_object("release_notes")
                self.w_release_notes_link = \
                    builder.get_object("ua_release_notes_button")
                self.w_progressbar = builder.get_object("createplanprogress")
                self.w_details_textview = builder.get_object("createplantextview")

                self.w_stage2 = builder.get_object("stage2")
                self.w_stages_box = builder.get_object("stages_box")
                self.w_stage1_label = builder.get_object("label_stage1")
                self.w_stage1_icon = builder.get_object("icon_stage1")
                self.w_stage2_label = builder.get_object("label_stage2")
                self.w_stage2_icon = builder.get_object("icon_stage2")
                self.w_stage3_label = builder.get_object("label_stage3")
                self.w_stage3_icon = builder.get_object("icon_stage3")
                self.w_stages_label = builder.get_object("label_stages")
                self.w_stages_icon = builder.get_object("icon_stages")
                self.current_stage_label = self.w_stage1_label
                self.current_stage_icon = self.w_stage1_icon

                self.w_stages_label.set_line_wrap(True)
                self.w_stages_label.set_size_request(DIALOG_DEFAULT_WIDTH - 20, -1)
                
                self.done_icon = gui_misc.get_icon(
                    self.parent.icon_theme, "progress_checkmark")
                blank_icon = gui_misc.get_icon(
                    self.parent.icon_theme, "progress_blank")

                checkmark_icon = gui_misc.get_icon(
                    self.parent.icon_theme, "pm-check", 24)

                self.w_stages_icon.set_from_pixbuf(checkmark_icon)
                
                self.w_stage1_icon.set_from_pixbuf(blank_icon)
                self.w_stage2_icon.set_from_pixbuf(blank_icon)
                self.w_stage3_icon.set_from_pixbuf(blank_icon)

                proceed_txt = _("_Proceed")
                gui_misc.change_stockbutton_label(self.w_confirm_ok_button, proceed_txt)

                infobuffer = self.w_details_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                infobuffer.create_tag("level1", left_margin=30, right_margin=10)
                infobuffer.create_tag("level2", left_margin=50, right_margin=10)

                self.w_progressbar.set_pulse_step(0.02)
                self.w_release_notes.hide()

                self.w_license_dialog = builder.get_object("license_dialog")
                self.w_license_label = builder.get_object("instruction_label")
                self.w_license_text = builder.get_object("textview1")
                self.w_license_accept_checkbutton = \
                    builder.get_object("license_accept_checkbutton")
                self.w_license_accept_button = \
                    builder.get_object("license_accept_button")
                self.w_license_reject_button = \
                    builder.get_object("license_reject_button")
                self.accept_text = gui_misc.get_stockbutton_label_label(
                    self.w_license_accept_button)
                gui_misc.change_stockbutton_label(self.w_license_reject_button,
                    _("_Reject"))
                self.current_license_no = 0
                self.packages_with_license = None
                self.packages_with_license_result = []
                self.n_licenses = 0
                self.dlg_expanded_details_h = DIALOG_EXPANDED_DETAILS_HEIGHT
                self.dlg_width = DIALOG_DEFAULT_WIDTH
                self.dlg_install_collapsed_h = DIALOG_INSTALL_COLLAPSED_HEIGHT
                self.dlg_remove_collapsed_h = DIALOG_REMOVE_COLLAPSED_HEIGHT
                self.dlg_done_collapsed_h = DIALOG_DONE_COLLAPSED_HEIGHT

                self.__setup_signals()
                if not self.top_level:
                        gui_misc.set_modal_and_transient(self.w_dialog,
                            self.w_main_window)
                self.w_license_dialog.set_icon(self.icon_confirm_dialog)
                gui_misc.set_modal_and_transient(self.w_license_dialog,
                    self.w_dialog)
                self.__start_action()
                self.__setup_createplan_dlg_sizes()

        def __setup_signals(self):
                signals_table = [
                    (self.w_cancel_button, "clicked",
                     self.__on_cancelcreateplan_clicked),
                    (self.w_close_button, "clicked",
                     self.__on_closecreateplan_clicked),
                    (self.w_dialog, "delete_event",
                     self.__on_createplandialog_delete),
                    (self.w_expander, "activate",
                     self.__on_details_expander_activate),
                    (self.w_help_button, "clicked",
                     self.__on_help_button_clicked),

                    (self.w_license_reject_button, "clicked",
                     self.__on_license_reject_button_clicked),
                    (self.w_license_accept_button, "clicked",
                     self.__on_license_accept_button_clicked),
                    (self.w_license_accept_checkbutton, "toggled",
                     self.__on_license_accept_checkbutton_toggled),
                    (self.w_license_dialog, "delete_event", 
                     self.__on_license_dialog_delete),

                    (self.w_confirm_dialog, "delete_event", 
                     self.__on_confirmdialog_delete_event),
                    (self.w_confirm_donotshow, "toggled",
                     self.__on_confirm_donotshow_toggled),
                    (self.w_confirm_cancel_button, "clicked",
                     self.__on_confirm_cancel_button_clicked),
                    (self.w_confirm_ok_button, "clicked",
                     self.__on_confirm_ok_button_clicked),
                     ]
                for widget, signal_name, callback in signals_table:
                        widget.connect(signal_name, callback)

        def __setup_createplan_dlg_sizes(self):
                #Get effective screen space available (net of panels and docks)
                #instead of using gtk.gdk.screen_width() and gtk.gdk.screen_height()
                root_win = gtk.gdk.get_default_root_window()
                net_workarea_prop = gtk.gdk.atom_intern('_NET_WORKAREA')
                sw, sh = root_win.property_get(net_workarea_prop)[2][2:4]
                sw -= 28 # Default width of Panel accounts for bottom or side System Panel
                sh -= 28
                scale = gui_misc.get_scale(self.w_details_textview)

                if DIALOG_EXPANDED_DETAILS_HEIGHT * scale <= sh:
                        self.dlg_expanded_details_h = \
                                (int) (DIALOG_EXPANDED_DETAILS_HEIGHT * scale)
                        self.dlg_install_collapsed_h = \
                                (int) (DIALOG_INSTALL_COLLAPSED_HEIGHT * scale)
                        self.dlg_remove_collapsed_h = \
                                (int) (DIALOG_REMOVE_COLLAPSED_HEIGHT * scale)
                        self.dlg_done_collapsed_h = \
                                (int) (DIALOG_DONE_COLLAPSED_HEIGHT * scale)
                else:
                        self.dlg_expanded_details_h = sh
                        if DIALOG_INSTALL_COLLAPSED_HEIGHT * scale <= sh:
                                self.dlg_install_collapsed_h = \
                                        (int) (DIALOG_INSTALL_COLLAPSED_HEIGHT * scale)
                                self.dlg_remove_collapsed_h = \
                                        (int) (DIALOG_REMOVE_COLLAPSED_HEIGHT * scale)
                                self.dlg_done_collapsed_h = \
                                        (int) (DIALOG_DONE_COLLAPSED_HEIGHT * scale)
                        else:
                                self.dlg_install_collapsed_h = sh
                                if DIALOG_REMOVE_COLLAPSED_HEIGHT * scale <= sh:
                                        self.dlg_remove_collapsed_h = (int) \
                                                (DIALOG_REMOVE_COLLAPSED_HEIGHT * scale)
                                        self.dlg_done_collapsed_h = (int) \
                                                (DIALOG_DONE_COLLAPSED_HEIGHT * scale)
                                else:
                                        self.dlg_remove_collapsed_h = sh
                                        if DIALOG_DONE_COLLAPSED_HEIGHT * scale <= sh:
                                                self.dlg_done_collapsed_h = (int) \
                                                        (DIALOG_DONE_COLLAPSED_HEIGHT * \
                                                        scale)
                                        else:
                                                self.dlg_done_collapsed_h = sh

                if DIALOG_DEFAULT_WIDTH * scale <= sw:
                        self.dlg_width = \
                                (int) (DIALOG_DEFAULT_WIDTH * scale)
                else:
                        self.dlg_width = sw

                if debug:
                        print "CreatePlan Dialog Sizes: window", sw, sh, scale, " dlg ", \
                                self.dlg_width, self.dlg_expanded_details_h, " coll ", \
                                self.dlg_install_collapsed_h, \
                                self.dlg_remove_collapsed_h, self.dlg_done_collapsed_h

                if self.gconf.details_expanded:
                        self.__set_dialog_size(self.dlg_width,
                            self.dlg_expanded_details_h)
                else:
                        if not (self.w_stage2.flags() & gtk.VISIBLE):
                                self.__set_dialog_size(self.dlg_width,
                                        self.dlg_remove_collapsed_h)
                        else:
                                self.__set_dialog_size(self.dlg_width,
                                        self.dlg_install_collapsed_h)

        def __start_action(self):
                if self.action == enumerations.REMOVE:
                        # For the remove, we are not showing the download stage
                        self.stages[3] = [_("Removing..."), _("Remove")]
                        self.w_stage3_label.set_text(self.stages[3][1])
                        self.w_stage2.hide()
                        self.w_dialog.set_title(_("Remove"))

                        if self.show_confirmation and len(self.confirmation_list) > 0:
                                self.w_confirm_dialog.set_title(_("Remove Confirmation"))
                                pkgs_no = len(self.confirmation_list)
                                remove_text = ngettext(
                                    "Review the package to be removed",
                                    "Review the packages to be removed", pkgs_no)
                                self.w_confirm_label.set_markup("<b>"+remove_text+"</b>")

                                self.w_install_expander.hide()
                                self.w_update_expander.hide()
                                if not self.retry:
                                        self.__init_confirmation_tree_view(
                                            self.w_remove_treeview)
                                liststore = gtk.ListStore(str, str, str)
                                for sel_pkg in self.confirmation_list:
                                        liststore.append(
                                            [sel_pkg[enumerations.CONFIRM_NAME],
                                            sel_pkg[enumerations.CONFIRM_PUB],
                                            sel_pkg[enumerations.CONFIRM_DESC]])
                                liststore.set_default_sort_func(lambda *args: -1) 
                                liststore.set_sort_column_id(0, gtk.SORT_ASCENDING)
                                self.w_remove_treeview.set_model(liststore)
                                self.w_remove_expander.set_expanded(True)
                                self.w_confirm_ok_button.grab_focus()
                                self.w_confirm_dialog.show()
                        else:
                                self.__proceed_with_stages()
                elif self.action == enumerations.IMAGE_UPDATE:
                        if not self.top_level:
                                self.w_dialog.set_title(_("Updates"))
                        self.__proceed_with_stages()
                elif self.action == enumerations.UPDATE_FACETS:
                        if not self.top_level:
                                self.w_dialog.set_title(
                                    _("Update Optional Components"))
                        self.__proceed_with_stages()
                else:
                        if self.title != None:
                                self.w_dialog.set_title(self.title)
                        else:
                                self.w_dialog.set_title(_("Install/Update"))

                        if self.show_confirmation and len(self.confirmation_list) > 0:
                                self.w_remove_expander.hide()
                                to_install = gtk.ListStore(str, str, str)
                                to_update = gtk.ListStore(str, str, str)
                                for cpk in self.confirmation_list:
                                        if cpk[enumerations.CONFIRM_STATUS] == \
                                            api.PackageInfo.UPGRADABLE:
                                                to_update.append(
                                                    [cpk[enumerations.CONFIRM_NAME], 
                                                    cpk[enumerations.CONFIRM_PUB],
                                                    cpk[enumerations.CONFIRM_DESC]])
                                        else:
                                                to_install.append(
                                                    [cpk[enumerations.CONFIRM_NAME],
                                                    cpk[enumerations.CONFIRM_PUB],
                                                    cpk[enumerations.CONFIRM_DESC]])

                                operation_txt = _("Install/Update Confirmation")
                                install_text = ngettext(
                                    "Review the package to be Installed/Updated",
                                    "Review the packages to be Installed/Updated",
                                     len(self.confirmation_list))

                                if len(to_install) == 0:
                                        operation_txt = _("Updates Confirmation")
                                        install_text = ngettext(
                                            "Review the package to be Updated",
                                            "Review the packages to be Updated",
                                            len(to_update))

                                if len(to_update) == 0:
                                        operation_txt = _("Install Confirmation")
                                        install_text = ngettext(
                                            "Review the package to be Installed",
                                            "Review the packages to be Installed",
                                            len(to_install))

                                self.w_confirm_dialog.set_title(operation_txt)
                                self.w_confirm_label.set_markup("<b>"+install_text+"</b>")

                                if len(to_install) > 0:
                                        self.__init_confirmation_tree_view(
                                            self.w_install_treeview)
                                        to_install.set_default_sort_func(lambda *args: -1)
                                        to_install.set_sort_column_id(0,
                                            gtk.SORT_ASCENDING)
                                        self.w_install_treeview.set_model(to_install)
                                        self.w_install_expander.set_expanded(True)
                                else:
                                        self.w_install_expander.hide()
                                if len(to_update) > 0:
                                        self.__init_confirmation_tree_view(
                                            self.w_update_treeview)
                                        to_update.set_default_sort_func(lambda *args: -1) 
                                        to_update.set_sort_column_id(0,
                                            gtk.SORT_ASCENDING)
                                        self.w_update_treeview.set_model(to_update)
                                        self.w_update_expander.set_expanded(True)
                                else:
                                        self.w_update_expander.hide()
                                self.w_confirm_ok_button.grab_focus()
                                self.w_confirm_dialog.show()
                        else:
                                self.__proceed_with_stages()

        @staticmethod
        def __init_confirmation_tree_view(treeview):
                name_renderer = gtk.CellRendererText()
                name_renderer.set_property("ellipsize", pango.ELLIPSIZE_END)
                column = gtk.TreeViewColumn(_('Name'), name_renderer,
                    text = enumerations.CONFIRM_NAME)
                column.set_resizable(True)
                column.set_min_width(150)
                column.set_sort_column_id(0)
                column.set_sort_indicator(True)
                treeview.append_column(column)
                publisher_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_('Publisher'), publisher_renderer,
                    text = enumerations.CONFIRM_PUB)
                column.set_resizable(True)
                column.set_sort_column_id(1)
                column.set_sort_indicator(True)
                treeview.append_column(column)
                summary_renderer = gtk.CellRendererText()
                summary_renderer.set_property("ellipsize", pango.ELLIPSIZE_END)
                column = gtk.TreeViewColumn(_('Summary'), summary_renderer,
                    text = enumerations.CONFIRM_DESC)
                column.set_resizable(True)
                column.set_sort_column_id(2)
                column.set_sort_indicator(True)
                treeview.append_column(column)

        def __on_confirm_donotshow_toggled(self, widget):
                if self.action == enumerations.REMOVE:
                        self.gconf.set_show_remove(not self.gconf.show_remove)
                elif self.action == enumerations.IMAGE_UPDATE:
                        self.gconf.set_show_image_update(not self.gconf.show_image_update)
                elif self.action == enumerations.INSTALL_UPDATE:
                        self.gconf.set_show_install(not self.gconf.show_install)

        def __on_confirm_ok_button_clicked(self, widget):
                if self.action == enumerations.INSTALL_UPDATE or \
                    self.action == enumerations.REMOVE:
                        self.__on_confirm_cancel_button_clicked(None)
                        if self.top_level:
                                self.w_main_window = self.w_dialog
                        self.__proceed_with_stages()
                else:
                        self.w_expander.set_expanded(self.gconf.details_expanded)
                        self.w_dialog.show()
                        self.__on_confirm_cancel_button_clicked(None)
                        self.__proceed_with_stages(continue_operation = True)

        def __on_confirmdialog_delete_event(self, widget, event):
                self.__on_confirm_cancel_button_clicked(widget)
                return True

        def __on_confirm_cancel_button_clicked(self, widget):
                self.w_confirm_dialog.hide()
                if self.top_level and widget: # User clicked cacnel, widget != None
                        gobject.idle_add(self.parent.install_terminated)

        def __on_createplandialog_delete(self, widget, event):
                self.__on_cancelcreateplan_clicked(None)
                return True

        def __set_dialog_size(self, w, h):
                self.w_dialog.set_size_request(w, h)
                self.w_dialog.resize(w, h)

        def __on_details_expander_activate(self, widget):
                collapsed = self.w_expander.get_expanded()
                if collapsed:
                        if not (self.w_stages_box.flags() & gtk.VISIBLE):
                                self.__set_dialog_size(self.dlg_width,
                                        self.dlg_done_collapsed_h)
                        elif not (self.w_stage2.flags() & gtk.VISIBLE):
                                self.__set_dialog_size(self.dlg_width,
                                        self.dlg_remove_collapsed_h)
                        else:
                                self.__set_dialog_size(self.dlg_width,
                                        self.dlg_install_collapsed_h)
                else:
                        self.__set_dialog_size(self.dlg_width,
                            self.dlg_expanded_details_h)

                self.gconf.set_details_expanded(not self.gconf.details_expanded)

        def __on_cancelcreateplan_clicked(self, widget):
                '''Handler for signal send by cancel button, which user might press
                during evaluation stage - while the dialog is creating plan'''
                if self.api_o.can_be_canceled() and self.operations_done_ex == False:
                        self.canceling = True
                        Thread(target = self.api_o.cancel, args = ()).start()
                        cancel_txt = _("Canceling...")
                        txt = "<b>" + self.current_stage_label_done + " - " \
                            + cancel_txt + "</b>"
                        gobject.idle_add(self.current_stage_label.set_markup, txt)
                        gobject.idle_add(self.current_stage_icon.set_from_stock,
                            gtk.STOCK_CANCEL, gtk.ICON_SIZE_MENU)
                        gobject.idle_add(self.w_stages_label.set_markup, cancel_txt)
                        self.w_cancel_button.set_sensitive(False)
                        if self.top_level:
                                gobject.idle_add(self.parent.install_terminated)
                if self.operations_done or self.operations_done_ex:
                        self.w_dialog.hide()
                        if self.web_install:
                                if self.operations_done_ex == False and \
                                        not self.web_install_all_installed:
                                        gobject.idle_add(self.parent.update_package_list,
                                            None)
                                else:
                                        gobject.idle_add(self.parent.update_package_list,
                                            self.web_updates_list)
                                return
                        if self.top_level:
                                gobject.idle_add(self.parent.install_terminated)
                        gobject.idle_add(self.parent.update_package_list, None)

        def __on_closecreateplan_clicked(self, widget):
                self.w_close_button.hide()
                self.w_dialog.hide()
                buf = self.w_details_textview.get_buffer()
                buf.set_text("")
                self.w_expander.set_expanded(False)
                self.__start_action()
                self.retry = False
                return

        def __on_help_button_clicked(self, widget):
                if self.top_level:
                        gui_misc.display_help("using_um")
                elif self.action == enumerations.INSTALL_UPDATE:
                        gui_misc.display_help("install-pkg")
                elif self.action == enumerations.REMOVE:
                        gui_misc.display_help("remove-pkg")
                else:
                        gui_misc.display_help("update-pkg")

        def __ipkg_ipkgui_uptodate(self):
                if self.ipkg_ipkgui_list == None:
                        return True
                for pd in self.api_o.gen_plan_install(self.ipkg_ipkgui_list):
                        continue
                upgrade_needed = not self.api_o.planned_nothingtodo(
                    li_ignore_all=True)
                return not upgrade_needed

        def __proceed_with_stages(self, continue_operation = False):
                if continue_operation == False:
                        self.__start_stage_one()
                        self.w_expander.set_expanded(self.gconf.details_expanded)
                        self.w_dialog.show()
                Thread(target = self.__proceed_with_stages_thread_ex,
                    args = (continue_operation, )).start()

        def __proceed_with_stages_thread_ex(self, continue_operation = False):
                if self.api_lock:
                        self.api_lock.acquire()
                self.__proceed_with_stages_thread_ex_with_lock(continue_operation)
                gui_misc.release_lock(self.api_lock)

        def __proceed_with_stages_thread_ex_with_lock(self, continue_operation = False):
                try:
                        try:
                                if self.action == enumerations.IMAGE_UPDATE and \
                                    continue_operation == False:
                                        self.__start_substage(
                                            _("Ensuring %s is up to date...") %
                                            self.parent_name,
                                            bounce_progress=True)
                                        self.set_purpose(self.PURPOSE_PKG_UPDATE_CHK)
                                        solaris_image = True
                                        ips_uptodate = True
                                        notfound = self.__installed_fmris_from_args(
                                            [gui_misc.package_name["SUNWipkg"],
                                            gui_misc.package_name["SUNWcs"]])
                                        if notfound:
                                                solaris_image = False
                                        if solaris_image:
                                                ips_uptodate = \
                                                    self.__ipkg_ipkgui_uptodate()
                                        self.set_purpose(self.PURPOSE_NORMAL)
                                        if not ips_uptodate:
                                                # Do the stuff with installing
                                                # pkg pkg-gui and restart in the
                                                # special mode
                                                self.ips_update = True
                                                self.__proceed_with_ipkg_thread()
                                                return
                                        self.update_details_text(_("%s "
                                            "is up to date.\n") % \
                                            self.parent_name, "level1")         
                                        gobject.idle_add(
                                            self.__create_uarenamebe_o)
                                        self.api_o.reset()
                                if continue_operation == False:
                                        self.__proceed_with_stages_thread()
                                else:
                                        self.__continue_with_stages_thread()
                        except (MemoryError, EnvironmentError), __e:
                                if isinstance(__e, EnvironmentError) and \
                                    __e.errno != errno.ENOMEM:
                                        raise
                                msg = misc.out_of_memory()
                                self.__g_error_stage(msg)
                                return
                        except RuntimeError, ex:
                                msg = str(ex)
                                if msg == "cannot release un-aquired lock":
                                        logger.error(msg)
                                else:
                                        self.__g_error_stage(msg)
                                        return
                except api_errors.InventoryException, e:
                        msg = _("Inventory exception:\n")
                        if e.illegal:
                                for i in e.illegal:
                                        msg += "\tpkg:\t" + i +"\n"
                        else:
                                msg = "%s" % e
                        self.__g_error_stage(msg)
                        return
                except api_errors.CatalogRefreshException, e:
                        res = gui_misc.get_catalogrefresh_exception_msg(e)
                        self.__g_error_stage(res[0])
                        return
                except api_errors.TransportError, ex:
                        msg = _("Please check the network "
                            "connection.\nIs the repository accessible?\n\n"
                            "%s") % str(ex)
                        self.__g_error_stage(msg)
                        return
                except api_errors.InvalidDepotResponseException, e:
                        msg = _("\nUnable to contact a valid package depot. "
                            "Please check your network settings and "
                            "attempt to contact the server using a web "
                            "browser.\n\n%s") % str(e)
                        self.__g_error_stage(msg)
                        return
                except api_errors.IpkgOutOfDateException:
                        msg = _("pkg(5) appears to be out of "
                            "date and should be updated.\n"
                            "Please update %s package") % (
                            gui_misc.package_name["SUNWipkg"])
                        self.__g_error_stage(msg)
                        return
                except api_errors.NonLeafPackageException, nlpe:
                        msg = _("Cannot remove:\n\t%s\n"
                                "Due to the following packages that "
                                "depend on it:\n") % nlpe.fmri.get_name()
                        for pkg_a in nlpe.dependents:
                                msg += "\t" + pkg_a.get_name() + "\n"

                        stem = nlpe.fmri.get_pkg_stem()
                        self.list_of_packages.remove(stem)
                        if self.confirmation_list:
                                for item in self.confirmation_list:
                                        if item[enumerations.CONFIRM_STEM] == stem:
                                                self.confirmation_list.remove(item)
                                                break 
                        if len(self.list_of_packages) > 0:
                                if self.w_close_button.get_use_stock():
                                        label = gui_misc.get_stockbutton_label_label(
                                            self.w_close_button)
                                else:
                                        label = self.w_close_button.get_label()
                                label = label.replace("_", "")
                                msg += "\n"
                                msg += _("Press %(button)s "
                                    "button to continue removal without"
                                    "\n\t%(package)s\n") % \
                                    {"button": label,
                                     "package": nlpe.fmri.get_name()}
                                self.retry = True
                                self.w_close_button.show()
                        self.__g_error_stage(msg)
                        return
                except api_errors.ProblematicPermissionsIndexException, err:
                        msg = str(err)
                        msg += _("\nFailure to consistently execute pkg "
                            "commands when running %s as a privileged user is "
                            "often a source of this problem.") % self.parent_name
                        msg += _("\nTo rebuild index, please execute the "
                            "following command as a privileged user:")
                        msg += _("\n\tpkg rebuild-index")
                        self.__g_error_stage(msg)
                        return
                except api_errors.CorruptedIndexException:
                        msg = _("There was an error during installation. The search "
                            "index is corrupted. You might want try to fix this "
                            "problem by executing the following command as a "
                            "privileged user:\n"
                            "\tpkg rebuild-index")
                        self.__g_error_stage(msg)
                        return
                except api_errors.ImageUpdateOnLiveImageException:
                        msg = _("This is a Live Image. The install "
                            "operation can't be performed.")
                        self.__g_error_stage(msg)
                        return
                except api_errors.RebootNeededOnLiveImageException:
                        msg = _("The requested operation would affect files that cannot "
                        "be modified in the Live Image.\n"
                        "Please retry this operation on an alternate boot environment.")
                        self.__g_error_stage(msg)
                        return
                except api_errors.PlanMissingException:
                        msg = _("There was an error during installation.\n"
                            "The Plan of the operation is missing and the operation "
                            "can't be finished. You might want try to fix this "
                            "problem by restarting %s\n") % self.parent_name
                        self.__g_error_stage(msg)
                        return
                except api_errors.ImageplanStateException:
                        msg = _("There was an error during installation.\n"
                            "The State of the image is incorrect and the operation "
                            "can't be finished. You might want try to fix this "
                            "problem by restarting %s\n") % self.parent_name
                        self.__g_error_stage(msg)
                        return
                except api_errors.CanceledException:
                        gobject.idle_add(self.__do_cancel)
                        self.stop_bouncing_progress()
                        return
                except api_errors.BENamingNotSupported:
                        msg = _("Specifying BE Name not supported.\n")
                        self.__g_error_stage(msg)
                        return
                # We do want to prompt user to load BE admin if there is
                # not enough disk space. This error can either come as an
                # error within API exception, see bug #7642 or as a standalone
                # error, that is why we need to check for both situations.
                except EnvironmentError, uex:
                        if uex.errno in (errno.EDQUOT, errno.ENOSPC):
                                self.__handle_nospace_error()
                        else:
                                self.__handle_error()
                        return
                except api_errors.HistoryStoreException, uex:
                        if (isinstance(uex.error, EnvironmentError) and
                           uex.error.errno in (errno.EDQUOT, errno.ENOSPC)):
                                self.__handle_nospace_error()
                        else:
                                self.__handle_error()
                        return
                except api_errors.ApiException, ex:
                        msg = str(ex)
                        self.__g_error_stage(msg)
                        return
                except Exception:
                        self.__handle_error()
                        return

        def __reset_window_title(self):
                if self.reset_window_id:
                        gobject.source_remove(self.reset_window_id)
                        self.reset_window_id = 0
                if self.w_main_window:
                        self.w_main_window.set_title(self.original_title)

        def __do_cancel(self):
                self.__do_dialog_hide()

        def __do_dialog_hide(self):
                self.w_dialog.hide()
                self.__reset_window_title()
    
        def __create_uarenamebe_o(self):
                if self.uarenamebe_o == None:
                        self.uarenamebe_o = \
                            uarenamebe.RenameBeAfterUpdateAll(
                            self.parent, self.icon_confirm_dialog,
                            self.w_main_window)

        def __handle_nospace_error(self):
                gobject.idle_add(self.__prompt_to_load_beadm)
                gobject.idle_add(self.__do_dialog_hide)
                self.stop_bouncing_progress()

        def __handle_error(self):
                traceback_lines = traceback.format_exc().splitlines()
                traceback_str = ""
                for line in traceback_lines:
                        traceback_str += line + "\n"
                self.__g_exception_stage(traceback_str)
                sys.exc_clear()

        def __proceed_with_ipkg_thread(self):
                self.__start_substage(_("Updating %s") % self.parent_name,
                    bounce_progress=True)
                self.__afterplan_information()
                self.prev_pkg = None
                self.__start_substage(_("Downloading..."), bounce_progress=False)
                self.api_o.prepare()
                self.__start_substage(_("Executing..."), bounce_progress=False)
                gobject.idle_add(self.w_cancel_button.set_sensitive, False)
                try:
                        self.api_o.execute_plan()
                except api_errors.WrapSuccessfulIndexingException:
                        pass
                except api_errors.WrapIndexingException, wex:
                        err = _("\n\nDespite the error while indexing, the "
                                    "image-update, install, or uninstall has completed "
                                    "successfuly.")
                        err = err.replace("\n\n", "")
                        err += "\n" + str(wex)
                        logger.error(err)
                        
                gobject.idle_add(self.__operations_done)

        def __proceed_with_stages_thread(self):
                self.__start_substage(None)
                self.label_text = _("Gathering package information, please wait...")
                self.update_label_text(self.label_text)
                self.update_details_text(
                    _("Gathering package information") + "\n", "level1")

                stuff_todo = self.__plan_stage()
                if stuff_todo:

                        if (self.action == enumerations.IMAGE_UPDATE and
                            self.show_confirmation):
                                gobject.idle_add(self.__show_image_update_confirmation)
                        else:
                                self.__continue_with_stages_thread()
                else:
                        if self.web_install:
                                gobject.idle_add(self.__operations_done,
                                    _("All packages already installed."))
                                return

                        if self.action == enumerations.INSTALL_UPDATE:
                                done_text = _("No updates necessary")
                        elif self.action == enumerations.IMAGE_UPDATE:
                                done_text = _("No updates available")
                        elif self.action == enumerations.UPDATE_FACETS:
                                done_text = _("All features already installed")
                        gobject.idle_add(self.__operations_done, done_text)

        def __show_image_update_confirmation(self):
                dic_to_update = {}
                dic_to_install = {}
                dic_to_remove = {}
                to_update = gtk.ListStore(str, str, str)
                to_install = gtk.ListStore(str, str, str)
                to_remove = gtk.ListStore(str, str, str)


                plan_desc = self.api_o.describe()
                if plan_desc == None:
                        return
                plan = plan_desc.get_changes()

                for pkg_plan in plan:
                        orig = pkg_plan[0]
                        dest = pkg_plan[1]
                        if orig and dest:
                                dic_to_update[dest.pkg_stem] = [dest.publisher, None] 
                        elif not orig and dest:
                                dic_to_install[dest.pkg_stem] = [dest.publisher, None] 
                        elif orig and not dest:
                                dic_to_remove[orig.pkg_stem] = [orig.publisher, None] 

                self.__update_summaries(dic_to_update, dic_to_install, dic_to_remove)

                self.__dic_to_liststore(dic_to_update, to_update)
                self.__dic_to_liststore(dic_to_install, to_install)
                self.__dic_to_liststore(dic_to_remove, to_remove)

                len_to_update = len(to_update)
                len_to_install = len(to_install)
                len_to_remove = len(to_remove)

                if len_to_update == 0 and len_to_install == 0 and len_to_remove == 0:
                        # Never show an empty confirmation dialog just proceed
                        self.__on_confirm_ok_button_clicked(None)
                        return

                self.__resize_confirm_frames(len_to_update,
                    len_to_install, len_to_remove)

                if len_to_update > 0:
                        self.__init_confirmation_tree_view(
                            self.w_update_treeview)
                        to_update.set_default_sort_func(lambda *args: -1) 
                        to_update.set_sort_column_id(0, gtk.SORT_ASCENDING)
                        self.w_update_treeview.set_model(to_update)
                        self.w_update_expander.set_expanded(True)
                else:
                        self.w_update_expander.hide()

                if len_to_install > 0:
                        self.__init_confirmation_tree_view(
                            self.w_install_treeview)
                        to_install.set_default_sort_func(lambda *args: -1) 
                        to_install.set_sort_column_id(0, gtk.SORT_ASCENDING)
                        self.w_install_treeview.set_model(to_install)
                        self.w_install_expander.set_expanded(True)
                else:
                        self.w_install_expander.hide()

                if len_to_remove > 0:
                        self.__init_confirmation_tree_view(
                            self.w_remove_treeview)
                        to_remove.set_default_sort_func(lambda *args: -1) 
                        to_remove.set_sort_column_id(0, gtk.SORT_ASCENDING)
                        self.w_remove_treeview.set_model(to_remove)
                        self.w_remove_expander.set_expanded(True)
                else:
                        self.w_remove_expander.hide()

                no_pkgs = len(to_update) + len(to_install) + len(to_remove)
                operation_txt = _("Updates Confirmation")
                install_text = ngettext(
                    "Review the package which will be affected by Updates",
                    "Review the packages which will be affected by Updates", no_pkgs)

                self.w_confirm_dialog.set_title(operation_txt)
                self.w_confirm_label.set_markup("<b>"+install_text+"</b>")

                self.w_confirm_ok_button.grab_focus()
                self.__start_substage(None,
                            bounce_progress=False)
                if self.top_level:
                        self.__reset_window_title()
                else:
                        self.w_dialog.hide()
                self.w_confirm_dialog.show()


        def __resize_confirm_frames(self, len_to_update, len_to_install, len_to_remove):
                calculated_height = DEFAULT_CONFIRMATION_HEIGHT

                if len_to_update > 0 and len_to_remove > 0 and len_to_install > 0:
                        calculated_height = (calculated_height/4)*2
                elif (len_to_update > 0 and len_to_remove > 0) or (len_to_update > 0 and
                    len_to_install > 0) or (len_to_remove > 0 and len_to_install > 0):
                        calculated_height = (calculated_height/3)*2

                self.w_install_frame.set_size_request(DEFAULT_CONFIRMATION_WIDTH,
                    calculated_height)
                self.w_update_frame.set_size_request(DEFAULT_CONFIRMATION_WIDTH,
                    calculated_height)
                self.w_remove_frame.set_size_request(DEFAULT_CONFIRMATION_WIDTH,
                    calculated_height)

        @staticmethod
        def __dic_to_liststore(dic, liststore):
                for entry in dic:
                        liststore.append([entry, dic[entry][0], dic[entry][1]])

        def __handle_licenses(self):
                self.packages_with_license = \
                    self.__get_packages_for_license_check()
                self.n_licenses = len(self.packages_with_license)
                if self.n_licenses > 0:
                        gobject.idle_add(self.__do_ask_license)
                        self.license_cv.acquire()
                        while not self.accept_license_done:
                                self.license_cv.wait()
                        gui_misc.release_lock(self.license_cv)
                        self.__do_accept_licenses()
                return

        def __continue_with_stages_thread(self):
                self.__afterplan_information()
                self.prev_pkg = None
                self.__handle_licenses()

                # The api.prepare() mostly is downloading the files so we are
                # Not showing this stage in the main stage dialog. If download
                # is necessary, then we are showing it in the details view
                if not self.action == enumerations.REMOVE:
                        self.__start_stage_two()
                        self.__start_substage(None,
                            bounce_progress=False)
                try:
                        self.api_o.prepare()
                except api_errors.PlanLicenseErrors:
                        gobject.idle_add(self.__do_dialog_hide)
                        if self.top_level:
                                gobject.idle_add(self.parent.install_terminated)
                        self.stop_bouncing_progress()
                        return
                self.__start_stage_three()
                self.__start_substage(None,
                    bounce_progress=False)
                gobject.idle_add(self.w_cancel_button.set_sensitive, False)
                try:
                        self.api_o.execute_plan()
                except api_errors.WrapSuccessfulIndexingException:
                        pass
                except api_errors.WrapIndexingException, wex:
                        err = _("\n\nDespite the error while indexing, the "
                                    "image-update, install, or uninstall has completed "
                                    "successfuly.")
                        err = err.replace("\n\n", "")
                        err += "\n" + str(wex)
                        logger.error(err)
                        
                gobject.idle_add(self.__operations_done)

        def __start_stage_one(self):
                self.__start_stage(self.stages.get(1), self.w_stage1_label,
                    self.w_stage1_icon)
                self.update_details_text(self.stages.get(1)[0]+"\n", "bold")

        def __start_stage_two(self):
                # End previous stage
                self.__end_stage()
                self.__start_stage(self.stages.get(2), self.w_stage2_label,
                    self.w_stage2_icon)
                self.update_details_text(self.stages.get(2)[0]+"\n", "bold")

        def __start_stage_three(self):
                self.__end_stage()
                self.__start_stage(self.stages.get(3),  self.w_stage3_label,
                    self.w_stage3_icon)
                self.update_details_text(self.stages.get(3)[0]+"\n", "bold")

        def __do_start_stage(self, stage_text, current_stage_label, current_stage_icon):
                self.current_stage_label = current_stage_label
                self.current_stage_icon = current_stage_icon
                self.current_stage_label_done = stage_text[1]
                if self.w_main_window:
                        new_title = stage_text[0]
                        self.w_main_window.set_title(new_title)
                self.current_stage_label.set_markup("<b>"+stage_text[0]+"</b>")
                self.current_stage_icon.set_from_stock(gtk.STOCK_GO_FORWARD,
                    gtk.ICON_SIZE_MENU)

        def __start_stage(self, stage_text, current_stage_label, current_stage_icon):
                gobject.idle_add(self.__do_start_stage, stage_text, current_stage_label,
                    current_stage_icon)

        def __do_end_stage(self):
                self.current_stage_label.set_text(self.current_stage_label_done)
                self.current_stage_icon.set_from_pixbuf(self.done_icon)
                self.__reset_window_title()

        def __end_stage(self):
                gobject.idle_add(self.__do_end_stage)

        def __g_error_stage(self, msg):
                if msg == None or len(msg) == 0:
                        msg = _("No further information available")
                self.operations_done = True
                self.operations_done_ex = True
                self.stop_bouncing_progress()
                self.update_details_text(_("\nError:\n"), "bold")
                self.update_details_text("%s" % msg, "level1")
                self.update_details_text("\n")
                txt = "<b>" + self.current_stage_label_done + _(" - Failed </b>")
                gobject.idle_add(self.__g_error_stage_setup, txt)
                gobject.idle_add(self.w_dialog.queue_draw)

        def __g_error_stage_setup(self, txt):
                self.__reset_window_title()
                if self.action == enumerations.IMAGE_UPDATE:
                        info_url = misc.get_release_notes_url()
                        if info_url and len(info_url) == 0:
                                info_url = gui_misc.RELEASE_URL
                        self.w_release_notes.show()
                        self.w_release_notes_link.set_uri(info_url)
                        self.dlg_expanded_details_h += DIALOG_RELEASE_NOTE_OFFSET * 2
                        self.dlg_install_collapsed_h += DIALOG_RELEASE_NOTE_OFFSET
                        self.dlg_remove_collapsed_h += DIALOG_RELEASE_NOTE_OFFSET

                self.current_stage_label.set_markup(txt)
                self.current_stage_icon.set_from_stock(gtk.STOCK_DIALOG_ERROR,
                    gtk.ICON_SIZE_MENU)
                self.w_expander.set_expanded(True)
                self.w_cancel_button.set_sensitive(True)
                self.__set_dialog_size(self.dlg_width, self.dlg_expanded_details_h)

        def __g_exception_stage(self, tracebk):
                self.__reset_window_title()
                self.operations_done = True
                self.operations_done_ex = True
                self.stop_bouncing_progress()
                if self.action == enumerations.IMAGE_UPDATE:
                        info_url = misc.get_release_notes_url()
                        if info_url and len(info_url) == 0:
                                info_url = gui_misc.RELEASE_URL
                        self.w_release_notes.show()
                        self.w_release_notes_link.set_uri(info_url)
                txt = "<b>" + self.current_stage_label_done + _(" - Failed </b>")
                gobject.idle_add(self.current_stage_label.set_markup, txt)
                gobject.idle_add(self.current_stage_icon.set_from_stock,
                    gtk.STOCK_DIALOG_ERROR, gtk.ICON_SIZE_MENU)
                msg_2 = misc.get_traceback_message()
                msg_2 = msg_2.replace("\n", " ").lstrip()
                msg_1 = _("An unknown error occurred in the %s stage.\n\n")\
                    % self.current_stage_name + msg_2
                self.update_details_text(_("\nError:\n"), "bold")
                self.update_details_text("%s\n\n" % msg_1, "level1")
                if tracebk:
                        msg = _("Exception traceback:\n")
                        self.update_details_text("%s" % msg,
                            "bold","level1")
                        self.update_details_text("%s\n" % tracebk, "level2")
                else:
                        msg = _("No further information available")
                        self.update_details_text("%s\n" % msg, "level2")
                publisher_header = _("List of configured publishers:")
                self.update_details_text("%s" % publisher_header,
                    "bold","level1")
                publisher_str = gui_misc.get_publishers_for_output(self.api_o)
                self.update_details_text("%s\n" % publisher_str,
                    "level2")
                gobject.idle_add(self.w_expander.set_expanded, True)
                gobject.idle_add(self.w_cancel_button.set_sensitive, True)

        def __start_substage(self, text, bounce_progress=True):
                if text:
                        self.update_label_text(text)
                        self.update_details_text(text + "\n", "level1")
                if bounce_progress:
                        if self.stopped_bouncing_progress:
                                self.start_bouncing_progress()
                else:
                        self.stop_bouncing_progress()

        def update_label_text(self, markup_text):
                gobject.idle_add(self.__stages_label_set_markup, markup_text)

        def __stages_label_set_markup(self, markup_text):
                if not self.canceling == True:
                        self.w_stages_label.set_markup(markup_text)

        def start_bouncing_progress(self):
                self.stop_progress_bouncing = False
                self.stopped_bouncing_progress = False
                Thread(target =
                    self.__g_progressdialog_progress_pulse).start()

        def __g_progressdialog_progress_pulse(self):
                while not self.stop_progress_bouncing:
                        gobject.idle_add(self.w_progressbar.pulse)
                        time.sleep(0.1)
                self.stopped_bouncing_progress = True
                gobject.idle_add(self.w_progressbar.set_fraction, 0.0)

        def is_progress_bouncing(self):
                return not self.stopped_bouncing_progress

        def stop_bouncing_progress(self):
                if self.is_progress_bouncing():
                        self.stop_progress_bouncing = True

        def update_details_text(self, text, *tags):
                gobject.idle_add(self.__update_details_text, text, *tags)

        def __update_details_text(self, text, *tags):
                buf = self.w_details_textview.get_buffer()
                textiter = buf.get_end_iter()
                if tags:
                        buf.insert_with_tags_by_name(textiter, text, *tags)
                else:
                        buf.insert(textiter, text)
                insert_mark = buf.get_insert()
                self.w_details_textview.scroll_to_mark(insert_mark, 0.0)

        def __update_window_title(self, display_string):
                self.w_main_window.set_title(display_string)

        def display_download_info(self):
                self.update_progress(self.dl_bytes.items,
                    self.dl_bytes.goalitems)
                if self.w_main_window:
                        progtimes100 = int(self.prog * 100)
                        if progtimes100 != self.prev_prog:
                                self.prev_prog = progtimes100
                                display_string = "%d%% - %s" % (progtimes100,
                                    self.stages[2][0])
                                gobject.idle_add(self.__update_window_title,
                                    display_string)

                if self.display_download_id == 0:
                        self.display_download_id = gobject.timeout_add( \
                            DISPLAY_DELAY, self.__display_download_text)

        def __display_download_text(self):
                self.display_download_id = 0
                size_a_str = misc.bytes_to_str(self.dl_bytes.items)
                size_b_str = misc.bytes_to_str(self.dl_bytes.goalitems)
                speed = self.dl_estimator.get_speed_estimate()
                speed_str = "" if speed is None else \
                    _("(%s)") % self.dl_estimator.format_speed(speed)

                c = _("Downloaded %(current)s of %(total)s %(speed)s") % \
                    {"current" : size_a_str,
                    "total" : size_b_str,
                    "speed" : speed_str}
                self.__stages_label_set_markup(c)

        def display_phase_info(self, phase_name, cur_n, goal_n):
                self.update_progress(cur_n, goal_n)
                if self.reset_window_id != 0:
                        gobject.source_remove(self.reset_window_id)
                        self.reset_window_id = 0
                if self.w_main_window:
                        progtimes100 = int(self.prog * 100)
                        if progtimes100 != self.prev_prog:
                                self.prev_prog = progtimes100
                                display_string = _("%(cur)d of %(goal)d - %(name)s") % \
                                    {"cur": cur_n, "goal": goal_n, \
                                    "name": phase_name}
                                gobject.idle_add(self.__update_window_title,
                                    display_string)
                                self.reset_window_id = gobject.timeout_add(
                                        RESET_PACKAGE_DELAY,
                                        self.__do_reset_window_text, phase_name)

        def __do_reset_window_text(self, phase_name):
                self.reset_window_id = 0
                self.__update_window_title(phase_name)

        def reset_label_text_after_delay(self):
                if self.reset_id != 0:
                        gobject.source_remove(self.reset_id)
                self.reset_id = gobject.timeout_add(RESET_PACKAGE_DELAY,
                    self.__do_reset_label_text)

        def __do_reset_label_text(self):
                self.reset_id = 0
                if self.label_text:
                        self.__stages_label_set_markup(self.label_text)

        def __update_progress(self):
                self.update_progress_id = 0
                self.w_progressbar.set_fraction(self.prog)

        def update_progress(self, current, total):
                self.prog = float(current)/total
                assert self.prog >= 0.0 and self.prog <= 1.0
                if self.update_progress_id == 0:
                        self.update_progress_id = gobject.timeout_add(DISPLAY_DELAY,
                            self.__update_progress)

        def __plan_stage(self):
                '''Function which plans the image'''
                if self.action == enumerations.INSTALL_UPDATE:
                        for pd in self.api_o.gen_plan_install(
                            self.list_of_packages, refresh_catalogs=False):
                                continue
                elif self.action == enumerations.REMOVE:
                        for pd in self.api_o.gen_plan_uninstall(
                            self.list_of_packages, noexecute=False):
                                continue
                elif self.action == enumerations.IMAGE_UPDATE:
                        # we are passing force, since we already checked if the
                        # packages are up to date.  Create BE if required
                        for pd in self.api_o.gen_plan_update(
                            refresh_catalogs=False, noexecute=False,
                            force=True, be_name=None, new_be=None):
                                continue
                        self.pylint_stub = self.api_o.solaris_image()
                else:
                        assert self.action == enumerations.UPDATE_FACETS
                        for pd in self.api_o.gen_plan_change_varcets(
                            variants=None, facets=self.facets,
                            noexecute=False, be_name=None, new_be=None):
                                continue
                return not self.api_o.planned_nothingtodo(li_ignore_all=True)

        def __operations_done(self, alternate_done_txt = None):
                self.__reset_window_title()
                self.label_text = None
                done_txt = _("Installation completed successfully")
                if self.action == enumerations.REMOVE:
                        done_txt = _("Packages removed successfully")
                elif self.action == enumerations.IMAGE_UPDATE:
                        done_txt = _("Packages updated successfully")
                elif self.action == enumerations.UPDATE_FACETS:
                        done_txt = _("Optional components updated successfully")
                if alternate_done_txt != None:
                        done_txt = alternate_done_txt
                self.w_stages_box.hide()
                self.w_stages_icon.show()
                self.__stages_label_set_markup("<b>" + done_txt + "</b>")
                self.__update_details_text("\n"+ done_txt, "bold")
                self.w_cancel_button.set_sensitive(True)
                self.w_cancel_button.set_label("gtk-close")
                self.w_cancel_button.grab_focus()
                self.w_progressbar.hide()
                self.stop_bouncing_progress()
                self.operations_done = True
                if not self.gconf.details_expanded:
                        self.__set_dialog_size(self.dlg_width, self.dlg_done_collapsed_h)
                if self.parent != None:
                        if not self.web_install and not self.ips_update \
                            and not self.action == enumerations.IMAGE_UPDATE \
                            and not self.action == enumerations.UPDATE_FACETS:
                                self.parent.update_package_list(self.update_list)
                        if self.web_install:
                                if done_txt == \
                                        _("All packages already installed.") or \
                                        done_txt == \
                                        _("Installation completed successfully"):
                                        self.web_install_all_installed = True
                                else:
                                        self.web_install_all_installed = False
                                self.web_updates_list = self.update_list
                if self.ips_update:
                        self.w_dialog.hide()
                        self.parent.restart_after_ips_update()
                elif self.action == enumerations.IMAGE_UPDATE or \
                        self.action == enumerations.UPDATE_FACETS:
                        if self.uarenamebe_o:
                                be_rename_dialog = \
                                    self.uarenamebe_o.show_rename_dialog(
                                    self.update_list)
                                if be_rename_dialog == True and not self.top_level:
                                        self.w_dialog.hide()

        def __prompt_to_load_beadm(self):
                msgbox = gtk.MessageDialog(parent = self.w_main_window,
                    buttons = gtk.BUTTONS_OK_CANCEL, flags = gtk.DIALOG_MODAL,
                    type = gtk.MESSAGE_ERROR,
                    message_format = _(
                        "Not enough disk space, the selected action cannot "
                        "be performed.\n\n"
                        "Click OK to manage your existing BEs and free up disk space or "
                        "Cancel to cancel the action."))
                msgbox.set_title(_("Not Enough Disk Space"))
                result = msgbox.run()
                msgbox.destroy()
                if result == gtk.RESPONSE_OK:
                        beadm.Beadmin(self.parent)

        def __afterplan_information(self):
                install_iter = None
                update_iter = None
                remove_iter = None
                plan_desc = self.api_o.describe()
                if plan_desc == None:
                        return
                self.reboot_needed = plan_desc.reboot_needed
                plan = plan_desc.get_changes()
                self.update_details_text("\n")
                for pkg_plan in plan:
                        origin_fmri = pkg_plan[0]
                        destination_fmri = pkg_plan[1]
                        if origin_fmri and destination_fmri:
                                if not update_iter:
                                        update_iter = True
                                        txt = _("Packages To Be Updated:\n")
                                        self.update_details_text(txt, "bold")
                                pkg_a = self.__get_pkgstr_from_pkginfo(destination_fmri)
                                self.update_details_text(pkg_a+"\n", "level1")
                        elif not origin_fmri and destination_fmri:
                                if not install_iter:
                                        install_iter = True
                                        txt = _("Packages To Be Installed:\n")
                                        self.update_details_text(txt, "bold")
                                pkg_a = self.__get_pkgstr_from_pkginfo(destination_fmri)
                                self.update_details_text(pkg_a+"\n", "level1")
                        elif origin_fmri and not destination_fmri:
                                if not remove_iter:
                                        remove_iter = True
                                        txt = _("Packages To Be Removed:\n")
                                        self.update_details_text(txt, "bold")
                                pkg_a = self.__get_pkgstr_from_pkginfo(origin_fmri)
                                self.update_details_text(pkg_a+"\n", "level1")

                v = plan_desc.get_varcets()
                if v == None or len(v) == 0:
                        self.update_details_text("\n")
                        return
                txt = _("Optional components\n")
                self.update_details_text(txt, "bold")
                txt = _("Number of facets set: %s\n" % (len(v)))
                self.update_details_text(txt, "level1")
                for x in v:
                        self.update_details_text("%s\n" % x, "level1")
                self.update_details_text("\n")

        def __get_pkgstr_from_pkginfo(self, pkginfo):
                dt_str = self.get_datetime(pkginfo.packaging_date)
                if not dt_str:
                        dt_str = ""
                s_ver = pkginfo.version
                s_bran = pkginfo.branch
                pkg_name = pkginfo.pkg_stem
                pkg_publisher = pkginfo.publisher
                if not pkg_publisher in self.update_list:
                        self.update_list[pkg_publisher] = []
                pub_list = self.update_list.get(pkg_publisher)
                if not pkg_name in pub_list:
                        pub_list.append(pkg_name)
                l_ver = 0
                version_pref = ""
                while l_ver < len(s_ver) -1:
                        version_pref += "%d%s" % (s_ver[l_ver],".")
                        l_ver += 1
                version_pref += "%d%s" % (s_ver[l_ver],"-")
                l_ver = 0
                version_suf = ""
                if s_bran != None:
                        while l_ver < len(s_bran) -1:
                                version_suf += "%d%s" % (s_bran[l_ver],".")
                                l_ver += 1
                        version_suf += "%d" % s_bran[l_ver]
                pkg_version = version_pref + version_suf + dt_str
                return pkg_name + "@" + pkg_version

        def __update_summaries(self, to_update, to_install, to_remove):
                pkgs_table = to_update.keys() + to_install.keys()
                info = None
                try:
                        info = self.api_o.info(pkgs_table, False,
                            frozenset([api.PackageInfo.SUMMARY,
                            api.PackageInfo.IDENTITY]))
                        info_r = self.api_o.info(to_remove.keys(), True,
                            frozenset([api.PackageInfo.SUMMARY,
                            api.PackageInfo.IDENTITY]))
                        for info_s in (info.get(0) + info_r.get(0)):
                                stem = info_s.pkg_stem
                                if stem in to_update:
                                        to_update[stem][1] = info_s.summary
                                elif stem in to_install:
                                        to_install[stem][1] = info_s.summary
                                elif stem in to_remove:
                                        to_remove[stem][1] = info_s.summary
                except api_errors.ApiException, ex:
                        err = str(ex)
                        logger.error(err)
                        gui_misc.notify_log_error(self.parent)

        @staticmethod
        def get_datetime(date_time):
                '''Support function for getting date from the API.'''
                date_tmp = None
                try:
                        date_tmp = time.strptime(date_time, "%a %b %d %H:%M:%S %Y")
                except ValueError:
                        return None
                if date_tmp:
                        date_tmp2 = datetime.datetime(*date_tmp[0:5])
                        return date_tmp2.strftime(":%m%d")
                return None

        def __installed_fmris_from_args(self, args_f):
                not_found = False
                try:
                        res = self.api_o.info(args_f, True,
                            frozenset([api.PackageInfo.STATE]))
                        if not res or len(res[0]) != len(args_f):
                                not_found = True 
                except api_errors.ApiException:
                        not_found = True
                return not_found

        def __do_ask_license(self):
                item = self.packages_with_license[self.current_license_no]
                pfmri = item[0]
                dest = item[2]
                pkg_name = pfmri.get_name()
                lic = dest.get_text()
                if dest.must_accept:
                        gui_misc.change_stockbutton_label(self.w_license_accept_button,
                            _("A_ccept"))
                        self.w_license_label.set_text(
                            _("You must accept the terms of the license before "
                            "downloading this package."))
                        self.w_license_accept_checkbutton.show()
                        self.w_license_reject_button.show()
                        self.w_license_accept_checkbutton.grab_focus()
                        self.w_license_accept_checkbutton.set_active(False)
                        self.w_license_accept_button.set_sensitive(False)
                else:
                        if self.accept_text != None:
                                gui_misc.change_stockbutton_label(
                                    self.w_license_accept_button,
                                     self.accept_text)
                        self.w_license_label.set_text(
                            _("You must view the terms of the license before "
                            "downloading this package."))
                        self.w_license_accept_checkbutton.hide()
                        self.w_license_reject_button.hide()
                        self.w_license_accept_button.set_sensitive(True)
                        self.w_license_accept_button.grab_focus()
                lic_buffer = self.w_license_text.get_buffer()
                lic_buffer.set_text(lic)
                title = _("%s License") % pkg_name
                self.w_license_dialog.set_title(title)
                self.w_license_dialog.show()
                return

        def __do_accept_licenses(self):
                for item, accepted_value in self.packages_with_license_result:
                        pfmri = item[0]
                        dest = item[2]
                        lic = dest.license
                        self.api_o.set_plan_license_status(pfmri, lic, 
                            displayed=True, accepted=accepted_value)

        def __get_packages_for_license_check(self):
                pkg_list = []
                plan = self.api_o.describe()
                for item in plan.get_licenses():
                        dest = item[2]
                        if dest.must_display or dest.must_accept:
                                pkg_list.append(item)
                return pkg_list

        def __on_license_reject_button_clicked(self, widget):
                self.packages_with_license_result.append(
                    (self.packages_with_license[self.current_license_no],
                    False))
                self.w_license_dialog.hide()
                self.license_cv.acquire()
                self.accept_license_done = True
                self.license_cv.notify()
                gui_misc.release_lock(self.license_cv)

        def __on_license_accept_button_clicked(self, widget):
                result = None
                item = self.packages_with_license[self.current_license_no]
                dest = item[2]
                if dest.must_accept:
                        result = True
                self.packages_with_license_result.append(
                    (item, result))
                self.w_license_dialog.hide()
                self.current_license_no += 1
                if self.current_license_no < self.n_licenses:
                        gobject.idle_add(self.__do_ask_license)
                else:
                        self.license_cv.acquire()
                        self.accept_license_done = True
                        self.license_cv.notify()
                        gui_misc.release_lock(self.license_cv)

        def __on_license_dialog_delete(self, widget, event):
                if self.w_license_reject_button.get_property('visible'):
                        self.__on_license_reject_button_clicked(None)
                else:
                        self.__on_license_accept_button_clicked(None)
                return True

        def __on_license_accept_checkbutton_toggled(self, widget):
                ret = self.w_license_accept_checkbutton.get_active()
                self.w_license_accept_button.set_sensitive(ret)
