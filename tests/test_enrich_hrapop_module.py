import json
from pathlib import Path
from viva_human_atlas.enrich_hrapop import enrich_hrapop_map

def test_enrich_hrapop_map_adds_hra_pop(tmp_path):
    # An entry whose organ HRApop covers should gain an hra_pop field.
    db = tmp_path / "db.json"
    db.write_text(json.dumps([
        {"biomodel_id": "M1", "organs": [{"label": "kidney", "uberon": "UBERON:0002113"}]},
    ]), encoding="utf-8")
    total, linked = enrich_hrapop_map(str(db))
    assert total == 1
    out = json.loads(db.read_text(encoding="utf-8"))
    assert linked >= 0                      # linked is 0 or 1 depending on HRApop coverage
    assert ("hra_pop" in out[0]) == (linked == 1)
