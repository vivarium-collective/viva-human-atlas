from viva_human_atlas.biopax_identifiers import extract_biopax_identifiers

_OWL = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:bp="http://www.biopax.org/release/biopax-level3.owl#">
 <bp:UnificationXref rdf:about="a">
  <bp:id>C00013</bp:id><bp:db>KEGG Compound</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="b">
  <bp:id>CHEBI:89363</bp:id><bp:db>ChEBI</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="c">
  <bp:id>GO:0005783</bp:id><bp:db>Gene Ontology</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="d">
  <bp:id>P01308</bp:id><bp:db>UniProt</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="e">
  <bp:id>R-HSA-70171</bp:id><bp:db>Reactome</bp:db></bp:UnificationXref>
 <bp:UnificationXref rdf:about="f">
  <bp:id>9606</bp:id><bp:db>Taxonomy</bp:db></bp:UnificationXref>
 <bp:PublicationXref rdf:about="g">
  <bp:id>26935066</bp:id><bp:db>PubMed</bp:db></bp:PublicationXref>
</rdf:RDF>"""


def test_extract_biopax_identifiers_by_db():
    out = extract_biopax_identifiers(_OWL)
    assert out["kegg"] == ["C00013"]
    assert out["chebi"] == ["CHEBI:89363"]
    assert out["go"] == ["GO:0005783"]
    assert out["uniprot"] == ["P01308"]
    assert out["reactome"] == ["R-HSA-70171"]
    assert out["taxonomy"] == ["NCBITaxon:9606"]  # normalized to a CURIE


def test_extract_biopax_ignores_publication_and_bad_xml():
    out = extract_biopax_identifiers(_OWL)
    assert "26935066" not in out["chebi"] + out["kegg"]  # PublicationXref skipped
    assert extract_biopax_identifiers("not xml")["chebi"] == []
