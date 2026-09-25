"""Rank system: what each tier unlocks, and how the app enforces it.

Four tiers — Normal (free), Bronze, Silver (VIP) and Gold (SVIP) — gate a
handful of capabilities. Everything is derived from a single ordered table so
the pricing page, the options dialog and the converters can never disagree
about who is allowed to do what.

``dev_mode`` is the escape hatch: when enabled every capability check passes,
which makes the whole feature surface testable without buying anything.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QSettings, Signal

DEV_PASSWORD = "abc1234"


@dataclass(frozen=True)
class Rank:
    key: str
    label: str          # display name, e.g. "Silver (VIP)"
    badge: str          # short text painted on the badge, e.g. "SILVER · VIP"
    color: Tuple[int, int, int]
    level: int
    price: str
    period: str
    tagline: str
    features: Tuple[str, ...]   # marketing bullets for the pricing card


RANKS: List[Rank] = [
    Rank(
        key="normal",
        label="Normal",
        badge="NORMAL",
        color=(0x8a, 0x8f, 0x98),           # grey
        level=0,
        price="$0",
        period="forever",
        tagline="Everything you need to convert everyday files.",
        features=(
            "Image, video & audio conversion",
            "Batch queue with per-file targets",
            "Estimated output size with confidence rating",
            "Trim, presets and thread control",
        ),
    ),
    Rank(
        key="bronze",
        label="Bronze",
        badge="BRONZE",
        color=(0xcd, 0x7f, 0x32),           # bronze
        level=1,
        price="$4.99",
        period="one time",
        tagline="Hardware speed and document formats.",
        features=(
            "Everything in Normal",
            "GPU Accelerated encoding (NVENC / Quick Sync / AMF)",
            "PDF converting support",
            "Office & Archives converting support",
            "Priority conversion queue",
        ),
    ),
    Rank(
        key="silver",
        label="Silver (VIP)",
        badge="SILVER · VIP",
        color=(0xb6, 0xc2, 0xcc),           # silver
        level=2,
        price="$9.99",
        period="per year",
        tagline="Full control over every file in the batch.",
        features=(
            "Everything in Bronze",
            "Per-File Customizations (unlimited overrides)",
            "Advanced codec, filter and container options",
            "Parallel batches up to 8 jobs",
            "VIP badge on your queue",
        ),
    ),
    Rank(
        key="gold",
        label="Gold (SVIP)",
        badge="GOLD · SVIP",
        color=(0xe6, 0xb3, 0x25),           # gold
        level=3,
        price="$19.99",
        period="per year",
        tagline="The complete workshop, unlocked.",
        features=(
            "Everything in Silver",
            "ALL features unlocked — including dev mode perks",
            "Unlimited parallel jobs and lossless pipelines",
            "Early access to new converters",
            "SVIP badge and priority support",
        ),
    ),
]

RANK_BY_KEY: Dict[str, Rank] = {rank.key: rank for rank in RANKS}


def get_rank(key: Optional[str]) -> Rank:
    """Look a rank up by key, falling back to Normal for unknown values."""
    return RANK_BY_KEY.get((key or "").strip().lower(), RANK_BY_KEY["normal"])


# ------------------------------------------------------------------ features --
# key -> (minimum rank level, translation key for the name, description)
FEATURES: Dict[str, Tuple[int, str, str]] = {
    "gpu_acceleration": (
        1, "GPU Acceleration",
        "Encode with NVENC, Quick Sync or AMF instead of the CPU — often 5-10× faster.",
    ),
    "pdf_conversion": (
        1, "PDF Converting",
        "Convert PDFs to images/text and images or documents to PDF.",
    ),
    "office_archives": (
        1, "Office & Archives Converting",
        "DOCX, XLSX, PPTX, ODT, EPUB, ZIP, 7Z, RAR and TAR families.",
    ),
    "per_file_customization": (
        2, "Per-File Customizations",
        "Give every file in a batch its own codec, CRF, resolution and filters.",
    ),
    "advanced_options": (
        2, "Advanced Options",
        "Custom filters, two-pass encoding and container-level tweaks.",
    ),
    "unlimited_parallel": (
        2, "Unlimited Parallel Jobs",
        "Raise the concurrent-conversion cap beyond the free limit.",
    ),
    "all_features": (
        3, "Everything Unlocked",
        "Every current and future feature of Everything Converter.",
    ),
    # The Error Assistant always runs, but paid tiers get the deeper analysis:
    # more failure patterns, multi-step remediation plans and a full log scan.
    # Normal uses the default effort; Bronze and above use max effort.
    "error_assistant_max_effort": (
        1, "Error Assistant — Max Effort",
        "Deeper diagnosis of conversion failures: extra checks, step-by-step "
        "remediation plans and a full scan of the raw output.",
    ),
}


# --------------------------------------------------------------- AI efforts --
# How hard the Error Assistant thinks about a failure. Every rank gets an
# effort level; higher ranks think harder ("default" -> "max").
EFFORT_DEFAULT = "default"
EFFORT_HIGH = "high"
EFFORT_MAX = "max"

EFFORT_NORMAL = EFFORT_DEFAULT   # Normal: effort default
EFFORT_BRONZE = EFFORT_MAX       # Bronze or plus: effort max
EFFORT_SILVER = EFFORT_MAX
EFFORT_GOLD = EFFORT_MAX

ERROR_ASSISTANT_EFFORTS: Dict[str, str] = {
    "normal": EFFORT_NORMAL,   # Normal: effort default
    "bronze": EFFORT_BRONZE,   # Bronze or plus: effort max
    "silver": EFFORT_SILVER,
    "gold": EFFORT_GOLD,
}

EFFORT_LEVELS = {EFFORT_DEFAULT: 0, EFFORT_HIGH: 1, EFFORT_MAX: 2}


def error_assistant_effort(rank_key: Optional[str], dev_mode: bool = False) -> str:
    """The Error Assistant effort for ``rank_key`` ("default" or "max").

    Dev mode always thinks as hard as possible, mirroring the rule that it
    unlocks every capability.
    """
    if dev_mode:
        return EFFORT_MAX
    return ERROR_ASSISTANT_EFFORTS.get((rank_key or "").strip().lower(),
                                       EFFORT_DEFAULT)


def error_assistant_max_effort(rank_key: Optional[str], dev_mode: bool = False) -> bool:
    """Convenience predicate used by the assistant UI."""
    return EFFORT_LEVELS[error_assistant_effort(rank_key, dev_mode)] >= \
        EFFORT_LEVELS[EFFORT_MAX]


def has_feature(feature: str, rank_key: Optional[str], dev_mode: bool = False) -> bool:
    """Whether ``feature`` is available at ``rank_key`` (or under dev mode)."""
    if dev_mode:
        return True
    requirement = FEATURES.get(feature)
    if requirement is None:
        # Unknown feature keys fail closed only in strict contexts; being liberal
        # here means newly added gates default to "available" until registered.
        return True
    return get_rank(rank_key).level >= requirement[0]


def required_rank(feature: str) -> Rank:
    """The first rank that unlocks ``feature`` (used in upgrade prompts)."""
    requirement = FEATURES.get(feature)
    level = requirement[0] if requirement else 0
    for rank in RANKS:
        if rank.level >= level:
            return rank
    return RANKS[-1]


class RankManager(QObject):
    """Process-wide, settings-backed view of the user's rank + dev mode."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("EverythingConverter", "Settings")
        self._dev_mode = self.settings.value("dev_mode", False, type=bool)

    @classmethod
    def instance(cls) -> "RankManager":
        global _INSTANCE
        if _INSTANCE is None:
            _INSTANCE = RankManager()
        return _INSTANCE

    # ------------------------------------------------------------- state --
    @property
    def rank(self) -> Rank:
        return get_rank(self.settings.value("rank", "normal", type=str))

    @property
    def rank_key(self) -> str:
        return self.rank.key

    @property
    def dev_mode(self) -> bool:
        return self._dev_mode

    def set_rank(self, key: str) -> None:
        self.settings.setValue("rank", get_rank(key).key)
        self.changed.emit()

    def try_enable_dev_mode(self, password: str) -> bool:
        """Unlock everything if ``password`` matches; returns whether it worked."""
        if (password or "").strip() != DEV_PASSWORD:
            return False
        self._dev_mode = True
        self.settings.setValue("dev_mode", True)
        self.changed.emit()
        return True

    def disable_dev_mode(self) -> None:
        self._dev_mode = False
        self.settings.setValue("dev_mode", False)
        self.changed.emit()

    def toggle_dev_mode(self) -> bool:
        """Flip dev mode; enabling requires the password, disabling does not."""
        if self._dev_mode:
            self.disable_dev_mode()
            return False
        return self.try_enable_dev_mode("")  # callers go through the prompt UI

    # ------------------------------------------------------------ checks --
    def has(self, feature: str) -> bool:
        return has_feature(feature, self.rank_key, self._dev_mode)

    @property
    def error_assistant_effort(self) -> str:
        """Effort the Error Assistant should use for this user ("default"/"max")."""
        return error_assistant_effort(self.rank_key, self._dev_mode)

    def lock_message(self, feature: str) -> str:
        """Human hint telling the user which rank unlocks a feature."""
        name, _description = FEATURES.get(feature, (feature, ""))[1:3]
        return "{} · {}".format(name, required_rank(feature).label)


_INSTANCE: Optional[RankManager] = None


def ranks_for_pricing() -> List[Rank]:
    return list(RANKS)
