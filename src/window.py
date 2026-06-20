import json
import os

from gi.repository import Adw, Gtk, Gdk, GLib, Gio
from PIL import Image, ImageFilter
from .input_lock import grab_all, ungrab_all


CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "keyboard-cleaner")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
BLURRED_BACKGROUND_PATH = os.path.join(CONFIG_DIR, "blurred-background.png")


@Gtk.Template(resource_path="/naplon_/keyboard/cleaner/window.ui")
class KeyboardCleanerWindow(Adw.ApplicationWindow):
    __gtype_name__ = "KeyboardCleanerWindow"

    background_picture = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    debug_label = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.locked_devices = []
        self.unlock_timer_id = None
        self.settings_dialog = None

        self.config = self.load_config()
        self.apply_config()

        self.connect("close-request", self.on_close_request)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        key_controller.connect("key-released", self.on_key_released)
        self.add_controller(key_controller)

        self.fullscreen()

        if not self.config["debug"]:
            try:
                self.locked_devices = grab_all()
            except Exception as error:
                print(f"Could not lock input devices: {error}")

    def load_config(self):
        default_config = {
            "debug": True,
            "background": "",
            "blur": False,
        }

        os.makedirs(CONFIG_DIR, exist_ok=True)

        if not os.path.exists(CONFIG_PATH):
            self.save_config(default_config)
            return default_config

        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as file:
                config = json.load(file)

            return {**default_config, **config}

        except Exception as error:
            print(f"Could not read config: {error}")
            return default_config

    def save_config(self, config=None):
        if config is None:
            config = self.config

        os.makedirs(CONFIG_DIR, exist_ok=True)

        with open(CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=4)

    def apply_config(self):
        self.debug_label.set_visible(self.config["debug"])

        background = self.config["background"]

        if not background or not os.path.exists(background):
            self.background_picture.set_visible(False)
            return

        if self.config["blur"]:
            blurred_path = self.create_blurred_background(background)

            if blurred_path:
                self.background_picture.set_filename(blurred_path)
            else:
                self.background_picture.set_filename(background)
        else:
            self.background_picture.set_filename(background)

        self.background_picture.set_visible(True)

    def create_blurred_background(self, path):
        try:
            image = Image.open(path).convert("RGB")

            blurred = image.filter(ImageFilter.GaussianBlur(radius=24))
            blurred.save(BLURRED_BACKGROUND_PATH, "PNG")

            return BLURRED_BACKGROUND_PATH

        except Exception as error:
            print(f"Could not blur background: {error}")
            return None

    def on_close_request(self, window):
        if self.config["debug"]:
            return False

        return True

    def on_key_pressed(self, controller, keyval, keycode, state):
        key_name = Gdk.keyval_name(keyval)

        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(state & Gdk.ModifierType.ALT_MASK)

        if ctrl and alt and key_name in ("s", "S"):
            self.open_settings()
            return True

        if ctrl and alt and key_name in ("u", "U") and self.unlock_timer_id is None:
            self.status_label.set_label("Keep holding...")
            self.unlock_timer_id = GLib.timeout_add_seconds(3, self.unlock)
            return True

        return True

    def on_key_released(self, controller, keyval, keycode, state):
        if self.unlock_timer_id is not None:
            GLib.source_remove(self.unlock_timer_id)
            self.unlock_timer_id = None
            self.status_label.set_label("Hold Ctrl + Alt + U for 3 seconds to unlock")

        return True

    def unlock(self):
        if self.locked_devices:
            ungrab_all(self.locked_devices)

        self.destroy()
        return False

    def open_settings(self):
        if self.settings_dialog:
            self.settings_dialog.present()
            return

        dialog = Adw.PreferencesWindow()
        dialog.set_title("Keyboard Cleaner Settings")
        dialog.set_modal(True)
        dialog.set_transient_for(self)
        dialog.connect("close-request", self.on_settings_closed)

        settings_page = Adw.PreferencesPage()
        settings_page.set_title("Settings")
        settings_page.set_icon_name("preferences-system-symbolic")

        settings_group = Adw.PreferencesGroup(title="Appearance and Behavior")

        debug_row = Adw.SwitchRow(
            title="Debug mode",
            subtitle="Disable input locking and allow closing the app with Alt+F4"
        )
        debug_row.set_active(self.config["debug"])
        debug_row.connect("notify::active", self.on_debug_changed)

        blur_row = Adw.SwitchRow(
            title="Blur background",
            subtitle="Blur the selected background image"
        )
        blur_row.set_active(self.config["blur"])
        blur_row.connect("notify::active", self.on_blur_changed)

        background_row = Adw.ActionRow(
            title="Background image",
            subtitle=self.config["background"] or "No image selected"
        )

        choose_button = Gtk.Button(label="Choose")
        choose_button.connect("clicked", self.choose_background, background_row)
        background_row.add_suffix(choose_button)

        clear_button = Gtk.Button(label="Clear")
        clear_button.connect("clicked", self.clear_background, background_row)
        background_row.add_suffix(clear_button)

        settings_group.add(debug_row)
        settings_group.add(blur_row)
        settings_group.add(background_row)
        settings_page.add(settings_group)

        about_page = Adw.PreferencesPage()
        about_page.set_title("About")
        about_page.set_icon_name("help-about-symbolic")

        about_group = Adw.PreferencesGroup(title="Application Info")

        about_group.add(Adw.ActionRow(
            title="Keyboard Cleaner",
            subtitle="A GNOME app to lock input while cleaning your keyboard and mouse"
        ))

        about_group.add(Adw.ActionRow(
            title="Version",
            subtitle="1.1"
        ))

        about_group.add(Adw.ActionRow(
            title="License",
            subtitle="MIT License"
        ))

        github_row = Adw.ActionRow(
            title="GitHub",
            subtitle="Project/source page"
        )
        github_button = Gtk.LinkButton(
            uri="https://github.com/naplon74/keyboard-cleaner",
            label="Open"
        )
        github_row.add_suffix(github_button)
        github_row.set_activatable_widget(github_button)

        website_row = Adw.ActionRow(
            title="Website",
            subtitle="naplon.xyz"
        )
        website_button = Gtk.LinkButton(
            uri="https://naplon.xyz",
            label="Open"
        )
        website_row.add_suffix(website_button)
        website_row.set_activatable_widget(website_button)

        about_group.add(github_row)
        about_group.add(website_row)
        about_page.add(about_group)

        dialog.add(settings_page)
        dialog.add(about_page)

        self.settings_dialog = dialog
        dialog.present()

    def on_settings_closed(self, dialog):
        self.settings_dialog = None
        return False

    def on_debug_changed(self, row, _):
        self.config["debug"] = row.get_active()
        self.save_config()
        self.apply_config()

    def on_blur_changed(self, row, _):
        self.config["blur"] = row.get_active()
        self.save_config()
        self.apply_config()

    def choose_background(self, button, background_row):
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose Background Image")

        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images")
        image_filter.add_mime_type("image/png")
        image_filter.add_mime_type("image/jpeg")
        image_filter.add_mime_type("image/webp")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)

        dialog.set_filters(filters)
        dialog.open(self, None, self.on_background_chosen, background_row)

    def on_background_chosen(self, dialog, result, background_row):
        try:
            file = dialog.open_finish(result)
            path = file.get_path()

            if path:
                self.config["background"] = path
                self.save_config()
                self.apply_config()
                background_row.set_subtitle(path)

        except Exception:
            pass

    def clear_background(self, button, background_row):
        self.config["background"] = ""
        self.save_config()
        self.apply_config()
        background_row.set_subtitle("No image selected")
