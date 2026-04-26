# SoundCloud Desktop
SoundCloud doesn't have a Windows app. This is one.
Built with PyQt6 + QtWebEngine — runs SoundCloud in a proper desktop window with a system tray, so it doesn't sit in your browser eating a tab.

## Features

- Runs SoundCloud in its own window
- Lives in the system tray when closed
- Ad blocker built in
- Launches with Windows (optional)
- Persistent login stays logged in between sessions

## Installation
```
pip install PyQt6 PyQt6-WebEngine pypresence
python main.py
```

## Build
```
python build.py
```

Produces a standalone `SoundCloud.exe` in `dist/SoundCloud/`.

## Discord Rich Presence

Go to [discord.com/developers](https://discord.com/developers), create an app, copy the Application ID and paste it into Settings inside the app.
