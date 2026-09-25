"""Application shell.

A ``FluentWindow`` providing the navigation rail, mica background and title bar.
It deliberately holds no conversion logic — that lives in the interfaces it
hosts. The old 993-line ``QMainWindow`` mixed shell, queue, options translation
and conversion orchestration into one class.
"""

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from qfluentwidgets import (
    FluentIcon, FluentWindow, InfoBar, InfoBarPosition, MessageBox,
    NavigationAvatarWidget, NavigationItemPosition, SystemThemeListener, Theme,
    isDarkTheme, setTheme, setThemeColor, toggleTheme,
)

import lang
from logger import logger
from ui.interfaces.convert_interface import ConvertInterface
from ui.interfaces.formats_interface import FormatsInterface
from ui.interfaces.settings_interface import SettingsInterface
from utils.paths import RESOURCES

APP_VERSION = "0.2.0"
ACCENT_DEFAULT = "#4f7cff"


def apply_appearance(settings: QSettings) -> None:
    """Apply the stored theme and accent colour process-wide."""
    mode = settings.value("theme_mode", "", type=str)
    if not mode:
        mode = "dark" if settings.value("dark_mode", False, type=bool) else "auto"

    setTheme({"dark": Theme.DARK, "light": Theme.LIGHT}.get(mode, Theme.AUTO))
    accent = settings.value("accent_color", ACCENT_DEFAULT, type=str) or ACCENT_DEFAULT
    setThemeColor(accent)


class MainWindow(FluentWindow):
    """Hosts the Convert, Formats and Settings interfaces."""

    def __init__(self):
        super().__init__()
        self.settings = QSettings("EverythingConverter", "Settings")
        self.tray_icon = None
        self._theme_listener = None

        self._build_interfaces()
        self._build_navigation()
        self._configure_window()
        self._setup_tray()
        self._start_theme_listener()

    # ---------------------------------------------------------- composition --
    def _build_interfaces(self):
        self.convert_interface = ConvertInterface(self)
        self.formats_interface = FormatsInterface(self)
        self.settings_interface = SettingsInterface(self)

        self.settings_interface.language_changed.connect(self._on_language_changed)
        self.settings_interface.appearance_changed.connect(self._on_appearance_changed)
        # Settings persist live (no OK button); the queue reacts immediately.
        self.settings_interface.settingsChanged.connect(
            self.convert_interface.on_settings_changed)
        self.convert_interface.busy_changed.connect(self._on_busy_changed)

    def _build_navigation(self):
        self.addSubInterface(self.convert_interface, FluentIcon.SYNC,
                             lang.lang.get("Convert"))
        self.addSubInterface(self.formats_interface, FluentIcon.TILES,
                             lang.lang.get("Formats"))
        self.addSubInterface(self.settings_interface, FluentIcon.SETTING,
                             lang.lang.get("Settings"),
                             position=NavigationItemPosition.BOTTOM)

        self.navigationInterface.addItem(
            routeKey="themeToggle",
            icon=FluentIcon.CONSTRACT,
            text=lang.lang.get("Switch theme"),
            onClick=self._toggle_theme,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

    def _configure_window(self):
        self.setWindowTitle(f"{lang.lang.get('EverythingConverter')}")

        icon_path = RESOURCES / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Mica needs a translucent window; it is a no-op before Windows 11.
        self.setMicaEffectEnabled(self.settings.value("mica_enabled", True, type=bool))

        geometry = self.settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1180, 780)
        self.setMinimumSize(940, 600)

    # ------------------------------------------------------------ appearance --
    def _start_theme_listener(self):
        """Follow Windows light/dark changes while in Auto mode."""
        try:
            self._theme_listener = SystemThemeListener(self)
            self._theme_listener.systemThemeChanged.connect(self._on_system_theme_changed)
            self._theme_listener.start()
        except Exception as exc:
            logger.debug("System theme listener unavailable: %s", exc)

    def _on_system_theme_changed(self):
        mode = self.settings.value("theme_mode", "auto", type=str)
        if mode not in ("", "auto"):
            return
        # Give qfluentwidgets a beat to recolour before we repaint.
        QTimer.singleShot(80, self._repaint_after_theme)

    def _on_appearance_changed(self):
        apply_appearance(self.settings)
        self.setMicaEffectEnabled(self.settings.value("mica_enabled", True, type=bool))
        self._repaint_after_theme()

    def _toggle_theme(self):
        toggleTheme(lazy=True)
        # Persist the explicit choice so it survives a restart.
        mode = "dark" if isDarkTheme() else "light"
        self.settings.setValue("theme_mode", mode)
        self.settings.setValue("dark_mode", mode == "dark")
        self.settings_interface._load()
        self._repaint_after_theme()

    def _repaint_after_theme(self):
        for widget in (self.convert_interface, self.formats_interface,
                       self.settings_interface):
            widget.update()

    # ------------------------------------------------------------------ i18n --
    def _on_language_changed(self, code):
        lang.lang.load_language(code)
        self.retranslate_ui()
        InfoBar.success(
            title=lang.lang.get("Language updated"),
            content=lang.lang.get("The interface has been translated."),
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=2500, parent=self,
        )

    def retranslate_ui(self):
        self.setWindowTitle(lang.lang.get("EverythingConverter"))

        self.convert_interface.retranslate()
        self.formats_interface.retranslate()
        self.settings_interface.retranslate()

        # Navigation labels are keyed by the interface object name.
        for interface, text in (
            (self.convert_interface, "Convert"),
            (self.formats_interface, "Formats"),
            (self.settings_interface, "Settings"),
        ):
            widget = self.navigationInterface.widget(interface.objectName())
            if widget is not None:
                widget.setText(lang.lang.get(text))

        toggle = self.navigationInterface.widget("themeToggle")
        if toggle is not None:
            toggle.setText(lang.lang.get("Switch theme"))

    # ------------------------------------------------------------------ tray --
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = RESOURCES / "icon.ico"
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        self.tray_icon.setToolTip(lang.lang.get("EverythingConverter"))
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.setVisible(True)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def notify(self, title, message):
        """Desktop notification, used when a batch finishes in the background."""
        if self.tray_icon is not None:
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 5000)

    def _on_busy_changed(self, busy):
        if not busy and not self.isActiveWindow():
            self.notify(lang.lang.get("EverythingConverter"),
                        lang.lang.get("Your conversions have finished."))

    # ----------------------------------------------------------- life cycle --
    def closeEvent(self, event):
        # A running batch has live ffmpeg processes; confirm before killing them.
        if self.convert_interface.is_busy:
            box = MessageBox(
                lang.lang.get("Conversions are still running"),
                lang.lang.get("Closing now will cancel them. Quit anyway?"),
                self,
            )
            box.yesButton.setText(lang.lang.get("Quit"))
            box.cancelButton.setText(lang.lang.get("Stay"))
            if not box.exec():
                event.ignore()
                return

        self.settings.setValue("window_geometry", self.saveGeometry())

        if self._theme_listener is not None:
            self._theme_listener.terminate()
            self._theme_listener.deleteLater()
        self.convert_interface.shutdown()

        super().closeEvent(event)
