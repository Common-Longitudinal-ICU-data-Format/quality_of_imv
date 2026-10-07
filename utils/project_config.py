"""Configuration loading and CLIF-version-aware category vocabularies.

Two config files, deliberately separate:

* ``config/config.json``      -- the clifpy site config (data_directory, filetype,
                                 timezone). Gitignored; contains local paths.
* ``config/project_params.json`` -- analysis parameters. Committed, so the research team
                                 can review them against ``analysis_plan/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Project root = parent of this file's directory.
ROOT = Path(__file__).resolve().parent.parent

CLIF_CONFIG_PATH = ROOT / "config" / "config.json"
PARAMS_PATH = ROOT / "config" / "project_params.json"

INTERMEDIATE_DIR = ROOT / "output" / "intermediate_phi"
FINAL_DIR = ROOT / "output" / "final_no_phi"


def load_params(path: Path | str | None = None) -> dict[str, Any]:
    """Load committed analysis parameters."""
    return json.loads(Path(path or PARAMS_PATH).read_text())


def load_clif_config(path: Path | str | None = None) -> dict[str, Any] | None:
    """Load the clifpy site config, or None if the site has not created one yet.

    Returning None rather than raising lets the notebooks fall back to synthetic demo
    data, so they are runnable before a site is wired up.
    """
    p = Path(path or CLIF_CONFIG_PATH)
    if not p.exists():
        return None
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# CLIF category vocabularies.
#
# These differ between CLIF 2.1 (title case) and CLIF 3.0 (snake_case), and getting
# them wrong produces silently empty filters rather than errors. See
# analysis_plan/02_quality_score.md section 11, trap 1.
# ---------------------------------------------------------------------------

VOCAB = {
    "2.1": {
        "imv_device": "IMV",
        "cpap_device": "CPAP",
        "controlled_modes": [
            "Assist Control-Volume Control",
            "Pressure Control",
            "Pressure-Regulated Volume Control",
            "SIMV",
        ],
        "support_modes": ["Pressure Support/CPAP"],
    },
    "3.0": {
        "imv_device": "imv",
        "cpap_device": "cpap",
        "controlled_modes": ["acvc", "pressure_control", "prvc", "simv"],
        "support_modes": ["ps_or_cpap"],
    },
}


def get_vocab(clif_version: str = "2.1") -> dict[str, Any]:
    """Category values for a CLIF schema version, lowercased for matching.

    All comparisons in this project are done on lowercased strings, so callers should
    lowercase the data column too. The one exception is ``patient.sex_category``, which
    the dashboard's PBW formula matches in exact case -- see
    analysis_plan/02_quality_score.md section 4.1.
    """
    if clif_version not in VOCAB:
        raise ValueError(
            f"Unsupported clif_version {clif_version!r}; expected one of {list(VOCAB)}"
        )
    v = VOCAB[clif_version]
    return {
        "imv_device": v["imv_device"].lower(),
        "cpap_device": v["cpap_device"].lower(),
        "controlled_modes": [m.lower() for m in v["controlled_modes"]],
        "support_modes": [m.lower() for m in v["support_modes"]],
    }
