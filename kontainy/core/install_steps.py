"""
kontainy — what an install is doing while it does it

An install that prints nothing for two minutes teaches nothing and looks
broken. Every package manager announces its stages in its own words; this
turns those words into the same few steps, each with a line saying what the
step really is — so waiting for `apt install docker.io` is a chance to learn
what apt does, not a blank screen.

Qt-free on purpose: the dialog shows it, and the command line can too.
"""

from __future__ import annotations

import re

#: (key, label, what it means). The order is the order they happen in.
GENERIC = [
    ("resolve", "Working out what is needed",
     "The manager reads its index of available packages and follows the "
     "dependencies of the one you asked for."),
    ("download", "Downloading",
     "Packages are fetched from the mirrors. This is the part that takes "
     "the time on a slow link; nothing has changed on your system yet."),
    ("install", "Installing",
     "Files are unpacked into place. Until this point the install could be "
     "cancelled without a trace."),
    ("configure", "Setting up",
     "Post-install scripts run: users and groups are created, services are "
     "registered, caches are rebuilt."),
]

DOCKER_PULL = [
    ("resolve", "Finding the image",
     "The registry is asked for the manifest — which layers this tag is "
     "made of, for your architecture."),
    ("download", "Downloading layers",
     "Each layer is fetched once and shared; a layer you already have is "
     "skipped, which is why the second pull is so much faster."),
    ("install", "Extracting layers",
     "Layers are unpacked into the image store, stacked in order."),
    ("configure", "Finishing",
     "The digest is verified and the tag now points at the image."),
]

WINDOWS_FEATURE = [
    ("resolve", "Checking the feature",
     "Windows looks up the optional feature and what it depends on."),
    ("download", "Fetching files",
     "Missing component files are taken from the local store or Windows "
     "Update."),
    ("install", "Enabling",
     "The feature's files are staged and the registry is updated."),
    ("configure", "Restart pending",
     "Most Windows features only finish after a restart; kontainy will "
     "still report them as missing until then."),
]

#: What each manager prints when it enters a stage.
PATTERNS = [
    # apt
    (r"reading package lists|building dependency tree|reading state", "resolve"),
    (r"^get:\d|^fetched |^hit:\d|^ign:\d", "download"),
    (r"preparing to unpack|^unpacking |selecting previously", "install"),
    (r"^setting up |processing triggers", "configure"),
    # dnf and zypper
    (r"dependencies resolved|resolving package dependencies|metadata cache",
     "resolve"),
    (r"downloading packages|retrieving package", "download"),
    (r"running transaction|^installing +:|^ *installing: ", "install"),
    (r"^installed:|^verifying +:|running post", "configure"),
    # pacman
    (r"resolving dependencies|looking for conflicting", "resolve"),
    (r"^:: retrieving packages|downloading ", "download"),
    # pacman verifies AFTER downloading, as part of the transaction that
    # installs. Calling it "resolve" sent the stages backwards.
    (r"checking keys|checking package integrity|loading package files|"
     r"checking available disk space", "install"),
    (r"^installing |^upgrading |^reinstalling ", "install"),
    (r"^:: running post-transaction|^optional dependencies", "configure"),
    # apk
    (r"^fetch https?://", "download"),
    (r"^\(\d+/\d+\) installing", "install"),
    (r"executing .*\.post-install|^ok: \d+ mib", "configure"),
    # winget and windows features
    (r"found .* \[.*\]|deployment image servicing", "resolve"),
    (r"^ *\d+%|downloading https?://|% complete", "download"),
    (r"starting package install|the operation completed", "install"),
    (r"successfully installed|restart needed|restart windows", "configure"),
    # docker / podman pull
    (r"pulling from |trying to pull", "resolve"),
    (r"downloading|download complete", "download"),
    (r"extracting|copying blob|writing manifest", "install"),
    (r"pull complete|digest: sha256|status: downloaded", "configure"),
    # wsl
    (r"downloading: ", "download"),
    (r"installing: |installing, this may take", "install"),
    (r"the requested operation is successful", "configure"),
]

COMPILED = [(re.compile(pattern, re.I), key) for pattern, key in PATTERNS]


def steps_for(command: str) -> list:
    """The stages to show for this command."""
    text = (command or "").lower()
    if " pull " in f" {text} ":
        return list(DOCKER_PULL)
    if "windowsoptionalfeature" in text or "dism" in text:
        return list(WINDOWS_FEATURE)
    return list(GENERIC)


def stage_of(line: str) -> str:
    """Which stage a line of output belongs to, or "" if it says nothing."""
    text = (line or "").strip()
    if not text:
        return ""
    for pattern, key in COMPILED:
        if pattern.search(text):
            return key
    return ""


def percent_of(line: str) -> int:
    """A percentage the tool reported itself, or -1.

    Only trusted when the tool prints one: guessing a percentage from the
    number of lines would be a progress bar that lies.
    """
    match = re.search(r"(\d{1,3})(?:\.\d+)?\s*%", line or "")
    if not match:
        return -1
    value = int(match.group(1))
    return value if 0 <= value <= 100 else -1
