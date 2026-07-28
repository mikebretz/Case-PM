Case PM Desktop Connector (v2.0)
================================

Click **Add Case PM to Desktop** on the login page.

1. OK on the login popup
2. Windows opens **Case PM Desktop.hta** (click Open if asked)
3. OK on the Windows prompt — installs to:
   Documents\Case PM Desktop\
4. Desktop shortcut **Case PM** is created

This connector opens Case PM in your web browser and points at a server URL.

For a full local app in its own window (no browser tab), use **RUN-DESKTOP.bat**
(Windows) or **RUN-DESKTOP.sh** (macOS/Linux) in the project root instead.

Icon: static/img/casepm-desktop-icon.ico

Regenerate: python scripts/generate_casepm_icon.py
