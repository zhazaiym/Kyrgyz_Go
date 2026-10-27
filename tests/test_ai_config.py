import os


def test_ai_clients_are_configured_for_required_invocation_modes():
    from mysite.chain.agent import agent_llm, extractor, llm
    from mysite.translations.translator import model as translation_model

    assert callable(llm.ainvoke)
    assert callable(agent_llm.astream)
    assert callable(extractor.ainvoke)
    assert callable(translation_model.invoke)
    assert translation_model.model == os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
