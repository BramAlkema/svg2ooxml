from __future__ import annotations

import pytest

from tools.visual.stack import default_visual_stack


@pytest.fixture
def visual_tools():
    return default_visual_stack()

pytestmark = pytest.mark.visual
