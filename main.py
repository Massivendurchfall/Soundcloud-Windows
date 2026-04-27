from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSystemTrayIcon, QMenu,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QWidget, QLineEdit
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage,
    QWebEngineUrlRequestInterceptor, QWebEngineScript
)
from PyQt6.QtCore import QUrl, Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
import sys
import os
import json
import shutil
import winreg
import time
from pypresence import Presence

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "SoundCloudApp")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
os.makedirs(DATA_DIR, exist_ok=True)


def _clear_corrupt_cache():
    for name in ("GPUCache", "ShaderCache", "Code Cache"):
        p = os.path.join(CACHE_DIR, name)
        if os.path.isdir(p):
            try:
                shutil.rmtree(p)
            except Exception:
                pass
    index = os.path.join(CACHE_DIR, "index")
    if os.path.isfile(index):
        try:
            os.remove(index)
        except Exception:
            pass


_clear_corrupt_cache()
os.makedirs(CACHE_DIR, exist_ok=True)

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-blink-features=AutomationControlled "
    "--no-sandbox "
    "--autoplay-policy=no-user-gesture-required "
    "--disable-features=AudioServiceOutOfProcess"
)

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
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

GET_TRACK_INFO_JS = """
(function() {
    try {
        const playControls = document.querySelector('.playControls');
        if (!playControls) return null;

        const playButton = playControls.querySelector('button[title*="Pause"], button[aria-label*="Pause"]');
        const isPlaying = !!playButton;

        const titleLink = playControls.querySelector('a[class*="playbackSoundBadge__titleLink"]');
        const artistLink = playControls.querySelector('a[class*="playbackSoundBadge__lightLink"]');

        if (!titleLink) return null;

        const title = titleLink.textContent.trim();
        const artist = artistLink ? artistLink.textContent.trim() : 'Unknown Artist';

        let artworkUrl = null;
        const artworkImg = playControls.querySelector('img[class*="sc-artwork"]');
        if (artworkImg && artworkImg.src) {
            artworkUrl = artworkImg.src.replace('-t50x50.', '-t500x500.');
        }

        const trackUrl = titleLink.href || window.location.href;

        const timeElements = playControls.querySelectorAll(
            'span[class*="playbackTimeline__timePassed"], span[class*="playbackTimeline__duration"]'
        );
        let currentTime = null;
        let duration = null;

        if (timeElements.length >= 2) {
            const parseTime = (str) => {
                const parts = str.split(':').map(p => parseInt(p, 10));
                if (parts.length === 2) return parts[0] * 60 + parts[1];
                if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
                return 0;
            };
            currentTime = parseTime(timeElements[0].textContent);
            duration = parseTime(timeElements[1].textContent);
        }

        return {
            isPlaying: isPlaying,
            title: title,
            artist: artist,
            artworkUrl: artworkUrl,
            trackUrl: trackUrl,
            currentTime: currentTime,
            duration: duration,
            timestamp: Date.now()
        };
    } catch (e) {
        return null;
    }
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
    defaults = {
        "autostart": False,
        "discord_rpc": True,
        "discord_client_id": "",
    }
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
        self.setFixedSize(360, 310)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._build_ui()
        self._style()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header ──────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(54)
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 20, 0)
        t = QLabel("Settings")
        t.setObjectName("headerTitle")
        hl.addWidget(t)
        root.addWidget(header)

        # ── Body ─────────────────────────────────────────────────────────────
        body = QWidget()
        body.setObjectName("body")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 18, 24, 18)
        bl.setSpacing(10)

        self.autostart_cb = QCheckBox("Launch with Windows")
        self.autostart_cb.setChecked(self.settings.get("autostart", False))
        self.autostart_cb.setObjectName("settingsCheck")
        bl.addWidget(self.autostart_cb)

        self.discord_rpc_cb = QCheckBox("Show in Discord (Rich Presence)")
        self.discord_rpc_cb.setChecked(self.settings.get("discord_rpc", True))
        self.discord_rpc_cb.setObjectName("settingsCheck")
        bl.addWidget(self.discord_rpc_cb)

        # separator line
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setObjectName("sep")
        bl.addWidget(sep)

        id_label = QLabel("Discord Application Client ID")
        id_label.setObjectName("idLabel")
        bl.addWidget(id_label)

        self.client_id_input = QLineEdit()
        self.client_id_input.setObjectName("clientIdInput")
        self.client_id_input.setPlaceholderText("z.B. 1234567890123456789")
        self.client_id_input.setText(self.settings.get("discord_client_id", ""))
        self.client_id_input.setMaxLength(30)
        bl.addWidget(self.client_id_input)

        hint = QLabel(
            '<a href="https://discord.com/developers/applications" '
            'style="color:#ff5500;text-decoration:none;">'
            '↗ Discord Developer Portal</a>'
        )
        hint.setOpenExternalLinks(True)
        hint.setObjectName("hintLabel")
        bl.addWidget(hint)

        # validation label (hidden by default)
        self.val_label = QLabel("")
        self.val_label.setObjectName("valLabel")
        self.val_label.setVisible(False)
        bl.addWidget(self.val_label)

        bl.addStretch()
        root.addWidget(body)

        # ── Footer ───────────────────────────────────────────────────────────
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
        client_id = self.client_id_input.text().strip()

        # Validate: if RPC is enabled, client_id must look valid
        if self.discord_rpc_cb.isChecked() and client_id:
            if not client_id.isdigit() or len(client_id) < 17:
                self.val_label.setText("⚠ Client ID ungültig – nur Zahlen, mind. 17 Stellen")
                self.val_label.setVisible(True)
                return

        self.val_label.setVisible(False)
        self.settings["autostart"] = self.autostart_cb.isChecked()
        self.settings["discord_rpc"] = self.discord_rpc_cb.isChecked()
        self.settings["discord_client_id"] = client_id
        self.accept()

    def get_settings(self):
        return self.settings

    def _style(self):
        self.setStyleSheet("""
            QDialog         { background: #111; }
            #header         { background: #1a1a1a; border-bottom: 1px solid #252525; }
            #headerTitle    { font-size: 14px; font-weight: 700; color: #fff;
                              font-family: 'Segoe UI', sans-serif; }
            #body           { background: #111; }
            #sep            { background: #232323; margin: 4px 0; }
            #settingsCheck  { color: #ccc; font-size: 13px; font-family: 'Segoe UI', sans-serif; }
            #settingsCheck::indicator {
                width: 16px; height: 16px;
                border: 1px solid #3a3a3a; border-radius: 4px; background: #1c1c1c;
            }
            #settingsCheck::indicator:checked { background: #ff5500; border-color: #ff5500; }
            #idLabel        { color: #888; font-size: 11px; font-family: 'Segoe UI', sans-serif;
                              margin-top: 2px; }
            #clientIdInput  { background: #1c1c1c; color: #fff;
                              border: 1px solid #3a3a3a; border-radius: 6px;
                              padding: 6px 10px; font-size: 12px;
                              font-family: 'Segoe UI', sans-serif; }
            #clientIdInput:focus { border-color: #ff5500; outline: none; }
            #hintLabel      { font-size: 11px; font-family: 'Segoe UI', sans-serif; }
            #valLabel       { color: #ff4444; font-size: 11px;
                              font-family: 'Segoe UI', sans-serif; }
            #footer         { background: #171717; border-top: 1px solid #222; }
            #btnCancel      { background: #242424; color: #888; border: none;
                              border-radius: 6px; padding: 8px 18px;
                              font-size: 13px; font-family: 'Segoe UI', sans-serif; }
            #btnCancel:hover { background: #2e2e2e; color: #fff; }
            #btnSave        { background: #ff5500; color: #fff; border: none;
                              border-radius: 6px; padding: 8px 20px;
                              font-size: 13px; font-weight: 600;
                              font-family: 'Segoe UI', sans-serif; }
            #btnSave:hover  { background: #ff6a1f; }
        """)


class SoundCloudPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        pass  # Konsole sauber halten


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

        # ── WebEngine Profile ────────────────────────────────────────────────
        self.profile = QWebEngineProfile("soundcloud", self)
        self.profile.setPersistentStoragePath(DATA_DIR)
        self.profile.setCachePath(CACHE_DIR)
        self.profile.setHttpCacheMaximumSize(80 * 1024 * 1024)
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

        # ── Discord Rich Presence ────────────────────────────────────────────
        self.discord_rpc: Presence | None = None
        self.last_track_info: dict | None = None
        self.rpc_start_time: int | None = None
        self._init_discord_rpc()

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_discord_presence)
        self.update_timer.start(5000)

    # ── Discord helpers ──────────────────────────────────────────────────────

    def _init_discord_rpc(self):
        """Verbinde mit Discord RPC, wenn Client ID gesetzt und gültig."""
        if not self.cfg.get("discord_rpc", True):
            return

        client_id = self.cfg.get("discord_client_id", "").strip()
        if not client_id:
            print("Discord RPC: Keine Client ID angegeben (Settings → Discord Client ID).")
            return
        if not client_id.isdigit() or len(client_id) < 17:
            print(f"Discord RPC: Client ID '{client_id}' sieht ungültig aus.")
            return

        try:
            self.discord_rpc = Presence(client_id)
            self.discord_rpc.connect()
            print(f"Discord RPC verbunden (Client ID: {client_id}).")
        except Exception as e:
            print(f"Discord RPC Fehler: {e}")
            self.discord_rpc = None

    def _disconnect_discord_rpc(self):
        """Sauberes Trennen der RPC-Verbindung ohne Asyncio-Leak."""
        rpc = self.discord_rpc
        self.discord_rpc = None          # erst None setzen → Timer greift nicht mehr rein
        self.last_track_info = None
        self.rpc_start_time = None
        if rpc is None:
            return
        try:
            rpc.clear()
        except Exception:
            pass
        try:
            # pypresence hat einen eigenen Event-Loop – sauber stoppen
            loop = getattr(rpc, "loop", None)
            if loop and not loop.is_closed():
                loop.call_soon_threadsafe(loop.stop)
            rpc.close()
        except Exception:
            pass

    def _update_discord_presence(self):
        """Wird alle 5 s aufgerufen – holt Track-Info per JS und updated Discord."""
        if not self.discord_rpc:
            return

        def handle_track_info(result):
            if not self.discord_rpc:
                return
            try:
                if not result or not isinstance(result, dict):
                    # Nichts spielt – Presence leeren
                    if self.last_track_info is not None:
                        try:
                            self.discord_rpc.clear()
                        except Exception:
                            pass
                        self.last_track_info = None
                    return

                is_playing  = result.get("isPlaying", False)
                title       = result.get("title", "Unknown Track")
                artist      = result.get("artist", "Unknown Artist")
                duration    = result.get("duration")
                current_time = result.get("currentTime")
                track_url   = result.get("trackUrl", "")

                track_changed = (
                    self.last_track_info is None
                    or self.last_track_info.get("title") != title
                    or self.last_track_info.get("artist") != artist
                )

                if is_playing:
                    kwargs = dict(
                        details=title[:128],               # Discord-Limit
                        state=f"by {artist}"[:128],
                        large_image="soundcloud_logo",     # Asset-Name im Developer Portal
                        large_text="SoundCloud",
                        small_image="playing",
                        small_text="Playing",
                    )

                    # Zeitstempel → Fortschrittsbalken in Discord
                    if duration and current_time is not None and duration > 0:
                        if track_changed or self.rpc_start_time is None:
                            self.rpc_start_time = int(time.time()) - current_time
                        kwargs["start"] = self.rpc_start_time
                        kwargs["end"]   = self.rpc_start_time + duration

                    # "Listen on SoundCloud"-Button (nur bei gültiger URL)
                    if track_url and track_url.startswith("https://soundcloud.com"):
                        kwargs["buttons"] = [{"label": "Listen on SoundCloud", "url": track_url}]

                    self.discord_rpc.update(**kwargs)

                else:
                    # Pausiert – kein Timestamp, kein Fortschrittsbalken
                    if track_changed:
                        self.rpc_start_time = None
                    self.discord_rpc.update(
                        details=title[:128],
                        state=f"by {artist}"[:128],
                        large_image="soundcloud_logo",
                        large_text="SoundCloud",
                        small_image="paused",
                        small_text="Paused",
                    )

                self.last_track_info = result

            except Exception as e:
                print(f"Discord presence update error: {e}")

        self.browser.page().runJavaScript(GET_TRACK_INFO_JS, handle_track_info)

    # ── Page load ───────────────────────────────────────────────────────────

    def _on_load_finished(self, ok):
        page = self.browser.page()
        page.runJavaScript(AD_HIDE_CSS_ONCE)
        page.runJavaScript(LIKE_THROTTLE_JS)

    # ── UI builders ─────────────────────────────────────────────────────────

    def _build_menu(self):
        bar = self.menuBar()
        bar.setStyleSheet("""
            QMenuBar { background: #111; color: #777; border-bottom: 1px solid #1e1e1e;
                       font-size: 12px; font-family: 'Segoe UI', sans-serif; }
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

    # ── Tray / window actions ────────────────────────────────────────────────

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
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new = dlg.get_settings()

        autostart_changed  = new["autostart"]       != self.cfg.get("autostart")
        rpc_enabled_change = new["discord_rpc"]      != self.cfg.get("discord_rpc")
        client_id_change   = new["discord_client_id"] != self.cfg.get("discord_client_id")

        if autostart_changed:
            set_autostart(new["autostart"])

        # Reconnect wenn RPC-Einstellungen sich geändert haben
        if rpc_enabled_change or client_id_change:
            self._disconnect_discord_rpc()
            self.cfg = new
            save_settings(self.cfg)
            if new["discord_rpc"]:
                self._init_discord_rpc()
        else:
            self.cfg = new
            save_settings(self.cfg)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "SoundCloud",
            "Läuft noch im Hintergrund.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _quit(self):
        self.update_timer.stop()
        self._disconnect_discord_rpc()
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
