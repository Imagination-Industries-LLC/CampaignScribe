"""Guard against legacy numeric tab references reintroduced after the rename.

The six tab classes/attributes use descriptive names (discover_tab, refine_tab,
build_profile_tab, history_tab, transcribe_tab, summarize_tab). Stringly-typed
cross-tab calls like self.app.tab5 are not caught by construction/smoke tests,
so this static scan fails if any legacy numeric attribute reference returns.
"""

from __future__ import annotations

import re
from pathlib import Path

# Matches self.tab3 / self.app.tab5 / app.tab2 etc. — legacy numeric attributes.
LEGACY_ATTR = re.compile(r"\b(?:self\.)?(?:app\.)?tab[1-6]\b")

UI_DIR = Path(__file__).resolve().parents[2] / "app" / "ui"


def test_no_legacy_numeric_tab_attribute_references():
    offenders = []
    for py in sorted(UI_DIR.glob("*.py")):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), start=1):
            if LEGACY_ATTR.search(line):
                offenders.append(f"{py.name}:{i}: {line.strip()}")
    assert not offenders, "Legacy numeric tab references found:\n" + "\n".join(offenders)
