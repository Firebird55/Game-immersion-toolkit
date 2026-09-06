from scripts.update_voice_assets import ongoing_voice_links


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
