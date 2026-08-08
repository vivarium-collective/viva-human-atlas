from viva_human_atlas import atlas_pack


def test_model_link_is_source_aware():
    bio = {"repository": "biomodels", "source_id": "BIOMD0000000633", "biomodel_id": "BIOMD0000000633",
           "name": "Bulik2016"}
    phys = {"repository": "physionet", "source_id": "mitdb", "name": "MIT-BIH",
            "identifier": "https://physionet.org/content/mitdb/"}
    assert atlas_pack.model_url(bio).endswith("BIOMD0000000633")
    assert atlas_pack.model_url(phys) == "https://physionet.org/content/mitdb/"
    assert atlas_pack.model_ref(phys)["repository"] == "physionet"
    assert atlas_pack.model_ref(phys)["source_id"] == "mitdb"
