from scripts.update_voice_assets import comic_voice_links, ongoing_voice_links


def test_ongoing_links_include_protagonist_variants_and_other_speakers() -> None:
    config = {"rows": [
        {
            "PMNJCMFLJIL": "Side_OngoingLevel_Test_01",
            "DGFCDOGFFGP": "OngoingLevel_Test_Belle_001",
            "EODLJIEIIGJ": "OngoingLevel_Test_Wise_001",
        },
        {
            "PMNJCMFLJIL": "Side_OngoingLevel_Test_02",
            "DGFCDOGFFGP": "OngoingLevel_Test_Evelyn_001",
            "EODLJIEIIGJ": "",
        },
    ]}
    english = {
        "Side_OngoingLevel_Test_01": "{M#Wise line.}{F#Belle line.}",
        "Side_OngoingLevel_Test_02": "Evelyn line.",
    }
    links = ongoing_voice_links(config, english)
    assert {item["source"] for item in links} == {
        "OngoingLevel_Test_Wise_001",
        "OngoingLevel_Test_Belle_001",
        "OngoingLevel_Test_Evelyn_001",
    }
    assert next(item for item in links if "Wise" in item["source"])["english"] == "Wise line."
    assert next(item for item in links if "Belle" in item["source"])["english"] == "Belle line."


def test_comic_variants_follow_explicit_gender_labels_and_reject_ambiguous_text():
    link = {'text_id': 'Comic_test', 'source': '{F#VO_Comic/VO_Test/Female}{M#VO_Comic/VO_Test/Male}'}
    assert comic_voice_links([link], {'Comic_test': '{M#Male line.}{F#Female line.}'}) == [
        {**link, 'source': 'VO_Comic/VO_Test/Female', 'english': 'Female line.'},
        {**link, 'source': 'VO_Comic/VO_Test/Male', 'english': 'Male line.'},
    ]
    assert comic_voice_links([link], {'Comic_test': 'No visible gender distinction.'}) == []
    plain = {**link, 'source': 'VO_Comic/VO_Test/Npc'}
    assert comic_voice_links([plain], {}) == [plain]
