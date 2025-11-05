"""Tests for PowerPoint action URI generation and hyperlink format compliance."""

from svg2ooxml.core.pipeline.navigation import (
    BookmarkTarget,
    CustomShowTarget,
    NavigationAction,
    NavigationKind,
    NavigationSpec,
)
from svg2ooxml.drawingml.navigation import normalize_navigation, register_navigation


def test_action_navigation_generates_valid_ppaction_uri():
    """Verify ACTION navigation generates valid ppaction:// URIs per ECMA-376."""
    spec = NavigationSpec(
        kind=NavigationKind.ACTION,
        action=NavigationAction.NEXT,
    )

    rel_id_counter = 0

    def allocate_rel_id():
        nonlocal rel_id_counter
        rel_id_counter += 1
        return f"rId{rel_id_counter}"

    assets = []

    def add_asset(asset):
        assets.append(asset)

    xml = register_navigation(
        spec,
        scope="shape",
        text="Next Slide",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )

    # Should generate ppaction:// URI with jump parameter
    assert "ppaction://hlinkshowjump?jump=nextslide" in xml
    assert 'action="ppaction://hlinkshowjump?jump=nextslide"' in xml

    # Should have asset with action URI
    assert len(assets) == 1
    assert assets[0].action == "ppaction://hlinkshowjump?jump=nextslide"
    assert assets[0].relationship_id is None  # Actions don't need relationships


def test_bookmark_navigation_does_not_generate_invalid_ppaction():
    """Verify BOOKMARK navigation doesn't generate invalid ppaction:// URIs.

    Per ECMA-376, ppaction://hlinkshowjump only supports 'jump' parameter.
    The 'bookmark' parameter is not part of the specification and causes
    PowerPoint to strip the hyperlink during repair.
    """
    spec = NavigationSpec(
        kind=NavigationKind.BOOKMARK,
        bookmark=BookmarkTarget(name="testrect1"),
    )

    rel_id_counter = 0

    def allocate_rel_id():
        nonlocal rel_id_counter
        rel_id_counter += 1
        return f"rId{rel_id_counter}"

    assets = []

    def add_asset(asset):
        assets.append(asset)

    xml = register_navigation(
        spec,
        scope="shape",
        text="Bookmark Link",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )

    # Should NOT generate ppaction:// URI with bookmark parameter
    assert "ppaction://hlinkshowjump?bookmark=" not in xml
    assert "bookmark=testrect1" not in xml

    # BOOKMARK navigation has no PowerPoint equivalent
    # XML may be generated but without action attribute (non-functional link is harmless)
    # The important thing is that it doesn't have invalid ppaction:// URLs
    assert 'action="' not in xml or "ppaction://hlinkshowjump?jump=" in xml


def test_custom_show_navigation_does_not_generate_invalid_ppaction():
    """Verify CUSTOM_SHOW navigation doesn't generate invalid ppaction:// URIs."""
    spec = NavigationSpec(
        kind=NavigationKind.CUSTOM_SHOW,
        custom_show=CustomShowTarget(name="MyShow"),
    )

    rel_id_counter = 0

    def allocate_rel_id():
        nonlocal rel_id_counter
        rel_id_counter += 1
        return f"rId{rel_id_counter}"

    assets = []

    def add_asset(asset):
        assets.append(asset)

    xml = register_navigation(
        spec,
        scope="shape",
        text="Custom Show",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )

    # Should NOT generate ppaction:// URI with show parameter
    assert "ppaction://hlinkshowjump?show=" not in xml
    assert "show=MyShow" not in xml

    # CUSTOM_SHOW navigation requires PowerPoint-specific setup
    # XML may be generated but without action attribute (non-functional link is harmless)
    assert 'action="' not in xml or "ppaction://hlinkshowjump?jump=" in xml


def test_all_action_types_generate_valid_uris():
    """Verify all NavigationAction enum values generate valid ppaction:// URIs."""
    actions = [
        (NavigationAction.NEXT, "nextslide"),
        (NavigationAction.PREVIOUS, "previousslide"),
        (NavigationAction.FIRST, "firstslide"),
        (NavigationAction.LAST, "lastslide"),
        (NavigationAction.ENDSHOW, "endshow"),
    ]

    for action, expected_param in actions:
        spec = NavigationSpec(kind=NavigationKind.ACTION, action=action)

        rel_id_counter = 0

        def allocate_rel_id():
            nonlocal rel_id_counter
            rel_id_counter += 1
            return f"rId{rel_id_counter}"

        assets = []

        def add_asset(asset):
            assets.append(asset)

        xml = register_navigation(
            spec,
            scope="shape",
            text=f"{action.name} Action",
            allocate_rel_id=allocate_rel_id,
            add_asset=add_asset,
        )

        # Verify correct jump parameter
        expected_action = f"ppaction://hlinkshowjump?jump={expected_param}"
        assert expected_action in xml, f"Expected {expected_action} for {action.name}"


def test_external_hyperlink_uses_relationship_not_action():
    """Verify external hyperlinks use relationship IDs, not action attributes."""
    spec = NavigationSpec(
        kind=NavigationKind.EXTERNAL,
        href="https://example.com",
    )

    rel_id_counter = 0

    def allocate_rel_id():
        nonlocal rel_id_counter
        rel_id_counter += 1
        return f"rId{rel_id_counter}"

    assets = []

    def add_asset(asset):
        assets.append(asset)

    xml = register_navigation(
        spec,
        scope="shape",
        text="External Link",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )

    # Should use relationship ID, not action attribute
    assert "r:id=" in xml
    assert "action=" not in xml

    # Should have asset with relationship
    assert len(assets) == 1
    assert assets[0].relationship_id == "rId1"
    assert assets[0].target == "https://example.com"
    assert assets[0].action is None  # External links don't use action


def test_slide_navigation_uses_relationship_not_action():
    """Verify slide navigation uses relationship IDs, not action attributes."""
    from svg2ooxml.core.pipeline.navigation import SlideTarget

    spec = NavigationSpec(
        kind=NavigationKind.SLIDE,
        slide=SlideTarget(index=2),
    )

    rel_id_counter = 0

    def allocate_rel_id():
        nonlocal rel_id_counter
        rel_id_counter += 1
        return f"rId{rel_id_counter}"

    assets = []

    def add_asset(asset):
        assets.append(asset)

    xml = register_navigation(
        spec,
        scope="shape",
        text="Go to Slide 2",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )

    # Should use relationship ID, not action attribute
    assert "r:id=" in xml
    assert "action=" not in xml

    # Should have asset with relationship to slide
    assert len(assets) == 1
    assert assets[0].relationship_id == "rId1"
    assert assets[0].target == "../slides/slide2.xml"
    assert assets[0].action is None  # Slide links don't use action
