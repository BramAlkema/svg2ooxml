"""Tests for PowerPoint action URI generation and hyperlink format compliance."""

from svg2ooxml.core.pipeline.navigation import (
    BookmarkTarget,
    CustomShowTarget,
    NavigationAction,
    NavigationKind,
    NavigationSpec,
    SlideTarget,
)
from svg2ooxml.drawingml.navigation import register_navigation
from svg2ooxml.drawingml.xml_builder import to_string


def _elem_to_xml(elem) -> str:
    """Serialize element to XML string, or return empty string for None."""
    if elem is None:
        return ""
    return to_string(elem)


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

    result = register_navigation(
        spec,
        scope="shape",
        text="Next Slide",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )
    xml = _elem_to_xml(result)

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

    result = register_navigation(
        spec,
        scope="shape",
        text="Bookmark Link",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )
    xml = _elem_to_xml(result)

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

    result = register_navigation(
        spec,
        scope="shape",
        text="Custom Show",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )
    xml = _elem_to_xml(result)

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

        def add_asset(asset, _assets=assets):
            _assets.append(asset)

        result = register_navigation(
            spec,
            scope="shape",
            text=f"{action.name} Action",
            allocate_rel_id=allocate_rel_id,
            add_asset=add_asset,
        )
        xml = _elem_to_xml(result)

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

    result = register_navigation(
        spec,
        scope="shape",
        text="External Link",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )
    xml = _elem_to_xml(result)

    # Should use relationship ID, not action attribute
    assert "r:id=" in xml
    assert "action=" not in xml

    # Should have asset with relationship
    assert len(assets) == 1
    assert assets[0].relationship_id == "rId1"
    assert assets[0].target == "https://example.com"
    assert assets[0].action is None  # External links don't use action


def test_external_hyperlink_trims_safe_target():
    """External targets are normalized before they are written to relationships."""
    spec = NavigationSpec(
        kind=NavigationKind.EXTERNAL,
        href=" https://example.com/docs ",
    )

    assets = []

    result = register_navigation(
        spec,
        scope="shape",
        text="External Link",
        allocate_rel_id=lambda: "rId1",
        add_asset=assets.append,
    )
    xml = _elem_to_xml(result)

    assert "r:id=" in xml
    assert len(assets) == 1
    assert assets[0].target == "https://example.com/docs"


def test_external_hyperlink_rejects_unsafe_targets():
    """Unsafe external hyperlinks are dropped before XML or rels are emitted."""
    unsafe_hrefs = [
        "javascript:alert(1)",
        " data:text/plain,hi",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "//example.com/path",
        "\\\\server\\share",
        "https://example.com/\nInjected",
        "http://localhost:8000",
        "http://127.0.0.2/status",
        "http://0.0.0.0/status",
        "http://10.0.0.1/status",
        "http://192.168.1.1/status",
        "http://[::1]/status",
        "http://169.254.169.254/latest",
        "http://metadata.google.internal/computeMetadata/v1/",
    ]

    for href in unsafe_hrefs:
        assets = []
        spec = NavigationSpec(kind=NavigationKind.EXTERNAL, href=href)

        result = register_navigation(
            spec,
            scope="shape",
            text="External Link",
            allocate_rel_id=lambda: "rId1",
            add_asset=assets.append,
        )

        assert result is None
        assert assets == []


def test_navigation_rejects_invalid_relationship_id():
    """Invalid rel IDs must not be embedded in hlinkClick XML."""
    assets = []
    spec = NavigationSpec(kind=NavigationKind.EXTERNAL, href="https://example.com")

    result = register_navigation(
        spec,
        scope="shape",
        text="External Link",
        allocate_rel_id=lambda: "bad id",
        add_asset=assets.append,
    )

    assert result is None
    assert assets == []


def test_slide_navigation_rejects_zero_index():
    """Slide relationships are one-based package references."""
    assets = []
    spec = NavigationSpec(kind=NavigationKind.SLIDE, slide=SlideTarget(index=0))

    result = register_navigation(
        spec,
        scope="shape",
        text="Go to Slide 0",
        allocate_rel_id=lambda: "rId1",
        add_asset=assets.append,
    )

    assert result is None
    assert assets == []


def test_slide_navigation_uses_relationship_not_action():
    """Verify slide navigation uses relationship IDs, not action attributes."""
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

    result = register_navigation(
        spec,
        scope="shape",
        text="Go to Slide 2",
        allocate_rel_id=allocate_rel_id,
        add_asset=add_asset,
    )
    xml = _elem_to_xml(result)

    # Should use relationship ID, not action attribute
    assert "r:id=" in xml
    assert "action=" not in xml

    # Should have asset with relationship to slide
    assert len(assets) == 1
    assert assets[0].relationship_id == "rId1"
    assert assets[0].target == "../slides/slide2.xml"
    assert assets[0].action is None  # Slide links don't use action
