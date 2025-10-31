from __future__ import annotations

import pytest

# Import fixtures so pytest registers them for the visual suite.
from tests.visual.helpers import visual_tools  # noqa: F401

pytestmark = pytest.mark.visual
