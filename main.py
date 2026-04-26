from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSystemTrayIcon, QMenu,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QWidget
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage,
    QWebEngineUrlRequestInterceptor, QWebEngineScript
)
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
import sys
import os
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

STEALTH_EARLY = """
(function() {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['de-DE', 'de', 'en-US', 'en']});
    Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    window.chrome = {
        runtime: { id: undefined, connect: function() {}, sendMessage: function() {} },
        loadTimes: function() {}, csi: function() {}, app: {},
    };
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : origQuery(parameters)
    );
})();
"""

AD_HIDE_CSS_ONCE = """
(function() {
    if (window.__scAdHiderInstalled) return;
    window.__scAdHiderInstalled = true;

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
        (document.head || document.documentElement).appendChild(style);
    }

    const SELECTORS = [
        '[class*="promoted"]', '[class*="Promoted"]', '[class*="advertisement"]',
        '[class*="upsell"]', '[class*="Upsell"]', '[class*="adSlot"]',
        '[class*="adBanner"]', '[class*="listenWithGo"]', '[class*="goPromo"]',
        '[aria-label="Advertisement"]', '[data-testid*="ad"]', '[data-testid*="promoted"]',
    ].join(',');

    let scheduled = false;
    function removeAdNodes() {
        scheduled = false;
        document.querySelectorAll(SELECTORS).forEach(el => {
            if (!el.closest('.playControls') && !el.closest('nav')) {
                el.style.display = 'none';
            }
        });
    }

    function scheduleRemove() {
        if (!scheduled) {
            scheduled = true;
            requestAnimationFrame(removeAdNodes);
        }
    }

    removeAdNodes();
    const observer = new MutationObserver(scheduleRemove);
    observer.observe(document.documentElement, { childList: true, subtree: true });
})();
"""

LIKE_THROTTLE_JS = """
(function() {
    if (window.__scLikeThrottleInstalled) return;
    window.__scLikeThrottleInstalled = true;

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
    defaults = {"autostart": False}
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
        self.setFixedSize(340, 180)
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
        bl.setContentsMargins(24, 20, 24, 20)
        bl.setSpacing(10)

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
        self.settings["autostart"] = self.autostart_cb.isChecked()
        self.accept()

    def get_settings(self):
        return self.settings

    def _style(self):
        self.setStyleSheet("""
            QDialog   { background: #111; }
            #header   { background: #1a1a1a; border-bottom: 1px solid #252525; }
            #headerTitle { font-size: 14px; font-weight: 700; color: #fff; font-family: 'Segoe UI', sans-serif; }
            #body     { background: #111; }
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

        self.ad_blocker = AdBlockInterceptor()
        self.profile.setUrlRequestInterceptor(self.ad_blocker)

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

        self._build_tray()
        self._build_menu()

    def _on_load_finished(self, ok):
        page = self.browser.page()
        page.runJavaScript(AD_HIDE_CSS_ONCE)
        page.runJavaScript(LIKE_THROTTLE_JS)

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
            self.cfg = new
            save_settings(self.cfg)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage("SoundCloud", "Still running in the background.",
                              QSystemTrayIcon.MessageIcon.Information, 2000)

    def _quit(self):
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
