<div align="center">

# Beyonder

**A fast, good-looking browser and profile launcher for Windows.**

Beyonder finds the browsers installed on your PC by itself and gives every browser profile its own one-click card.

![Platform](https://img.shields.io/badge/platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![WebView2](https://img.shields.io/badge/UI-pywebview%20%2B%20WebView2-00C2FF?style=for-the-badge)

<br>

<img src="assets/screenshots/light1.png" width="100%" alt="Beyonder, main window (light)">
<img src="assets/screenshots/dark1.png" width="100%" alt="Beyonder, main window (dark)">

</div>

<br>

## Highlights

- **Automatic browser discovery.** Scans the same list Windows uses for Default apps, plus the usual install folders.
- **One card per profile.** Chromium, Firefox family and Opera GX profiles are read straight from the browser, with real names and pictures.
- **Read-only and safe.** Beyonder never deletes or changes anything inside a browser's own data. Remove is always undoable.
- **Native window, web interface.** A pywebview window (WebView2) with an HTML/CSS/JS interface and Python logic behind it.
- **Lives in your tray.** Start with Windows, a global hotkey, and your 5 most recent profiles one click away.
- **Light, Dark or System theme**, drag-to-reorder, launch statistics, and one-click backup and restore.

## Download
 
Grab the latest build from the [**Releases page**](../../releases/latest).
 
| File | What it is |
|---|---|
| [`Beyonder-Windows.zip`](../../releases/latest/download/Beyonder-Windows.zip) | Ready-to-run app. Unzip it and run `Beyonder.exe`. No Python needed. |
| [`Beyonder-Source.zip`](../../releases/latest/download/Beyonder-Source.zip) | The source code, to run with Python or build yourself. |
 
> [!NOTE]
> The `.exe` is not code-signed, so Windows SmartScreen may show a warning the first time. Choose **More info**, then **Run anyway**.

## Quick start

1. Install **Python 3.9 or newer** for Windows (64-bit) and the **Microsoft Edge WebView2 Runtime** (already present on Windows 11 and most Windows 10 PCs).
2. Double-click `beyonder.pyw`.
3. On the first run the app installs `pywebview`, `Pillow` and `pystray` by itself. This needs internet and takes a short while before the window appears. If it fails, run:

   ```
   pip install pywebview Pillow pystray
   ```

If WebView2 is missing, a message box shows the download link.

<details>
<summary><b>More screenshots</b></summary>

<br>

<table>
  <tr>
    <td align="center"><b>Dark Mode</b></td>
    <td align="center"><b>Light Mode</b></td>
  </tr>
  <tr>
    <td><img src="assets/screenshots/dark2.png" alt="Dark 2"></td>
    <td><img src="assets/screenshots/light2.png" alt="Light 2"></td>
  </tr>
  <tr>
    <td><img src="assets/screenshots/dark3.png" alt="Dark 3"></td>
    <td><img src="assets/screenshots/light3.png" alt="Light 3"></td>
  </tr>
  <tr>
    <td><img src="assets/screenshots/dark4.png" alt="Dark 4"></td>
    <td><img src="assets/screenshots/light4.png" alt="Light 4"></td>
  </tr>
</table>

</details>

## Contents

- [Folder layout](#folder-layout)
- [Adding browsers](#adding-browsers)
- [The Default profile](#the-default-profile)
- [Adding profiles](#adding-profiles)
- [Profile cards and Edit](#profile-cards-and-edit)
- [Sync at launch](#sync-at-launch)
- [Right-click menus](#right-click-menus)
- [Using Beyonder](#using-beyonder) (window controls, tray, settings, shortcuts)
- [Data](#data)
- [Troubleshooting](#troubleshooting)
- [Package as an .exe](#package-as-an-exe-with-pyinstaller)
- [Under the hood](#under-the-hood)

---

## Folder layout

```
Beyonder/
├── beyonder.pyw        entry point
├── ui/                 index.html, css/style.css, js/*.js
├── assets/
│   ├── favicon.ico     title bar, taskbar and Alt-Tab icon
│   ├── fonts/          Heading.ttf, Accent.ttf, Body.ttf, Button.ttf
│   └── screenshots/    dark1-4.png, light1-4.png
└── data/               created on first run (your browsers, stats, log)
```

## Adding browsers

Click **+ New** in the top row. A popup scans this PC for the browsers Windows knows about (the same list Windows uses for Default apps, plus the usual install folders), shows every browser it finds with its own icon, and lets you pick several at once.

- Click an icon to lock onto it, click again to let go.
- The checkbox selects or clears everything shown. The search bar filters the grid.
- Browsers that are already in Beyonder are **not shown** in the popup.
- The counter on the right of the tools row reads `SELECTED 01 / 04`, followed by ` · 03 ADDED` when some browsers are already in Beyonder. When nothing is left to pick it reads `03 ADDED`.

**Add Manually** is the last tile of the grid. It opens the Windows file picker for an `.exe` file, for a browser the scan can't find.

- Beyonder names it by itself: a known browser name from the path, else the program's product name, else its folder name, with ` (2)` added if the name is taken.
- The icon is taken from the file, and a new, already selected tile is placed just before the Add Manually tile.
- You can pick several in a row and then press Add once. Picking a browser that is already in the grid just selects it.
- When there is nothing to show (everything already added, nothing found, or a search without a match), only the Add Manually tile appears, in the middle of the popup.

No names or icons to type: the name comes from Windows and the icon from the browser's program file.

Every browser added this way also gets a **Default** profile (see below), and Beyonder starts looking for the folder where the browser keeps its profiles in the background, so the first **Add Profiles** click is quick. While the popup scans, the loader (a row of 8 blocks with a cyan, pink and white/black light wave) sits in the middle of the browser grid, not over the whole popup.

## The Default profile

When a browser is added with the **+ New** popup, Beyonder creates a profile named **Default** in it. Its picture is the browser's icon and it does exactly what `Open` does: it starts the browser's program file with no arguments, so launching is quick. It counts in the launch statistics like any profile.

- **Name and picture:** the name is fixed, and the Edit popup shows it read-only. The picture can be changed, and `Reset` next to it brings the browser's icon back.
- **Removing it:** it can be removed like any profile (Undo toast, and the Removed items list in Settings). To bring it back faster, right-click the browser and choose `Add to Profiles`. This item appears only when the browser has no Default profile.
- **Beyonder's own profile:** it is not part of the browser's profile list, so the sync at launch never compares it with the browser (it still turns red when the browser's program file is gone, like every card). Its folder is `data/<Browser>/_beyonder_default`.
- **Older browsers:** browsers that were added before this version do not get one automatically; use `Add to Profiles`.
- **Not the same as Chromium's `Default`:** a Chromium browser's own `Default` profile folder appears in Add Profiles as `[ Default ]` and has its own key.

## Adding profiles

Select a browser and press **Add Profiles**. The popup reads the browser's own profile list and shows one row per profile: a checkbox, the real profile name, and the profile's folder name in square brackets on the right (`[ Profile 1 ]`).

- The search bar filters by name and folder.
- Rows are Tab-focusable, and Space or Enter toggles them.
- **Shift+Click** applies the state of the row you clicked first to every importable row up to the one you Shift+Click.
- Profiles that are already in Beyonder are shown checked, greyed out and locked, so duplicates cannot happen.
- **Select all** only touches the importable rows, and the counter (`SELECTED 02 / 05`) counts only those.
- A profile is identified by the folder key the browser uses, never by its name, so two profiles may share a display name.

While the popup reads, the loader sits in the middle of the profile list (the search bar and Select all stay as they are). Empty and error states:

| Message | When it appears |
|---|---|
| `NO PROFILES FOUND` | The browser has no profiles at all, or its folder cannot be found |
| `NO MATCH` | The search matches none |
| `COULD NOT READ PROFILES` | A profile file exists but cannot be read |

### Supported browsers

Profiles are always read **read-only**, and a browser may be running.

| Family | Browsers | Source | Launch |
|---|---|---|---|
| **Chromium** | Chrome, Edge, Brave, Vivaldi, Chromium, Helium and other Chromium browsers | `Local State` in the `User Data` folder | `--profile-directory=<folder>` |
| **Firefox** | Firefox, LibreWolf, Waterfox, Zen, Floorp | `profiles.ini` under `%APPDATA%` | `-no-remote -P "<name>"` |
| **Opera GX** | Opera GX | its own `_side_profiles` folder | `--side-profile-name=<folder>` plus fixed flags |
| **No profile system** | Opera, Tor Browser | none | Default profile only |

<details>
<summary><b>How each family is read (details)</b></summary>

<br>

**Chromium browsers.** Reads `Local State` inside the browser's `User Data` folder:

- `%LOCALAPPDATA%\Google\Chrome\User Data`, `Microsoft\Edge`, `BraveSoftware\Brave-Browser`, `Vivaldi`, `Chromium`, `imput\Helium`
- portable installs next to the program
- any other `User Data` folder one or two levels below `%LOCALAPPDATA%` that matches the browser's name

The name is Chrome's own profile name. The picture is `Google Profile Picture.png` when there is one, otherwise a coloured tile with the first letter.

**Firefox family.** Reads `profiles.ini` in the browser's folder under `%APPDATA%`. No pictures (initial tile).

**Opera GX.** Reads its own `_side_profiles` folder: `<program folder>\profiles\data\_side_profiles` for standalone installs, else `%APPDATA%\Opera Software\Opera GX Stable\_side_profiles`. The folder is always there; it only has no folders inside while no side profile exists. Each profile folder has a json (name, colour, theme) and an `.ico` picture. The fixed flags are kept in `OPERA_GX_FIXED_FLAGS` in `beyonder.pyw`.

**Browsers without a profile system** (plain **Opera** and **Tor Browser**). Add Profiles opens the `Not supported yet` notice at once, without opening the Add Profiles popup. Their only profile is the Default one. The list is `UNSUPPORTED_KINDS` in `beyonder.pyw` (plus a matching kind in `browser_kind`); add a row to cover another browser.

</details>

<details>
<summary><b>How Beyonder finds a browser's profile folder (details)</b></summary>

<br>

The folder a reader found is remembered as `data_dir` in the browser's `browser.json` (for Opera GX, the folder that holds `_side_profiles`). It is looked for again when the remembered folder no longer exists. The search order depends on where the program file is:

- **Under `%ProgramFiles%`, `%ProgramFiles(x86)%` or `%LOCALAPPDATA%`** (a normal install): the usual places first (the tables in `beyonder.pyw`: `CHROMIUM_DATA_DIRS`, `FIREFOX_DATA_DIRS`, the Opera GX folders), then the folders around the program file.
- **Anywhere else** (a standalone or portable browser): the folders around the program file first, then the usual places, because a portable build keeps its data next to itself.

Looking around the program file (`find_data_dir_near_exe`) is strictly read-only: it only lists names, never opens anything for writing, and never follows symlinks or junctions.

- The program's own folder is searched completely, with no depth, count or time limit. Folders named Cache, Code Cache, GPUCache, Service Worker, Crashpad, Extensions, node_modules, .git, $Recycle.Bin, System Volume Information and Windows are skipped.
- Only when that finds nothing, the parent and grandparent folders are searched through their `Data`, `Profile`, `Profiles` and `User Data` subfolders (the portable layout: program in `App`, data in a sibling `Data`).
- A drive root or a system folder such as Program Files is never searched as a whole.

What it looks for:

- **Chromium:** a folder with `Local State` (one that also has `Default` or `Profile N` wins).
- **Firefox family:** a folder with `profiles.ini`, or the profile folder of a portable build (a `Profile` or `Data` folder with `prefs.js`, shown as one profile named `Default`).
- **Opera GX:** the folder that holds `_side_profiles`.

The number of folders, entries and the time it took are written to `data/error.log`.

The search starts in the background when a browser is added. If you press Add Profiles while it is still running, the popup waits for it and shows its loader. A browser whose folder cannot be found at all opens the popup with `NO PROFILES FOUND`.

> [!NOTE]
> Paths added from the web (VERIFY): Helium `%LOCALAPPDATA%\imput\Helium\User Data` (and the plain `Helium\User Data`), Zen `%APPDATA%\zen`, LibreWolf `%APPDATA%\LibreWolf`, Waterfox `%APPDATA%\Waterfox` and the older `%APPDATA%\Waterfox\Waterfox`. Floorp keeps `%APPDATA%\Floorp` and relies on the search around its program file.

</details>

## Profile cards and Edit

Cards show the picture, name and launch count. A profile without a picture gets a tile in its colour (or a colour derived from its key) with its first letter, drawn in the heading font and centered exactly on the visible shape of the letter (`BYD.initialSvg` in `ui/js/bridge.js`, used by the cards and the Edit popup).

**Edit** changes only Beyonder's copy: the **name** and the **picture** (with the crop and zoom popup). `Reset` next to each field brings back the browser's own name or picture. Edits are never written to the browser.

## Sync at launch

Once per launch, in the background, Beyonder compares every imported profile with its browser:

- The browser's name replaces the card's name unless you renamed it.
- Colours and pictures are refreshed (a picture you chose yourself is kept).
- The launch arguments are updated.
- A profile the browser no longer has turns red (`LINK LOST`) and comes back to normal if it reappears. Its record and folder are never deleted.
- If a browser's program moved, Beyonder looks for the same browser again and updates the path.
- New profiles are **never** added automatically: they only appear in the Add Profiles popup.

This only happens when the browser's data folder was found and read. When it could not be located at all, Beyonder cannot tell, and every imported profile of that browser is left untouched. The Default profile is never compared with the browser. Changes made in a browser while Beyonder is open show up after the next launch.

## Right-click menus

| Right-click on | Options |
|---|---|
| A **browser** | `Open` (starts the browser normally, launch statistics do not change), `Remove`, and `Add to Profiles` (brings back the Default profile, shown only while it does not exist) |
| A **profile card** | `Edit` and `Remove` |

There is no Delete anywhere. Beyonder never deletes or changes anything inside a browser's own data. Everything about a profile in Beyonder is a link plus a visual copy; Remove (with Undo and the Removed items list) only drops it from the list and keeps Beyonder's own folder.

---

## Using Beyonder

### Window controls

- Beyonder opens maximized (taskbar stays visible). The restore button returns it to a smaller window.
- Clicking its taskbar button minimizes it when it is focused, and restores it when it is minimized.
- Drag the title bar to move the window. Double-click it to maximize or restore.
- Drag any window edge or corner to resize. The 1280x800 design scales uniformly to fit.

### Tray, taskbar and start with Windows

- **Start with Windows:** Beyonder adds itself to your Windows startup list (current user) and starts hidden, so it only sits in the tray. The entry always points at the copy that ran last, so after packaging, run `Beyonder.exe` once and it takes over. Turn it off in Settings or from the tray menu.
- **Tray icon:** Windows keeps new tray icons inside the arrow next to the Wi-Fi icon. Click the icon to open Beyonder. Right-click for Open, your 5 most recently launched profiles (click one to launch it without opening the window), Start with Windows and Quit Beyonder.
- **Cross button:** by default the Cross in the title bar (and Alt+F4) hides the window to the tray and Beyonder keeps running; use Quit Beyonder in the tray menu to really close it. In Settings you can switch the Cross button to quit instead.
- **Edge to edge:** maximized, the window has no rounded corners and no 1px border (Windows 11 adds both to every window), so it meets the screen edges like any other maximized app. Restoring brings them back.
- **Minimize:** the taskbar button shows only the icon while Beyonder is minimized and shows the title again when it is open.
- **Opening a profile** minimizes Beyonder automatically (can be turned off in Settings).
- **Only one copy runs.** Starting Beyonder again brings the running one to the front.

### Settings

The gear button in the title bar opens Settings. Changes apply at once and are saved in `data/settings.json`.

| Setting | What it does |
|---|---|
| **Theme** | Light, Dark or System (follows the Windows 11 app color mode, live). Switching plays the scanline wipe. |
| **Start with Windows** | Adds or removes Beyonder from your startup list. |
| **Minimize after launch** | On or off. |
| **Cross button** | Hide to tray, or quit. |
| **Global hotkey** | Off by default. A shortcut that shows Beyonder, or hides it when it is already in front. Click the Keys button and press the combination (it needs Ctrl, Alt or Win). If another app already owns it, Settings says so. |
| **Backup** | Export saves everything in `data/` (not the error log) as one zip. Restore replaces `data/` with a backup; a copy of the current data is saved first as `data-before-restore-<time>.zip` next to the data folder. |
| **Removed items** | Lists browsers and profiles you removed (their folders are still on disk) with Restore. |
| **Default sort** | Manual (the order you added them), Most used or Recent. The order is applied the next time the cards are drawn, never while you are looking at them. |

### Keyboard and mouse

- **Arrow keys** move between profile cards, **Enter** launches the focused one.
- **Ctrl+1** to **Ctrl+9** switch to the 1st to 9th browser.
- **Drag** a browser in the top row or a profile card to a new place; the others move out of the way and the order is saved. Dragging a card while the sort is Most used or Recent turns the order you see into the Manual order and switches the sort to Manual.

### Broken cards and Undo

- A profile whose browser program no longer exists gets a permanent red border and an infected look with a `[ LINK LOST ]` tag. It is checked at load and again whenever the window comes back to the front.
- Remove shows a small Undo toast in the bottom-left corner for 5 seconds. Undo brings it back at its old position, Cancel closes the toast and keeps it removed.

---

## Data

Everything Beyonder stores lives in the `data/` folder next to the app.

```
data/launcher.json                 {"browsers":[{"name":..., "exe":...}]}
data/stats.json                    {"launches": 42, "usage": {"<Browser>": {"<profile key>": {"n": 3, "last": 1762400000}}}}
data/<Browser>/icon.png            the browser's icon
data/<Browser>/browser.json        {"exe": "C:\\...\\browser.exe", "data_dir": "the folder the profiles are read from"}
data/<Browser>/imported.json       {"profiles":[{"key", "name", "source_name", "renamed", "color", "args", "avatar_custom"}]}
data/<Browser>/<key>/avatar.png    the profile's picture (at most 256 px); a removed profile also keeps profile.json here
data/<Browser>/_beyonder_default/  the Default profile (key `_beyonder_default`), same layout
```

- A profile's folder is named after its key (made filename-safe). Older manual profiles (named folders from v13) are ignored, never deleted.
- This is a new system. `data/browsers.json` and the folders of the old manual version are left alone and ignored; nothing is deleted.
- Remove keeps the folder, so Restore and Undo are lossless. There is no Delete: Beyonder never deletes anything of a browser.
- A damaged `launcher.json` is copied to `launcher.json.bad-<time>` before anything is overwritten.
- Launches count every successful launch. `usage` holds each profile's own launch count and last-used time (used by the Most used / Recent sort).
- A profile opens by starting its browser's program file with the profile's `args`. A card turns red (`[ LINK LOST ]`) when its browser's program file has been moved or uninstalled, or when the browser no longer has that profile.

## Troubleshooting

- `data/error.log` records Python and JavaScript errors.
- A pink error panel appears at the bottom left of the window for any error. Close it with the Close button.
- Set the environment variable `BEYONDER_DEBUG=1` before starting to enable the WebView2 developer tools (right-click, Inspect).
- If fonts look wrong, check that the four files in `assets/fonts` are named exactly `Heading.ttf`, `Accent.ttf`, `Body.ttf`, `Button.ttf`. Until `Button.ttf` exists, buttons fall back to the Heading font. A font that fails to load is logged.

## Package as an .exe with PyInstaller

```
pip install pyinstaller pywebview Pillow pystray
pyinstaller --noconsole --onedir --name Beyonder --icon assets\favicon.ico ^
  --add-data "ui;ui" --add-data "assets;assets" --collect-all webview ^
  --hidden-import pystray._win32 beyonder.pyw
```

- `--onedir` starts faster than `--onefile` (nothing is unpacked on every launch), which matters for a daily launcher.
- The finished app is the folder `dist\Beyonder`. Run `Beyonder.exe` inside it and copy your `data` folder next to `Beyonder.exe`. The app keeps `data` beside the .exe, never inside the bundle.
- `--icon` gives the .exe the same logo. The running window takes its icon from `assets/favicon.ico` through WM_SETICON.
- A packaged build does not auto-install packages, so install them before building.
- Rebuild after every code change.

### Pin it to the taskbar

1. Unpin any old Beyonder shortcut (for example the one that pointed at `pythonw.exe`).
2. Start `Beyonder.exe`.
3. Right-click its taskbar icon and choose **Pin to taskbar**.

Pinning from the running window gives the pin the same hidden app ID the window uses, so clicking the pinned icon opens Beyonder in that same icon, with no second icon next to it.

## Under the hood

<details>
<summary><b>Popup animation</b></summary>

<br>

Every popup opens with a line wipe and closes with the exact reverse (glow revealed with the line, 6 px line, 85% bar thickness, 6 bars). The duration is 1 ms per 1 px of the popup's height, capped at 600 ms: popups taller than 600 px use a static 600 ms. The glow's closing step stays at a fixed 180 ms. The glitch line and bars end the instant the popup is fully formed.

The settings are the constants at the top of the popup wipe section in `ui/js/modal.js`: `WIPE_CAP`, `WIPE_TAIL`, `LINE_PX`, `BAR_K`, `BAR_N`.

Click the empty area around a popup to close it (same as Escape). A press that starts inside the popup and ends outside, like selecting text, does not close it.

</details>

<details>
<summary><b>Button text effect</b></summary>

<br>

Hovering a button scrambles its letters (45 ms steps, 600 ms, left to right, mixed characters). It lives in `ui/js/fx.js`.

</details>

---
 
## Try it, break it, tell me
 
Thanks for stopping by. Beyonder is a project I care about, and it gets better every time someone uses it on a PC that is different from mine. So please **give it a try**. It takes a minute to set up, and I hope it makes opening the right browser profile a little faster for you.
 
I'd love to hear from you:
 
- 🐞 **Found a bug or something odd?** Please [open an issue](../../issues) or simply. Tell me what you did, what you expected, and what happened instead. The last lines of `data/error.log` help a lot, and a screenshot is even better.
- 💡 **Want a feature or an improvement?** Suggest it in the [issues](../../issues) too. Small annoyances count as much as big ideas.
- 🌐 **Is your favorite browser missing or not behaving?** Tell me it's name. That is usually all I need to add support for it.
Every report, big or small, is welcome, and it genuinely helps shape what comes next. If Beyonder saves you some clicks, a ⭐ on the repo is a lovely way to say thanks.

## Find me
 
Come say hi, share what you're doing with Beyonder, or send me a message.

Email: [thenoirguy.me@gmail.com](https://mail.google.com/mail/?view=cm&fs=1&to=thenoirguy.me%40gmail.com)

Facebook: [The Noir Guy](https://www.facebook.com/profile.php?id=61596567771708)

Instagram: [@the_noir.guy](https://www.instagram.com/the_noir.guy/)

Twitter/X: [@the_noir_guy](https://x.com/the_noir_guy)

Discord: [The_Noir_Guy](https://discord.com/users/1569354601386479647)
 
## License
 
This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).
 
- Free for personal, hobby, research, and non-commercial use.
- Commercial use is **not allowed** without a separate license from the author.
