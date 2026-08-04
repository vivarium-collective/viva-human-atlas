from viva_human_atlas.sbml_identifiers import collection_of_uri, extract_identifiers


def test_collection_of_uri_recognises_each_class():
    cases = {
        "http://identifiers.org/chebi/CHEBI:17234": ("chebi", "CHEBI:17234"),
        "http://identifiers.org/uniprot/P01308": ("uniprot", "P01308"),
        "http://identifiers.org/kegg.compound/C00031": ("kegg", "C00031"),
        "http://identifiers.org/go/GO:0006006": ("go", "GO:0006006"),
        "http://purl.obolibrary.org/obo/CL_0000169": ("cl", "CL:0000169"),
        "http://identifiers.org/uberon/UBERON:0001264": ("uberon", "UBERON:0001264"),
        "urn:miriam:obo.fma:FMA%3A16016": ("fma", "FMA:16016"),
        "http://identifiers.org/bto/BTO:0000991": ("bto", "BTO:0000991"),
    }
    for uri, expected in cases.items():
        assert collection_of_uri(uri) == expected
    assert collection_of_uri("http://identifiers.org/pubmed/11073807") is None


_SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
 <model id="m">
  <listOfSpecies>
   <species id="glucose" metaid="s1">
    <annotation><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:bqbiol="http://biomodels.net/biology-qualifiers/">
     <rdf:Description rdf:about="#s1">
      <bqbiol:is><rdf:Bag>
        <rdf:li rdf:resource="http://identifiers.org/chebi/CHEBI:17234"/>
        <rdf:li rdf:resource="http://identifiers.org/kegg.compound/C00031"/>
      </rdf:Bag></bqbiol:is>
      <bqbiol:isPartOf><rdf:Bag>
        <rdf:li rdf:resource="http://identifiers.org/uberon/UBERON:0001264"/>
      </rdf:Bag></bqbiol:isPartOf>
     </rdf:Description>
    </rdf:RDF></annotation>
   </species>
   <species id="insulin" metaid="s2">
    <annotation><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns:bqbiol="http://biomodels.net/biology-qualifiers/">
     <rdf:Description rdf:about="#s2">
      <bqbiol:is><rdf:Bag>
        <rdf:li rdf:resource="http://identifiers.org/uniprot/P01308"/>
      </rdf:Bag></bqbiol:is>
     </rdf:Description>
    </rdf:RDF></annotation>
   </species>
  </listOfSpecies>
 </model>
</sbml>"""


def test_extract_identifiers_collects_all_classes():
    out = extract_identifiers(_SBML)
    assert out["chebi"] == ["CHEBI:17234"]
    assert out["kegg"] == ["C00031"]
    assert out["uniprot"] == ["P01308"]
    assert out["uberon"] == ["UBERON:0001264"]
    assert out["n_species"] == 2
    assert out["go"] == [] and out["cl"] == []
