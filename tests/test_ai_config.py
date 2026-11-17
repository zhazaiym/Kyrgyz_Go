import os


def test_ai_clients_are_configured_for_required_invocation_modes():
    from ML.agent import agent_llm, extractor
    from ML.provider import client
    from ML.translation import translator

    assert callable(client('llm').ainvoke)
    assert callable(agent_llm.astream)
    assert callable(extractor.ainvoke)
    assert callable(translator.invoke)
    assert client('translation').model == os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')


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
