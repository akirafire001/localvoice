import json
from types import SimpleNamespace as NS

import pytest

from localvoice.config import Config
from localvoice.services import llm as llm_mod
from localvoice.services.llm import LLMError, OpenAILLM, _MetaError


def _resp(text=None, status="completed", refusal=False, reason=None, annotations=()):
    content = []
    if refusal:
        content.append(NS(type="refusal", refusal="no"))
    if text is not None:
        content.append(NS(type="output_text", text=text, annotations=list(annotations)))
    return NS(
        output=[NS(type="message", content=content)],
        output_text=text or "",
        status=status,
        incomplete_details=NS(reason=reason) if reason else None,
        model="gpt-test",
        usage=NS(input_tokens=1000, output_tokens=200, input_tokens_details=NS(cached_tokens=500)),
    )


class FakeResponses:
    def __init__(self, resp):
        self.resp = resp
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.resp


def _adapter(resp, **cfg):
    a = OpenAILLM.__new__(OpenAILLM)
    a.cfg = Config(OPENAI_API_KEY="k", LLM_PROVIDER="openai", LLM_PRICE_INPUT_PER_MTOK=2.0,
                   LLM_PRICE_OUTPUT_PER_MTOK=8.0, **cfg)
    a.model = "gpt-test"
    a.client = NS(responses=FakeResponses(resp))
    return a


def test_json_call_uses_strict_schema_and_costs():
    a = _adapter(_resp(json.dumps({"summary": "ok"})))
    schema = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"],
              "additionalProperties": False}
    data, meta = a._json_call("sys", "user", schema, "low", 4.0, max_tokens=100)
    assert data == {"summary": "ok"}
    kw = a.client.responses.kwargs
    assert kw["text"]["format"]["strict"] is True and kw["reasoning"] == {"effort": "low"}
    assert kw["store"] is False and kw["max_output_tokens"] == 100
    # 500 uncached*2 + 500 cached*2*0.1 + 200*8 per million
    assert meta["cost_usd"] == pytest.approx((1000 + 100 + 1600) / 1e6)


def test_refusal_incomplete_and_bad_json():
    for resp, code in ((_resp(refusal=True), "refusal"),
                       (_resp("{", status="incomplete", reason="max_output_tokens"), "max_tokens"),
                       (_resp("not json"), "invalid_json")):
        with pytest.raises(_MetaError) as e:
            _adapter(resp)._json_call("s", "u", {}, "low", 4.0)
        assert e.value.code == code


def test_web_search_citations_become_materials():
    text = "Hiroshima okonomiyaki is layered."
    ann = NS(type="url_citation", url="https://example.org/a", title="A", start_index=0, end_index=9)
    materials, _ = _adapter(_resp(text, annotations=[ann])).research_with_web_search("xn76ur", (34.3, 132.4), [])
    assert materials == [{"kind": "web", "title": "A", "url": "https://example.org/a", "text": "Hiroshima"}]


def test_get_llm_picks_openai(app):
    with app.app_context():
        cfg = app.config["LV"]
        cfg.LLM_PROVIDER, cfg.OPENAI_API_KEY = "openai", "sk-test"
        assert isinstance(llm_mod.get_llm(), OpenAILLM)
        cfg.OPENAI_API_KEY = ""
        app.extensions.pop("lv_llm_client", None)
        assert llm_mod.get_llm() is None


def test_api_errors_map_to_llm_error():
    import openai

    a = _adapter(None)

    def boom(**_):
        raise openai.APIConnectionError(request=NS(method="POST", url="x"))

    a.client = NS(responses=NS(create=boom))
    with pytest.raises(LLMError, match="connection_error"):
        a._json_call("s", "u", {}, "low", 4.0)
