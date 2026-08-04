from viva_human_atlas import llm_extract


class _FakeClient:
    def __init__(self, payload): self._payload = payload; self.calls = 0
    class _Messages:
        pass
    @property
    def messages(self):
        outer = self
        class M:
            def create(self, **kwargs):
                outer.calls += 1
                class Block:  # a tool_use content block
                    type = "tool_use"; name = "record_model_facts"; input = outer._payload
                class Resp: content = [Block()]
                return Resp()
        return M()


def test_extract_returns_tool_input():
    client = _FakeClient({"organs": ["pancreas"], "disease": "type 2 diabetes", "summary": "x"})
    out = llm_extract.extract("Topp2000", "beta-cell mass...", None, client=client)
    assert out["organs"] == ["pancreas"]
    assert out["disease"] == "type 2 diabetes"


def test_extract_no_text_returns_empty_and_no_call():
    client = _FakeClient({})
    assert llm_extract.extract("x", None, None, client=client) == {}
    assert client.calls == 0
