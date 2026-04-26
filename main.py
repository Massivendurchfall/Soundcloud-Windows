from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSystemTrayIcon, QMenu,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QWidget
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage,
    QWebEngineUrlRequestInterceptor, QWebEngineScript
)
from PyQt6.QtCore import QUrl, QTimer, Qt
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
import sys
import os
import time
import threading
import json
import winreg

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-blink-features=AutomationControlled "
    "--no-sandbox"
)

DATA_DIR      = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "SoundCloudApp")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
os.makedirs(DATA_DIR, exist_ok=True)

AUTOSTART_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "SoundCloudApp"

AD_DOMAINS = [
    "promoted.soundcloud.com", "moatads.com", "2mdn.net", "doubleclick.net",
    "googleadservices.com", "googlesyndication.com", "adnxs.com", "adsrvr.org",
    "advertising.com", "ads.soundcloud.com", "scorecardresearch.com",
    "quantserve.com", "chartbeat.com", "hotjar.com", "fullstory.com",
    "ams.creativecdn.com", "pagead2.googlesyndication.com",
    "tpc.googlesyndication.com", "securepubads.g.doubleclick.net",
    "static.ads-twitter.com", "connect.facebook.net", "bat.bing.com",
    "cdn.branch.io", "impression.appsflyer.com",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Injiziert bei DocumentCreation — bevor SoundCloud irgendein JS ausführt
STEALTH_EARLY = """
(function() {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['de-DE', 'de', 'en-US', 'en']});
    Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});

    window.chrome = {
        runtime: {
            id: undefined,
            connect: function() {},
            sendMessage: function() {},
        },
        loadTimes: function() {},
        csi: function() {},
        app: {},
    };

    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : origQuery(parameters)
    );
})();
"""

AD_HIDE_CSS = """
(function injectAdHider() {
    const style = document.createElement('style');
    style.id = 'sc-ad-hider';
    style.textContent = `
        .promotedTrack, [class*="promoted"], [class*="Promoted"],
        [class*="advertisement"], [class*="Advertisement"],
        [class*="adBanner"], [class*="AdBanner"], [class*="adSlot"],
        [class*="adContainer"], [class*="ad-container"], [class*="ad-banner"],
        [class*="adWrapper"], .upsellBanner, [class*="upsell"], [class*="Upsell"],
        [class*="upgradeButton"], [class*="listenWithPremium"],
        .rightSidebar__adSlot, .adSlot, [class*="adSlot"], [class*="AdSlot"],
        [aria-label="Advertisement"], [data-testid*="ad"], [data-testid*="Ad"],
        [data-testid*="promoted"], [data-testid*="Promoted"],
        .adBanner__container, .adBanner, .listenWithGo,
        [class*="listenWithGo"], [class*="goPromo"], [class*="GoPromo"],
        [class*="subscribeButton"], [class*="SubscribeButton"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
            height: 0 !important;
            overflow: hidden !important;
        }
    `;
    if (!document.getElementById('sc-ad-hider')) {
        document.head.appendChild(style);
    }
    function removeAdNodes() {
        const selectors = [
            '[class*="promoted"]', '[class*="Promoted"]', '[class*="advertisement"]',
            '[class*="upsell"]', '[class*="Upsell"]', '[class*="adSlot"]',
            '[class*="adBanner"]', '[class*="listenWithGo"]', '[class*="goPromo"]',
            '[aria-label="Advertisement"]', '[data-testid*="ad"]', '[data-testid*="promoted"]',
        ];
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                if (!el.closest('.playControls') && !el.closest('nav')) {
                    el.style.display = 'none';
                }
            });
        });
    }
    removeAdNodes();
    const observer = new MutationObserver(() => removeAdNodes());
    observer.observe(document.body, { childList: true, subtree: true });
})();
"""

LIKE_THROTTLE_JS = """
(function() {
    const MIN_DELAY_MS = 1500;
    const MAX_DELAY_MS = 4000;
    let lastLike = 0;

    function randomDelay() {
        return Math.floor(Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS + 1)) + MIN_DELAY_MS;
    }

    function isLikeButton(el) {
        if (!el) return false;
        const cls = el.className || '';
        const label = el.getAttribute('aria-label') || '';
        const title = el.getAttribute('title') || '';
        return (
            cls.includes('like') || cls.includes('Like') ||
            cls.includes('heart') || cls.includes('Heart') ||
            label.toLowerCase().includes('like') ||
            title.toLowerCase().includes('like')
        );
    }

    document.addEventListener('click', function(e) {
        let el = e.target;
        for (let i = 0; i < 4; i++) {
            if (isLikeButton(el)) {
                const now = Date.now();
                const elapsed = now - lastLike;
                const delay = randomDelay();
                if (elapsed < MIN_DELAY_MS) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    const target = el;
                    setTimeout(() => { lastLike = Date.now(); target.click(); }, delay - elapsed);
                    return;
                }
                lastLike = now;
                break;
            }
            if (!el.parentElement) break;
            el = el.parentElement;
        }
    }, true);
})();
"""


class AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl().host()
        for domain in AD_DOMAINS:
            if domain in url:
                info.block(True)
                return


def load_settings():
    defaults = {"discord_id": "", "autostart": False, "discord_enabled": True}
    try:
        with open(SETTINGS_FILE, "r") as f:
            return {**defaults, **json.load(f)}
    except Exception:
        return defaults


def save_settings(s: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)


def set_autostart(enabled: bool):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, f'"{exe}"')
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Autostart error: {e}")


try:
    from pypresence import Presence
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False


class DiscordPresence:
    def __init__(self, client_id: str):
        self.rpc        = None
        self.connected  = False
        self.client_id  = client_id
        self.current    = ""
        self.start_time = int(time.time())
        self._lock      = threading.Lock()
        if client_id and DISCORD_AVAILABLE:
            threading.Thread(target=self._connect, daemon=True).start()

    def _connect(self):
        try:
            self.rpc = Presence(self.client_id)
            self.rpc.connect()
            self.connected = True
            self._push("Browsing SoundCloud", "")
        except Exception:
            self.connected = False

    def _push(self, state, details):
        if not self.connected or not self.rpc:
            return
        try:
            self.rpc.update(
                state=state, details=details or None, start=self.start_time,
                large_image="soundcloud", large_text="SoundCloud",
            )
        except Exception:
            self.connected = False

    def set_track(self, title: str, enabled: bool = True):
        if not enabled:
            return
        with self._lock:
            track = ""
            for suffix in ["| Free Listening on SoundCloud", "| Listen for free on SoundCloud"]:
                if suffix in title:
                    track = title.split("|")[0].strip()
                    break
            if not track and " - SoundCloud" in title:
                track = title.replace(" - SoundCloud", "").strip()
            if track.lower() in ("soundcloud", ""):
                track = ""
            if track == self.current:
                return
            self.current = track
            if track:
                parts   = track.split(" - ", 1)
                details = f"🎵 {parts[1].strip()}" if len(parts) == 2 else f"🎵 {track}"
                state   = f"by {parts[0].strip()}" if len(parts) == 2 else "SoundCloud"
                self.start_time = int(time.time())
            else:
                details, state = "", "Browsing SoundCloud"
            threading.Thread(target=self._push, args=(state, details), daemon=True).start()

    def reconnect(self, new_id: str):
        self.close()
        self.client_id  = new_id
        self.connected  = False
        self.current    = ""
        self.start_time = int(time.time())
        if new_id and DISCORD_AVAILABLE:
            threading.Thread(target=self._connect, daemon=True).start()

    def close(self):
        if self.connected and self.rpc:
            try:
                self.rpc.close()
            except Exception:
                pass


def make_tray_icon():
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soundcloud.png")
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#ff5500"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, 32, 32)
    p.setPen(QColor("#ffffff"))
    f = p.font()
    f.setBold(True)
    f.setPixelSize(14)
    p.setFont(f)
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "SC")
    p.end()
    return QIcon(px)


class SettingsDialog(QDialog):
    def __init__(self, parent, settings: dict):
        super().__init__(parent)
        self.settings = dict(settings)
        self.setWindowTitle("Settings")
        self.setFixedSize(440, 340)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._build_ui()
        self._style()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header.setFixedHeight(54)
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 20, 0)
        t = QLabel("Settings")
        t.setObjectName("headerTitle")
        hl.addWidget(t)
        root.addWidget(header)

        body = QWidget()
        body.setObjectName("body")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 22, 24, 22)
        bl.setSpacing(10)

        lbl = QLabel("Discord Application ID  (= Client ID)")
        lbl.setObjectName("boldLabel")
        bl.addWidget(lbl)

        sub = QLabel(
            "discord.com/developers → Select your app → "
            "Copy \"Application ID\" — this is also the Client ID."
        )
        sub.setObjectName("subLabel")
        sub.setWordWrap(True)
        bl.addWidget(sub)

        self.dc_input = QLineEdit()
        self.dc_input.setPlaceholderText("e.g.  123456789012345678")
        self.dc_input.setText(self.settings.get("discord_id", ""))
        self.dc_input.setObjectName("idInput")
        bl.addWidget(self.dc_input)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setObjectName("divider")
        bl.addSpacing(4)
        bl.addWidget(div)
        bl.addSpacing(4)

        self.discord_cb = QCheckBox("Enable Discord Rich Presence")
        self.discord_cb.setChecked(self.settings.get("discord_enabled", True))
        self.discord_cb.setObjectName("autoCheck")
        bl.addWidget(self.discord_cb)

        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setObjectName("divider")
        bl.addSpacing(4)
        bl.addWidget(div2)
        bl.addSpacing(4)

        self.autostart_cb = QCheckBox("Launch with Windows")
        self.autostart_cb.setChecked(self.settings.get("autostart", False))
        self.autostart_cb.setObjectName("autoCheck")
        bl.addWidget(self.autostart_cb)
        bl.addStretch()
        root.addWidget(body)

        footer = QWidget()
        footer.setObjectName("footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(24, 10, 24, 10)
        fl.addStretch()

        bc = QPushButton("Cancel")
        bc.setObjectName("btnCancel")
        bc.clicked.connect(self.reject)
        fl.addWidget(bc)

        bs = QPushButton("Save")
        bs.setObjectName("btnSave")
        bs.clicked.connect(self._save)
        fl.addWidget(bs)
        root.addWidget(footer)

    def _save(self):
        self.settings["discord_id"]      = self.dc_input.text().strip()
        self.settings["discord_enabled"] = self.discord_cb.isChecked()
        self.settings["autostart"]       = self.autostart_cb.isChecked()
        self.accept()

    def get_settings(self):
        return self.settings

    def _style(self):
        self.setStyleSheet("""
            QDialog   { background: #111; }
            #header   { background: #1a1a1a; border-bottom: 1px solid #252525; }
            #headerTitle { font-size: 14px; font-weight: 700; color: #fff; font-family: 'Segoe UI', sans-serif; }
            #body     { background: #111; }
            #boldLabel { font-size: 13px; font-weight: 600; color: #fff; font-family: 'Segoe UI', sans-serif; }
            #subLabel { font-size: 11px; color: #555; font-family: 'Segoe UI', sans-serif; }
            #idInput {
                background: #1c1c1c; border: 1px solid #2e2e2e; border-radius: 6px; color: #fff;
                font-family: 'Consolas', monospace; font-size: 13px; padding: 8px 12px;
            }
            #idInput:focus { border-color: #ff5500; }
            #divider  { color: #222; }
            #autoCheck { color: #ccc; font-size: 13px; font-family: 'Segoe UI', sans-serif; }
            #autoCheck::indicator { width: 16px; height: 16px; border: 1px solid #3a3a3a; border-radius: 4px; background: #1c1c1c; }
            #autoCheck::indicator:checked { background: #ff5500; border-color: #ff5500; }
            #footer   { background: #171717; border-top: 1px solid #222; }
            #btnCancel { background: #242424; color: #888; border: none; border-radius: 6px; padding: 8px 18px; font-size: 13px; font-family: 'Segoe UI', sans-serif; }
            #btnCancel:hover { background: #2e2e2e; color: #fff; }
            #btnSave { background: #ff5500; color: #fff; border: none; border-radius: 6px; padding: 8px 20px; font-size: 13px; font-weight: 600; font-family: 'Segoe UI', sans-serif; }
            #btnSave:hover { background: #ff6a1f; }
        """)


class SoundCloudPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        pass


class SoundCloudApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_settings()
        self.setWindowTitle("SoundCloud")
        self.setMinimumSize(800, 600)
        self.resize(1200, 800)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soundcloud.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.profile = QWebEngineProfile("soundcloud", self)
        self.profile.setPersistentStoragePath(DATA_DIR)
        self.profile.setCachePath(os.path.join(DATA_DIR, "cache"))
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self.profile.setHttpUserAgent(USER_AGENT)

        # Ad-Blocker
        self.ad_blocker = AdBlockInterceptor()
        self.profile.setUrlRequestInterceptor(self.ad_blocker)

        # Stealth-Script bei DocumentCreation registrieren (frühestmöglich)
        script = QWebEngineScript()
        script.setName("stealth")
        script.setSourceCode(STEALTH_EARLY)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self.profile.scripts().insert(script)

        page = SoundCloudPage(self.profile, self)
        self.browser = QWebEngineView()
        self.browser.setPage(page)
        self.browser.setUrl(QUrl("https://soundcloud.com"))
        self.setCentralWidget(self.browser)

        page.loadFinished.connect(self._on_load_finished)

        self.discord = DiscordPresence(self.cfg.get("discord_id", ""))

        self.title_timer = QTimer(self)
        self.title_timer.timeout.connect(
            lambda: self.discord.set_track(
                self.browser.page().title(),
                self.cfg.get("discord_enabled", True)
            )
        )
        self.title_timer.start(1000)

        self.ad_timer = QTimer(self)
        self.ad_timer.timeout.connect(self._inject_ad_hider)
        self.ad_timer.start(3000)

        self._build_tray()
        self._build_menu()

    def _on_load_finished(self, ok):
        page = self.browser.page()
        page.runJavaScript(AD_HIDE_CSS)
        page.runJavaScript(LIKE_THROTTLE_JS)

    def _inject_ad_hider(self):
        self.browser.page().runJavaScript(AD_HIDE_CSS)

    def _build_menu(self):
        bar = self.menuBar()
        bar.setStyleSheet("""
            QMenuBar { background: #111; color: #777; border-bottom: 1px solid #1e1e1e; font-size: 12px; font-family: 'Segoe UI', sans-serif; }
            QMenuBar::item:selected { background: #1e1e1e; color: #fff; }
            QMenu { background: #1a1a1a; color: #ccc; border: 1px solid #2a2a2a; font-size: 12px; }
            QMenu::item:selected { background: #ff5500; color: #fff; }
            QMenu::separator { background: #2a2a2a; height: 1px; }
        """)
        m = bar.addMenu("SoundCloud")
        m.addAction("⚙️  Settings", self._open_settings)
        m.addSeparator()
        m.addAction("✕  Quit", self._quit)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_tray_icon(), parent=self)
        self.tray.setToolTip("SoundCloud")
        menu = QMenu()
        menu.addAction("🎵  Open SoundCloud").triggered.connect(self._show_window)
        menu.addSeparator()
        menu.addAction("⚙️  Settings").triggered.connect(self._open_settings)
        menu.addSeparator()
        menu.addAction("✕  Quit").triggered.connect(self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _open_settings(self):
        dlg = SettingsDialog(self, self.cfg)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = dlg.get_settings()
            if new["autostart"] != self.cfg.get("autostart"):
                set_autostart(new["autostart"])
            id_changed     = new["discord_id"]      != self.cfg.get("discord_id")
            toggle_changed = new["discord_enabled"]  != self.cfg.get("discord_enabled", True)
            if id_changed or toggle_changed:
                if new["discord_enabled"] and new["discord_id"]:
                    self.discord.reconnect(new["discord_id"])
                else:
                    self.discord.close()
            self.cfg = new
            save_settings(self.cfg)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage("SoundCloud", "Still running in the background.",
                              QSystemTrayIcon.MessageIcon.Information, 2000)

    def _quit(self):
        self.discord.close()
        self.tray.hide()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SoundCloud")
    app.setQuitOnLastWindowClosed(False)
    window = SoundCloudApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
