# modules/config.py
import json
from pathlib import Path

from modules.platformModules import config_dir

# config_dir should already point at wherever you resolved it —
# same Path object you're using elsewhere for the config directory.
CONFIG_FILE = Path(config_dir) / "config.json"

_DEFAULTS = {
    "appearance_mode": "System",
}

# Collections where new named entries get seeded in over app versions,
# without ever overwriting or reviving whatever the user's done with a
# name they've already seen — see _seed_new_defaults().
_SEEDABLE = ("custom_targets", "presets")


def _seed_new_defaults(data: dict) -> tuple:
    """Adds any default preset/custom-target the user has never seen
    before (per _DEFAULTS above), without reviving one they deleted.

    The tricky bit: "user deleted this preset" and "user has never had
    this preset" both look identical in the data alone — an absent key.
    So presence/absence of the *name* isn't enough; we track which names
    have ever been seeded to this user in data["_seeded"], and only copy
    a default in the first time its name shows up there. After that,
    what happens to it is entirely the user's call, forever.

    Returns (data, changed) — changed is True if this call added
    anything, so the caller knows whether a save is worth doing.
    """
    changed = False
    seeded = data.setdefault("_seeded", {})
    for key in _SEEDABLE:
        seeded_names = set(seeded.get(key, []))
        bucket = data.setdefault(key, {})
        for name, spec in _DEFAULTS.get(key, {}).items():
            if name not in seeded_names:
                bucket[name] = spec
                seeded_names.add(name)
                changed = True
        if seeded.get(key) != sorted(seeded_names):
            seeded[key] = sorted(seeded_names)
            changed = True
    return data, changed


def load_config() -> dict:
    is_first_run = not CONFIG_FILE.exists()
    data = {}
    if not is_first_run:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}  # corrupt/unreadable file — fall through to defaults

    # Merge over defaults rather than trusting the file wholesale — this
    # way, if a future app version adds a new flat setting key, an
    # existing user's older config.json (which won't have that key yet)
    # still gets a sane default instead of a KeyError. This is a shallow
    # overlay, so data["presets"]/["custom_targets"] (if present) win
    # wholesale here — the fine-grained "add only what's new" merge for
    # those happens next, in _seed_new_defaults().
    merged = {**_DEFAULTS, **data}
    merged, seeded_something = _seed_new_defaults(merged)

    if is_first_run or seeded_something:
        save_config(merged)
    return merged


def save_config(data: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        print(f"  ✗ Failed to save config: {e}")


def get_setting(key, default=None):
    return load_config().get(key, default)


def set_setting(key, value):
    data = load_config()
    data[key] = value
    save_config(data)
