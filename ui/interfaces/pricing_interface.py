"""Pricing page: one card per rank, live dev-mode switch, feature matrix.

Everything on this page is derived from ``services.ranks`` — the same table the
converters and dialogs consult for entitlement checks — so the marketing copy
can never drift from what the app actually enforces.

The page is intentionally free of any purchase flow: choosing a rank simply
calls :meth:`RankManager.set_rank` (in a real build this would hand off to a
store front-end), while the Dev mode button asks for the developer password
and unlocks every capability when it matches.
"""

from PySide6.QtCore import Qt, QPropertyAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, CardWidget, FluentIcon, IconWidget, LineEdit,
    MessageBox, PrimaryPushButton, PushButton, StrongBodyLabel, TitleLabel,
    TransparentToggleToolButton, isDarkTheme,
)

import lang
from services.ranks import (
    FEATURES, RANKS, Rank, RankManager, required_rank,
)
from ui.widgets.badge import RankBadge


def _rgb(rank: Rank, alpha: int = 255) -> str:
    r, g, b = rank.color
    return f"rgba({r}, {g}, {b}, {alpha / 255:.3f})"


class _FeatureRow(QFrame):
    """One row of the 'what each rank gets' matrix."""

    def __init__(self, key: str, ranks, current_level: int, parent=None):
        super().__init__(parent)
        self.setObjectName("featureRow")
        level, name, description = FEATURES[key]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(StrongBodyLabel(lang.lang.get(name), self))
        hint = CaptionLabel(description, self)
        hint.setWordWrap(True)
        text.addWidget(hint)
        layout.addLayout(text, 1)

        for rank in ranks:
            unlocked = rank.level >= level
            mark = QLabel("✓" if unlocked else "—", self)
            mark.setAlignment(Qt.AlignCenter)
            mark.setMinimumWidth(64)
            mark.setStyleSheet(
                "color: {}; font-weight: 600;".format(
                    _rgb(rank) if unlocked
                    else ("#9aa0a6" if not isDarkTheme() else "#6c7076")))
            mark.setToolTip("{} · {}".format(
                lang.lang.get(name), required_rank(key).label))
            layout.addWidget(mark)


class PricingCard(CardWidget):
    """A single rank card: badge, price, bullets and an action button."""

    chosen = None  # set by the interface (callable)

    def __init__(self, rank: Rank, current: bool, recommended: bool,
                 parent=None):
        super().__init__(parent)
        self.rank = rank
        self.current = current
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(230)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._accent = QFrame(self)
        self._accent.setFixedHeight(4)
        self._accent.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 {_rgb(rank)}, stop:1 {_rgb(rank, 60)});"
            " border-top-left-radius: 7px; border-top-right-radius: 7px;")
        outer.addWidget(self._accent)

        body = QVBoxLayout()
        body.setContentsMargins(18, 16, 18, 18)
        body.setSpacing(8)
        outer.addLayout(body)

        head = QHBoxLayout()
        self.badge = RankBadge(rank, self, scale=1.1)
        head.addWidget(self.badge)
        head.addStretch(1)
        if recommended:
            tag = QLabel("★", self)
            tag.setStyleSheet("color: #e6b325; font-size: 15px;")
            tag.setToolTip(lang.lang.get("Most popular"))
            head.addWidget(tag)
        body.addLayout(head)

        title = rank.label
        body.addWidget(TitleLabel(lang.lang.get(title), self))
        body.addWidget(CaptionLabel(lang.lang.get(rank.tagline), self))

        price_row = QHBoxLayout()
        price_row.setSpacing(6)
        price = QLabel(rank.price, self)
        price_font = price.font()
        price_font.setPointSize(price_font.pointSize() + 10)
        price_font.setBold(True)
        price.setFont(price_font)
        price.setStyleSheet(f"color: {_rgb(rank)};")
        price_row.addWidget(price)
        period = CaptionLabel(rank.period, self)
        period.setAlignment(Qt.AlignBottom)
        price_row.addWidget(period)
        price_row.addStretch(1)
        body.addLayout(price_row)

        body.addSpacing(4)
        for feature in rank.features:
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel("●", self)
            dot.setStyleSheet(f"color: {_rgb(rank)}; font-size: 8px;")
            row.addWidget(dot, 0, Qt.AlignTop)
            label = BodyLabel(lang.lang.get(feature), self)
            label.setWordWrap(True)
            row.addWidget(label, 1)
            body.addLayout(row)

        body.addStretch(1)
        self.button = PrimaryPushButton(self) if not current else PushButton(self)
        self.button.setCursor(Qt.PointingHandCursor)
        self._apply_state(current)
        body.addWidget(self.button)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28 if recommended else 18)
        shadow.setColor(QColor(0, 0, 0, 60 if isDarkTheme() else 34))
        shadow.setOffsetY(6)
        self.setGraphicsEffect(shadow)

    def _apply_state(self, current: bool):
        self.current = current
        if current:
            self.button.setText(lang.lang.get("Current plan"))
            self.button.setEnabled(False)
        else:
            self.button.setText(lang.lang.get("Choose {}").format(self.rank.label))
            self.button.setEnabled(True)
        border = _rgb(self.rank) if current else (
            "rgba(130, 130, 130, 0.28)" if not isDarkTheme()
            else "rgba(255, 255, 255, 0.10)")
        self.setProperty("selected", current)
        self.setStyleSheet(
            f"PricingCard {{ border: {'2px' if current else '1px'} solid {border}; }}")

    def choose(self, callback):
        self.chosen = callback
        self.button.clicked.connect(lambda: self.chosen(self.rank))


class DevModeCard(CardWidget):
    """Password-gated master switch that unlocks every paid capability."""

    def __init__(self, manager: RankManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        icon = IconWidget(FluentIcon.DEVELOPER_TOOLS, self)
        icon.setFixedSize(22, 22)
        layout.addWidget(icon)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(StrongBodyLabel(lang.lang.get("Dev mode"), self))
        self.hint = CaptionLabel(
            lang.lang.get("Unlocks ALL features, every rank and max-effort tools."),
            self)
        text.addWidget(self.hint)
        layout.addLayout(text, 1)

        self.status = QLabel(self)
        layout.addWidget(self.status)

        self.password = LineEdit(self)
        self.password.setPlaceholderText(lang.lang.get("Developer password"))
        self.password.setEchoMode(LineEdit.Password)
        self.password.setFixedWidth(180)
        self.password.returnPressed.connect(self._try_enable)
        self.password.setVisible(False)
        layout.addWidget(self.password)

        self.button = PushButton(lang.lang.get("Enable dev mode"), self)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self._on_clicked)
        layout.addWidget(self.button)

        self.refresh()

    def _on_clicked(self):
        if self.manager.dev_mode:
            box = MessageBox(
                lang.lang.get("Disable dev mode?"),
                lang.lang.get(
                    "Locked features and rank-only options will be hidden again."),
                self.window())
            box.yesButton.setText(lang.lang.get("Disable"))
            box.cancelButton.setText(lang.lang.get("Keep"))
            if box.exec():
                self.manager.disable_dev_mode()
            return
        if self.password.isVisible():
            self._try_enable()
        else:
            self.password.setVisible(True)
            self.password.setFocus(Qt.OtherFocusReason)

    def _try_enable(self):
        password = self.password.text()
        self.password.clear()
        self.password.setVisible(False)
        if self.manager.try_enable_dev_mode(password):
            self.button.setText(lang.lang.get("Disable dev mode"))
            return
        box = MessageBox(
            lang.lang.get("Wrong password"),
            lang.lang.get("That password does not unlock dev mode."),
            self.window())
        box.yesButton.setText(lang.lang.get("Try again"))
        box.cancelButton.setText(lang.lang.get("Cancel"))
        if box.exec():
            self.password.setVisible(True)
            self.password.setFocus(Qt.OtherFocusReason)

    def refresh(self):
        enabled = self.manager.dev_mode
        self.status.setText(lang.lang.get("ON") if enabled else lang.lang.get("OFF"))
        self.status.setStyleSheet(
            "font-weight: 700; color: {};".format(
                "#2ecc71" if enabled else "#e74c3c"))
        self.button.setText(lang.lang.get("Disable dev mode") if enabled
                            else lang.lang.get("Enable dev mode"))
        if not enabled:
            self.password.setVisible(False)


class PricingInterface(QWidget):
    """Scrollable pricing page registered as a sub-interface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pricingInterface")
        self.manager = RankManager.instance()

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 30, 36, 30)
        root.setSpacing(18)

        header = QVBoxLayout()
        header.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.addWidget(TitleLabel(lang.lang.get("Pricing"), self))
        self.rank_badge = RankBadge(self.manager.rank, self)
        title_row.addWidget(self.rank_badge, 0, Qt.AlignVCenter)
        title_row.addStretch(1)
        header.addLayout(title_row)
        subtitle = BodyLabel(
            lang.lang.get("Pick the rank that fits your workflow — you can change "
                          "it at any time. Dev mode unlocks everything."), self)
        subtitle.setWordWrap(True)
        header.addWidget(subtitle)
        root.addLayout(header)

        self.dev_card = DevModeCard(self.manager, self)
        root.addWidget(self.dev_card)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        self.card_widgets = []
        recommended = "gold"
        for rank in RANKS:
            card = PricingCard(rank,
                               current=self._is_current(rank),
                               recommended=(rank.key == recommended),
                               parent=self)
            card.choose(self._choose_rank)
            cards.addWidget(card)
            self.card_widgets.append(card)
        root.addLayout(cards)

        matrix_head = QHBoxLayout()
        matrix_head.addWidget(StrongBodyLabel(
            lang.lang.get("Feature availability"), self))
        matrix_head.addStretch(1)
        root.addLayout(matrix_head)

        matrix = CardWidget(self)
        matrix_layout = QVBoxLayout(matrix)
        matrix_layout.setContentsMargins(6, 6, 6, 6)
        matrix_layout.setSpacing(0)
        head = QFrame(matrix)
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(12, 8, 12, 4)
        head_layout.setSpacing(8)
        head_layout.addWidget(StrongBodyLabel("", head))
        head_layout.addStretch(1)
        for rank in RANKS:
            label = QLabel(rank.badge.split(" ")[0], head)
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumWidth(64)
            label.setStyleSheet(
                f"color: {_rgb(rank)}; font-weight: 700; font-size: 11px;")
            head_layout.addWidget(label)
        matrix_layout.addWidget(head)
        for key in FEATURES:
            matrix_layout.addWidget(_FeatureRow(key, RANKS,
                                                self.manager.rank.level, matrix))
        root.addWidget(matrix)
        root.addStretch(1)

        self.manager.changed.connect(self.refresh)

    # ------------------------------------------------------------------ logic --
    def _is_current(self, rank: Rank) -> bool:
        return (not self.manager.dev_mode
                and self.manager.rank_key == rank.key)

    def _choose_rank(self, rank: Rank):
        self.manager.set_rank(rank.key)

    def refresh(self):
        self.rank_badge.set_rank(Rank(self.manager.rank.key,
                                      self.manager.rank.label + (" · DEV" if
                                      self.manager.dev_mode else ""),
                                      self.manager.rank.badge + (" · DEV" if
                                      self.manager.dev_mode else ""),
                                      self.manager.rank.color,
                                      self.manager.rank.level,
                                      self.manager.rank.price,
                                      self.manager.rank.period,
                                      self.manager.rank.tagline,
                                      self.manager.rank.features)
                                 if self.manager.dev_mode else self.manager.rank)
        for card in self.card_widgets:
            card._apply_state(self._is_current(card.rank))
        self.dev_card.refresh()

    def retranslate(self):
        pass  # rebuilt lazily; labels refresh on next full retranslate pass
