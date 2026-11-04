import os


def test_ai_clients_are_configured_for_required_invocation_modes():
    from mysite.chain.agent import agent_llm, extractor, llm
    from mysite.translations.translator import model as translation_model

    assert callable(llm.ainvoke)
    assert callable(agent_llm.astream)
    assert callable(extractor.ainvoke)
    assert callable(translation_model.invoke)
    assert translation_model.model == os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')


def test_translation_provider_does_not_set_ignored_sampling_temperature(monkeypatch):
    import langchain_google_genai

    from ML import provider

    options = {}

    def fake_chat_model(**kwargs):
        options.update(kwargs)
        return object()

    monkeypatch.setattr(langchain_google_genai, 'ChatGoogleGenerativeAI', fake_chat_model)
    provider.client.cache_clear()
    try:
        provider.client('translation')
        assert 'temperature' not in options
    finally:
        provider.client.cache_clear()
