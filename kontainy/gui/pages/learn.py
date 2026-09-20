"""
kontainy — Learn page

Ported from VenvStudio's ``learn_page.py`` layout:

* a 230px left navigation frame, one checkable button per category, tinted
  with the category colour and a 3px left bar when active;
* a QStackedWidget of QScrollAreas on the right, **built lazily** — one panel
  per category, filled on first visit. VenvStudio measured 4.6 seconds of
  startup building all categories up front; the reader only ever looks at one;
* collapsible ``TopicCard`` frames rather than a tree plus a text browser.

Educational text is large on purpose: the palette's ``fs_learn``
(font_size + 5, minimum 18px) is the floor and is never reduced.
"""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ...learn.content import LEARN_CATEGORIES, learn_stats
from ..syntax_highlighter import highlighter_for
from .base import Page


def _esc(text) -> str:
    return html.escape(str(text))


def _md_to_html(text: str, c: dict) -> str:
    """Inline markdown: `code`, **bold**, *italic*, bullets."""
    out = []
    for para in str(text).split("\n\n"):
        lines = []
        for line in para.split("\n"):
            line = _esc(line)
            line = re.sub(
                r"`([^`]+)`",
                f"<code style='background:{c['input_bg']};color:{c['accent']};"
                "padding:1px 5px;border-radius:4px'>\\1</code>", line)
            line = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", line)
            line = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", line)
            if line.startswith("• ") or line.startswith("- "):
                line = "&nbsp;&nbsp;•&nbsp; " + line[2:]
            lines.append(line)
        out.append("<p style='margin:0 0 10px 0'>" + "<br>".join(lines) + "</p>")
    return "".join(out)


class TopicCard(QFrame):
    """One collapsible topic. Click the header to expand."""

    setting_requested = Signal(str)

    def __init__(self, topic: dict, colors: dict, parent=None):
        super().__init__(parent)
        self._topic = topic
        self._c = colors
        self._expanded = False
        self._highlighter = None
        self._setup()

    # --- construction ------------------------------------------------------
    def _setup(self):
        c = self._c
        self.setObjectName("topicCard")
        self.setStyleSheet(f"""
            QFrame#topicCard {{
                background: {c['card']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
            QFrame#topicCard:hover {{
                border: 1px solid {c['accent']}77;
            }}
        """)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setStyleSheet("background: transparent; border: none;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 14, 18, 14)

        title = QLabel(self._topic["title"])
        title.setStyleSheet(
            f"color: {c['fg']}; font-size: 17px; font-weight: bold;"
            " border: none; letter-spacing: 0.3px;")
        title.setWordWrap(True)
        hl.addWidget(title, 1)

        self._arrow = QLabel("\u203a")
        self._arrow.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: 26px; border: none;"
            " padding-left: 10px;")
        hl.addWidget(self._arrow)
        layout.addWidget(header)

        self._body_widget = QWidget()
        self._body_widget.setVisible(False)
        self._body_widget.setStyleSheet("background: transparent; border: none;")
        bl = QVBoxLayout(self._body_widget)
        bl.setContentsMargins(18, 4, 18, 18)
        bl.setSpacing(14)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(
            f"background: {c['border']}; max-height: 1px; border: none;")
        bl.addWidget(sep)

        self._add_body(bl)
        self._add_diagram(bl)
        self._add_table(bl)
        self._add_snippet(bl)
        self._add_info_boxes(bl)
        self._add_footer(bl)

        layout.addWidget(self._body_widget)

    def _add_body(self, bl):
        if not self._topic.get("body"):
            return
        c = self._c
        label = QLabel(_md_to_html(self._topic["body"], c))
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        label.setStyleSheet(
            f"color: {c['fg']}; font-size: {c['fs_learn']}px;"
            " border: none; line-height: 160%;")
        bl.addWidget(label)

    def _add_diagram(self, bl):
        if not self._topic.get("diagram"):
            return
        c = self._c
        label = QLabel(self._topic["diagram"])
        label.setStyleSheet(
            f"background: {c['input_bg']}; color: {c['fg']};"
            f" font-family: monospace; font-size: {c['fs_base'] + 1}px;"
            " padding: 14px; border-radius: 8px; border: none;"
            " line-height: 140%;")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(label)

    def _add_table(self, bl):
        table = self._topic.get("table")
        if not table:
            return
        c = self._c
        frame = QFrame()
        frame.setStyleSheet(
            f"background: {c['input_bg']}; border-radius: 8px; border: none;")
        tl = QVBoxLayout(frame)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)

        head = QFrame()
        head.setStyleSheet(
            f"background: transparent; border-bottom: 2px solid {c['border']};")
        hdl = QHBoxLayout(head)
        hdl.setContentsMargins(14, 10, 14, 10)
        for column in table["headers"]:
            label = QLabel(_md_to_html(column, c))
            label.setTextFormat(Qt.RichText)
            label.setStyleSheet(
                f"color: {c['fg_muted']}; font-weight: bold;"
                f" font-size: {c['fs_base'] + 1}px; border: none;")
            hdl.addWidget(label, 1)
        tl.addWidget(head)

        for row in table["rows"]:
            line = QFrame()
            line.setStyleSheet(
                "background: transparent;"
                f" border-bottom: 1px solid {c['border']};")
            rl = QHBoxLayout(line)
            rl.setContentsMargins(14, 9, 14, 9)
            for cell in row:
                label = QLabel(_md_to_html(cell, c))
                label.setTextFormat(Qt.RichText)
                label.setWordWrap(True)
                label.setStyleSheet(
                    f"color: {c['fg']}; font-size: {c['fs_base'] + 1}px;"
                    " border: none;")
                rl.addWidget(label, 1)
            tl.addWidget(line)
        bl.addWidget(frame)

    def _add_snippet(self, bl):
        snippet = self._topic.get("snippet")
        if not snippet:
            return
        c = self._c
        language = self._topic.get("language", "bash")

        frame = QFrame()
        frame.setStyleSheet(
            f"background: {c['input_bg']}; border-radius: 8px; border: none;")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)

        head = QFrame()
        head.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {c['border']};")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 7, 10, 7)
        lang = QLabel(language)
        lang.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_small']}px;"
            " font-weight: bold; border: none;")
        hl.addWidget(lang, 1)

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("secondary")
        copy_btn.setFixedWidth(80)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._copy_snippet)
        hl.addWidget(copy_btn)
        fl.addWidget(head)

        edit = QTextEdit()
        edit.setPlainText(snippet)
        edit.setReadOnly(True)
        # NOTE: every segment must be an f-string. A plain "}}" in a
        # non-f segment stays as two braces and Qt silently refuses the whole
        # stylesheet with "Could not parse stylesheet of object QTextEdit".
        edit.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: {c['fg']};"
            f" font-family: monospace; font-size: {c['fs_base'] + 2}px;"
            f" border: none; padding: 12px; }}")
        edit.setFixedHeight(min(28 + (snippet.count("\n") + 1) * 21, 470))
        self._highlighter = highlighter_for(language, edit.document())
        fl.addWidget(edit)
        bl.addWidget(frame)

    def _add_info_boxes(self, bl):
        c = self._c
        for key, icon, label, color in (
            ("tip", "\U0001f4a1", "Tip", c["success"]),
            ("note", "\u2139", "Note", c["accent"]),
            ("warning", "\u26a0", "Watch out", c["warning"]),
        ):
            if not self._topic.get(key):
                continue
            frame = QFrame()
            frame.setStyleSheet(
                f"background: {color}1a; border-left: 4px solid {color};"
                " border-radius: 6px;")
            il = QVBoxLayout(frame)
            il.setContentsMargins(14, 11, 14, 11)
            il.setSpacing(4)
            head = QLabel(f"{icon}  {label}")
            head.setStyleSheet(
                f"color: {color}; font-weight: bold;"
                f" font-size: {c['fs_base'] + 1}px; border: none;")
            il.addWidget(head)
            text = QLabel(_md_to_html(self._topic[key], c))
            text.setWordWrap(True)
            text.setTextFormat(Qt.RichText)
            text.setStyleSheet(
                f"color: {c['fg']}; font-size: {c['fs_learn'] - 1}px;"
                " border: none; line-height: 155%;")
            il.addWidget(text)
            bl.addWidget(frame)

    def _add_footer(self, bl):
        c = self._c
        topic = self._topic
        if not (topic.get("links") or topic.get("setting_key")
                or topic.get("rule_id")):
            return
        holder = QWidget()
        holder.setStyleSheet("background: transparent; border: none;")
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        if topic.get("setting_key"):
            btn = QPushButton(f"\u2699  Open setting: {topic['setting_key']}")
            btn.setObjectName("secondary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda: self.setting_requested.emit(topic["setting_key"]))
            row.addWidget(btn)

        if topic.get("rule_id"):
            label = QLabel(f"Diagnostic rule: {topic['rule_id']}")
            label.setStyleSheet(
                f"color: {c['fg_muted']}; font-size: {c['fs_small']}px;"
                " border: none;")
            row.addWidget(label)

        for text, url in topic.get("links", []):
            link = QPushButton(f"\U0001f517  {text}")
            link.setObjectName("secondary")
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(lambda _=False, u=url: self._open_url(u))
            row.addWidget(link)

        row.addStretch()
        bl.addWidget(holder)

    # --- behaviour ---------------------------------------------------------
    def _copy_snippet(self):
        QGuiApplication.clipboard().setText(self._topic.get("snippet", ""))

    def _open_url(self, url: str):
        QDesktopServices.openUrl(QUrl(url))

    def mousePressEvent(self, event):
        self._toggle()
        super().mousePressEvent(event)

    def _toggle(self):
        self._expanded = not self._expanded
        self._body_widget.setVisible(self._expanded)
        self._arrow.setText("\u2304" if self._expanded else "\u203a")

    def expand(self):
        if not self._expanded:
            self._toggle()


class CategoryPanel(QWidget):
    """Header plus every TopicCard of one category."""

    setting_requested = Signal(str)

    def __init__(self, category: dict, colors: dict, parent=None):
        super().__init__(parent)
        self._cat = category
        self._c = colors
        self.cards = []
        self._setup()

    def _setup(self):
        c = self._c
        cat = self._cat
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 26)
        layout.setSpacing(12)

        head = QWidget()
        head.setStyleSheet("background: transparent; border: none;")
        hl = QVBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 6)
        hl.setSpacing(4)

        top = QWidget()
        top.setStyleSheet("background: transparent;")
        row = QHBoxLayout(top)
        row.setContentsMargins(0, 0, 0, 0)
        icon = QLabel(cat["icon"])
        icon.setStyleSheet("font-size: 26px; border: none;")
        row.addWidget(icon)
        title = QLabel(cat["title"])
        title.setStyleSheet(
            f"color: {cat['color']}; font-size: {c['fs_header']}px;"
            " font-weight: bold; border: none;")
        row.addWidget(title)
        count = QLabel(f"{len(cat['topics'])} / {cat['target']} topics")
        count.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_small']}px;"
            " border: none; padding-left: 8px;")
        row.addWidget(count)
        row.addStretch()
        hl.addWidget(top)

        desc = QLabel(cat.get("desc", ""))
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_base'] + 1}px;"
            " border: none;")
        hl.addWidget(desc)
        layout.addWidget(head)

        if not cat["topics"]:
            empty = QLabel(
                "Content for this category is planned but not written yet.\n"
                "Nothing is ever removed from Learn — only added.")
            empty.setWordWrap(True)
            empty.setStyleSheet(
                f"color: {c['fg_muted']}; font-size: {c['fs_base'] + 2}px;"
                f" background: {c['card']}; border: 1px dashed {c['border']};"
                " border-radius: 10px; padding: 26px;")
            layout.addWidget(empty)

        for topic in cat["topics"]:
            card = TopicCard(topic, c)
            card.setting_requested.connect(self.setting_requested)
            layout.addWidget(card)
            self.cards.append(card)

        layout.addStretch()


class LearnPage(Page):
    NAME = "learn"
    TITLE = "Learn"
    ICON = "\U0001f4da"
    SUBTITLE = ("Containers, Docker, Podman, Kubernetes, systemd, KVM and LXC "
                "— from first principles to troubleshooting.")

    open_setting = Signal(str)

    def build(self) -> None:
        self._panels = {}
        self._built = []

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search topics\u2026")
        self.search.returnPressed.connect(self._search)
        self.toolbar.addWidget(self.search, 1)
        self.add_tool_button("Search", self._search, kind="primary")
        st = learn_stats()
        self.progress = QLabel(
            f"{st['kategori']} categories \u00b7 "
            f"{st['yazilan']}/{st['hedef']} topics")
        self.toolbar.addWidget(self.progress)

        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        self.nav_frame = QFrame()
        self.nav_frame.setFixedWidth(230)
        nav_layout = QVBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(10, 16, 10, 16)
        nav_layout.setSpacing(4)

        self.nav_title = QLabel("  \U0001f4da Learn")
        nav_layout.addWidget(self.nav_title)
        self.nav_subtitle = QLabel("  Containers, end to end")
        nav_layout.addWidget(self.nav_subtitle)

        self._nav_buttons = []
        self._stack = QStackedWidget()

        for index, cat in enumerate(LEARN_CATEGORIES):
            button = QPushButton(f"  {cat['icon']}   {cat['title']}")
            button.setCheckable(True)
            button.setFixedHeight(42)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self._switch_cat(i))
            nav_layout.addWidget(button)
            self._nav_buttons.append(button)

            # Lazy: an empty scroll area now, the real panel on first visit.
            panel = QScrollArea()
            panel.setWidgetResizable(True)
            panel.setStyleSheet(
                "QScrollArea { border: none; background: transparent; }")
            self._stack.addWidget(panel)
            self._built.append(False)

        nav_layout.addStretch()
        main.addWidget(self.nav_frame)
        main.addWidget(self._stack, 1)
        self.body.addLayout(main, 1)

        self.apply_theme()
        self._switch_cat(0)

    # --- theme -------------------------------------------------------------
    def apply_theme(self) -> None:
        super().apply_theme()
        c = self.colors()
        self.nav_frame.setStyleSheet(
            f"QFrame {{ background: {c['card']};"
            f" border-right: 1px solid {c['border']}; }}")
        self.nav_title.setStyleSheet(
            f"color: {c['fg']}; font-size: 20px; font-weight: bold;"
            " padding: 4px 0 6px 0; border: none;")
        self.nav_subtitle.setStyleSheet(
            f"color: {c['fg_muted']}; font-size: {c['fs_small'] + 1}px;"
            " padding: 0 0 14px 0; border: none;")
        for button, cat in zip(self._nav_buttons, LEARN_CATEGORIES):
            button.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {c['fg_muted']};
                    border: none;
                    border-radius: 8px;
                    text-align: left;
                    font-size: {c['fs_base'] + 2}px;
                    font-weight: bold;
                    padding: 0 10px;
                }}
                QPushButton:hover {{
                    background: {c['accent']}22;
                    color: {c['fg']};
                }}
                QPushButton:checked {{
                    background: {c['accent']}33;
                    color: {cat['color']};
                    border-left: 3px solid {cat['color']};
                    padding-left: 7px;
                }}
            """)

        # Card colours are baked in at build time, so a theme switch has to
        # rebuild them — the same lesson VenvStudio hit in B115.
        current = self._stack.currentIndex() if self._built else -1
        self._built = [False] * len(self._built)
        self._panels.clear()
        if current >= 0:
            self._build_category(current)

    # --- navigation --------------------------------------------------------
    def _build_category(self, index: int) -> None:
        if self._built[index]:
            return
        panel = CategoryPanel(LEARN_CATEGORIES[index], self.colors())
        panel.setting_requested.connect(self.open_setting)
        self._stack.widget(index).setWidget(panel)
        self._panels[index] = panel
        self._built[index] = True

    def _switch_cat(self, index: int) -> None:
        self._build_category(index)
        self._stack.setCurrentIndex(index)
        for i, button in enumerate(self._nav_buttons):
            button.setChecked(i == index)

    def _search(self) -> None:
        needle = self.search.text().strip().casefold()
        if not needle:
            return
        for index, cat in enumerate(LEARN_CATEGORIES):
            for position, topic in enumerate(cat["topics"]):
                blob = " ".join(str(topic.get(k, "")) for k in
                                ("title", "body", "snippet", "tip",
                                 "note", "warning")).casefold()
                if needle in blob:
                    self._switch_cat(index)
                    panel = self._panels.get(index)
                    if panel and position < len(panel.cards):
                        panel.cards[position].expand()
                    self.status.emit(
                        f"Found in {cat['title']}: {topic['title']}")
                    return
        self.status.emit(f"No topic matches \u201c{self.search.text().strip()}\u201d")
