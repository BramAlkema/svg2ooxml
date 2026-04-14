from __future__ import annotations

from lxml import etree as ET
from tools.visual.powerpoint_oracle import _normalize_timing_tree, _summarize_slide


def test_normalize_timing_tree_rewrites_ids_group_ids_and_shape_ids() -> None:
    timing = ET.fromstring(
        """
        <p:timing xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
          <p:tnLst>
            <p:par>
              <p:cTn id="11" grpId="22">
                <p:stCondLst>
                  <p:cond delay="0">
                    <p:tn val="11"/>
                  </p:cond>
                </p:stCondLst>
                <p:childTnLst>
                  <p:set>
                    <p:cBhvr>
                      <p:cTn id="12"/>
                      <p:tgtEl><p:spTgt spid="88"/></p:tgtEl>
                    </p:cBhvr>
                  </p:set>
                </p:childTnLst>
              </p:cTn>
            </p:par>
          </p:tnLst>
          <p:bldLst>
            <p:bldP spid="88" grpId="22"/>
          </p:bldLst>
        </p:timing>
        """
    )

    normalized = _normalize_timing_tree(timing)

    assert normalized.xpath("string(.//p:cTn[1]/@id)", namespaces={"p": timing.nsmap["p"]}) == "id1"
    assert normalized.xpath("string(.//p:cTn[1]/@grpId)", namespaces={"p": timing.nsmap["p"]}) == "grp1"
    assert normalized.xpath("string(.//p:tn/@val)", namespaces={"p": timing.nsmap["p"]}) == "id1"
    assert normalized.xpath("string(.//p:spTgt/@spid)", namespaces={"p": timing.nsmap["p"]}) == "shape1"
    assert normalized.xpath("string(.//p:bldP/@spid)", namespaces={"p": timing.nsmap["p"]}) == "shape1"
    assert normalized.xpath("string(.//p:bldP/@grpId)", namespaces={"p": timing.nsmap["p"]}) == "grp1"


def test_summarize_slide_collects_effect_patterns() -> None:
    slide_xml = b"""
    <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
      <p:timing>
        <p:tnLst>
          <p:par>
            <p:cTn id="1" dur="indefinite" nodeType="tmRoot">
              <p:childTnLst>
                <p:par>
                  <p:cTn id="5" nodeType="clickEffect" presetID="1" presetClass="entr" presetSubtype="0">
                    <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                    <p:childTnLst>
                      <p:set>
                        <p:cBhvr>
                          <p:cTn id="6" dur="1"/>
                          <p:tgtEl><p:spTgt spid="42"/></p:tgtEl>
                          <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>
                        </p:cBhvr>
                      </p:set>
                      <p:animEffect transition="in" filter="fade">
                        <p:cBhvr>
                          <p:cTn id="7" dur="500"/>
                          <p:tgtEl><p:spTgt spid="42"/></p:tgtEl>
                        </p:cBhvr>
                      </p:animEffect>
                    </p:childTnLst>
                  </p:cTn>
                </p:par>
              </p:childTnLst>
            </p:cTn>
          </p:par>
        </p:tnLst>
      </p:timing>
    </p:sld>
    """

    summary = _summarize_slide("slide1.xml", slide_xml)

    assert summary.has_timing is True
    assert summary.tag_counts["set"] == 1
    assert summary.tag_counts["animEffect"] == 1
    assert len(summary.effect_patterns) == 1

    pattern = summary.effect_patterns[0]
    assert pattern.node_type == "clickEffect"
    assert pattern.preset_class == "entr"
    assert pattern.child_tags == ["set", "animEffect"]
    assert pattern.target_shapes == ["42"]
    assert pattern.attr_names == ["style.visibility"]
    assert pattern.start_delays == ["0"]
    assert pattern.behavior_durations == ["1", "500"]
    assert pattern.signature == "clickEffect|entr|1|set+animEffect|style.visibility"
    assert pattern.family_signature == "clickEffect|entr|set+animEffect|style.visibility"
