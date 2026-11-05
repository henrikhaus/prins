"""Needs the network: fetches real logos, because "print the Spotify logo" must really work."""

from __future__ import annotations

import pytest

from prins.design.assets import AssetError, logo_svg
from prins.design.canvas import Canvas, DesignError


@pytest.mark.parametrize("name", ["spotify", "Spotify", "github", "nike", "apple", "Coca-Cola", "Node.js"])
def test_real_logos_render(name):
    canvas = Canvas()
    canvas.apply({"op": "logo", "name": name, "x": 80, "y": 30, "w": 150, "h": 150})
    assert canvas.image.convert("L").histogram()[0] > 800, name


def test_an_unknown_logo_says_what_to_try_instead():
    with pytest.raises(DesignError, match="draw_image or draw_svg"):
        Canvas().apply({"op": "logo", "name": "definitely-not-a-real-brand-xyz"})


def test_logos_work_for_the_internal_designer_too():
    canvas = Canvas(external=False)
    canvas.apply({"op": "logo", "name": "spotify"})
    assert canvas.image.convert("L").histogram()[0] > 3000
