from __future__ import annotations

from pathlib import Path

from tools.visual.filter_usage import analyze_filter_usage, render_markdown


def test_analyze_filter_usage_counts_primitives_chains_and_pairs(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    (corpus / "a.svg").write_text(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <defs>
            <filter id="f1">
              <feGaussianBlur stdDeviation="4"/>
              <feOffset dx="2" dy="3"/>
              <feMerge/>
            </filter>
          </defs>
        </svg>
        """,
        encoding="utf-8",
    )
    (corpus / "b.svg").write_text(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <defs>
            <filter id="f2">
              <feGaussianBlur stdDeviation="2"/>
            </filter>
            <filter id="f3">
              <feFlood flood-color="red"/>
              <feComposite operator="in"/>
            </filter>
          </defs>
        </svg>
        """,
        encoding="utf-8",
    )

    report = analyze_filter_usage([corpus / "a.svg", corpus / "b.svg"], roots=[corpus])

    assert report.total_svgs == 2
    assert report.filtered_svgs == 2
    assert report.total_filter_elements == 3
    assert report.total_primitive_instances == 6
    assert report.primitive_instance_counts["fegaussianblur"] == 2
    assert report.primitive_document_counts["fegaussianblur"] == 2
    assert report.chain_counts["fegaussianblur > feoffset > femerge"] == 1
    assert report.chain_counts["feflood > fecomposite"] == 1
    assert report.adjacent_pair_counts["fegaussianblur -> feoffset"] == 1
    assert report.adjacent_pair_counts["feoffset -> femerge"] == 1
    assert report.per_root_instance_counts[corpus.as_posix()]["feflood"] == 1
    markdown = render_markdown(report, top_n=5)
    assert "`fegaussianblur`" in markdown
    assert "`fegaussianblur > feoffset > femerge`" in markdown


def test_analyze_filter_usage_ignores_nested_light_source_children(tmp_path: Path) -> None:
    svg_path = tmp_path / "lighting.svg"
    svg_path.write_text(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <defs>
            <filter id="light">
              <feDiffuseLighting>
                <fePointLight x="1" y="2" z="3"/>
              </feDiffuseLighting>
            </filter>
          </defs>
        </svg>
        """,
        encoding="utf-8",
    )

    report = analyze_filter_usage([svg_path], roots=[tmp_path])

    assert report.primitive_instance_counts == {"fediffuselighting": 1}
    assert "fepointlight" not in report.primitive_instance_counts
