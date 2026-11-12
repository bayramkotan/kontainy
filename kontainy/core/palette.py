"""
kontainy — one box that reaches everything

kontainy has 19 pages, 152 settings, 19 diagnostic rules and 204 Learn
topics, and until now every one of them was reachable only by clicking
through the sidebar and then hunting inside the page. That is the whole of
"it feels basic": the content is there and the way in is not.

This builds the index that Ctrl+K searches. It is Qt-free so the ranking can
be tested without a display, and so the command line can use the same
matcher later.

Three rules it follows:

* **Opening the palette never runs a command.** Containers, images and
  volumes are folded in from whatever the pages already loaded, never by
  shelling out. A box that takes two seconds to appear is a box nobody
  opens, and a box that starts talking to engines when you press a key is
  worse than that.
* **Matching is by subsequence, not substring.** The catalogue is full of
  names like `default-address-pools` and `short-name-mode`; people type
  "dap" and "snm". A substring search answers nothing for either, which is
  how a search box teaches people it is useless.
* **Every entry says what it is and where it goes.** A result list mixing
  pages, settings and topics with no label is a guessing game — so each row
  carries its kind and its home.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Typed prefixes, the way editors do it. Narrowing by hand beats scrolling.
SCOPES = {
    ">": "action",
    "#": "setting",
    "?": "topic",
    "@": "object",
    "/": "page",
}

#: What each kind is called in the list, and how much it is favoured when
#: the query is short. A two-letter query almost always means a page.
KINDS = {
    "page": ("Page", 30),
    "action": ("Action", 25),
    "object": ("", 18),
    "setting": ("Setting", 10),
    "topic": ("Learn", 6),
}


#: What people type when they mean a page, which is rarely its title.
#: "k8s" matched nothing at all before this — there is no 8 in Kubernetes —
#: and a search box that cannot find Kubernetes from "k8s" is one people
#: stop trying. Keyed by a fragment of the page's internal name.
ALIASES = {
    "overview": "home start dashboard what is installed",
    "diagnostics": "doctor check problems warnings health",
    "docker": "docker dockerd daemon context compose",
    "podman": "podman quadlet rootless connection",
    "kubernetes": "k8s kube kubectl cluster pod node kubeconfig",
    "libvirt": "kvm qemu virsh vm virtual machine domain",
    "hyperv": "hyper-v vm virtual machine windows",
    "vmware": "vmrun workstation player vmx vm",
    "incus": "lxc lxd system container",
    "lxd": "lxc incus system container",
    "containers": "ps running stopped exited start stop restart",
    "machines": "vm virtual machine guest",
    "images": "image registry pull push tag layer prune",
    "volumes": "volume data mount bind storage prune backup",
    "catalog": "settings config daemon.json containers.conf storage.conf "
               "registries.conf option flag",
    "app-settings": "docker desktop wslconfig virtualbox vmware preferences",
    "install": "install uninstall setup remove add engine",
    "preferences": "theme font appearance terminal options",
    "learn": "docs help tutorial guide teach explain topics",
    "log": "logs journal output history",
}


def aliases_for(name: str) -> str:
    """Extra words for a page, matched loosely against its internal name."""
    found = [words for key, words in ALIASES.items() if key in name]
    return " ".join(found)


@dataclass
class Entry:
    """One thing the palette can take you to."""

    kind: str
    label: str
    detail: str = ""
    hint: str = ""
    keywords: str = ""
    payload: dict = field(default_factory=dict)

    @property
    def haystack(self) -> str:
        return f"{self.label} {self.keywords}".casefold()


# --- matching --------------------------------------------------------------------
def score(query: str, entry: Entry) -> int:
    """How well this entry answers the query, or 0 for not at all.

    Subsequence matching with the bonuses that make a palette feel like it
    read your mind rather than your keystrokes: a run of adjacent letters
    counts for more than scattered ones, a letter that starts a word counts
    for more than one in the middle, and matching early in the name counts
    for more than matching at the end.
    """
    needle = query.casefold().strip()
    if not needle:
        return KINDS.get(entry.kind, ("", 0))[1] + 1
    hay = entry.haystack
    label = entry.label.casefold()

    # An exact or leading match is never beaten by a clever fuzzy one.
    if label == needle:
        return 1000
    if label.startswith(needle):
        return 900 - min(len(label), 100)
    if needle in label:
        return 700 - label.index(needle)

    # The whole word, somewhere in the keywords. Typing "doctor" used to
    # land on the Docker page — "doctor" is a whole word in the Diagnostics
    # page's keywords, but only the label was checked for a substring, so
    # that exact hit was scored as a scattered fuzzy match and lost to
    # letters picked out of the word "context".
    # Only at a word boundary. A match buried inside a word is weak
    # evidence, and a Learn topic carries 400 characters of body in its
    # keywords, so "dap" would find "adapter" and outrank the setting whose
    # initials it actually is. Those fall through to the fuzzy scorer,
    # where their position costs them.
    found = hay.find(needle)
    if found >= 0 and (found == 0 or hay[found - 1] in " -_./:"):
        return 600 - min(found, 200)

    position, run, total = 0, 0, 0
    for char in needle:
        found = hay.find(char, position)
        if found < 0:
            return 0
        if found == position and position:
            run += 1
            total += 4 + run          # adjacent letters are the strong signal
        else:
            run = 0
            total += 1
        if found == 0 or (found and hay[found - 1] in " -_./:"):
            total += 6                # the start of a word
        position = found + 1
    total += max(0, 20 - position)    # matched early rather than trailing off
    return max(1, total)


def rank(query: str, entries: list, limit: int = 40) -> list:
    """The best entries for a query, most useful first.

    A leading scope character narrows to one kind before anything is
    scored, so `#storage` cannot drown in Learn topics about storage.
    """
    kind = None
    if query[:1] in SCOPES:
        kind = SCOPES[query[0]]
        query = query[1:]
    pool = [e for e in entries if kind is None or e.kind == kind]

    scored = []
    for entry in pool:
        value = score(query, entry)
        if not value:
            continue
        # ⚠️ The kind bonus breaks ties between comparable matches; it must
        # never promote a weak one over a strong one. Added flat, it did:
        # "snm" put the KVM page above "Short name mode", because a few of
        # those letters are scattered through the page's subtitle and a
        # page outweighs a setting by 20. Capped against the match itself,
        # a weak match can no longer buy its way up on kind alone.
        weight = KINDS.get(entry.kind, ("", 0))[1]
        scored.append((value + min(weight, max(1, value // 3)), entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1].label.casefold()))
    return [entry for _, entry in scored[:limit]]


# --- building the index ----------------------------------------------------------
def page_entries(pages: dict) -> list:
    """Every page, by its own title and subtitle.

    The subtitle goes into the keywords because that is where the words
    people actually search for live: "Images" is findable, but so should
    "unused" and "registry" be.
    """
    out = []
    for name, page in pages.items():
        title = getattr(page, "TITLE", name)
        out.append(Entry(
            kind="page", label=title,
            detail=getattr(page, "SUBTITLE", "")[:110],
            hint="Page",
            keywords=f"{name} {aliases_for(name)} "
                     f"{getattr(page, 'SUBTITLE', '')}",
            payload={"page": name}))
    return out


def setting_entries() -> list:
    """The catalogue: 152 settings, each one reachable by its own key."""
    from .catalog import ALL_SETTINGS
    out = []
    for item in ALL_SETTINGS:
        hint = f"Setting · {item.engine}"
        if item.danger >= 2:
            hint += " · ⚠"
        out.append(Entry(
            kind="setting", label=item.title,
            detail=f"{item.key} — {item.desc[:90]}",
            hint=hint,
            keywords=f"{item.key} {item.file} {item.surface} "
                     f"{item.cli or ''} {' '.join(item.tags or [])}",
            payload={"setting": item.key}))
    return out


def topic_entries() -> list:
    """All 204 Learn topics, each landing on the card itself."""
    from ..learn.content import LEARN_CATEGORIES
    out = []
    for cat_index, cat in enumerate(LEARN_CATEGORIES):
        for position, topic in enumerate(cat["topics"]):
            out.append(Entry(
                kind="topic", label=str(topic.get("title", "")),
                detail=str(topic.get("body", ""))[:110].replace("\n", " "),
                hint=f"Learn · {cat['title']}",
                keywords=f"{cat['title']} {cat['id']} "
                         f"{str(topic.get('body', ''))[:400]}",
                payload={"topic": [cat_index, position]}))
    return out


def object_entries(pages: dict) -> list:
    """Containers, images and volumes — but ONLY ones already in hand.

    ⚠️ This never runs a command. The unified pages keep their last listing
    in `rows`, so folding those in costs nothing; asking the engines here
    would make Ctrl+K pause for seconds on a machine with a slow socket,
    and a palette that pauses is a palette nobody uses twice.
    """
    nouns = {"containers": ("Container", "name"),
             "machines": ("Machine", "name"),
             "images": ("Image", "reference"),
             "volumes": ("Volume", "name")}
    out = []
    for page_name, (noun, key) in nouns.items():
        page = pages.get(page_name)
        for row in getattr(page, "rows", None) or []:
            label = str(row.get(key) or row.get("name") or "")
            if not label:
                continue
            where = f"{row.get('engine', '')} · {row.get('target', '')}"
            state = str(row.get("state") or row.get("status") or "")
            out.append(Entry(
                kind="object", label=label,
                detail=f"{where}{' · ' + state if state else ''}",
                hint=noun,
                keywords=f"{noun} {where} {state} "
                         f"{row.get('image', '')} {row.get('id', '')}",
                payload={"page": page_name, "select": label}))
    return out


def action_entries(actions: list) -> list:
    """The menu bar, flattened. Everything in it is a verb worth typing."""
    out = []
    for label, where, callback in actions:
        out.append(Entry(
            kind="action", label=label, detail=where, hint="Action",
            keywords=where, payload={"call": callback}))
    return out


def build(pages: dict, actions: list = None) -> list:
    """The whole index, in the order the kinds are usually wanted."""
    return (page_entries(pages)
            + action_entries(actions or [])
            + object_entries(pages)
            + setting_entries()
            + topic_entries())


__all__ = ["Entry", "KINDS", "SCOPES", "ALIASES", "aliases_for",
           "score", "rank", "build",
           "page_entries", "setting_entries", "topic_entries",
           "object_entries", "action_entries"]
