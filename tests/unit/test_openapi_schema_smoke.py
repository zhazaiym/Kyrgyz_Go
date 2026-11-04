def test_fastapi_openapi_builds_with_domain_schema_modules():
    from main import app

    spec = app.openapi()

    assert '/tours/' in spec['paths']
    assert '/travel-requests/' in spec['paths']
    schemas = spec['components']['schemas']
    assert 'TourOutSchema' in schemas
    assert 'TravelRequestOutSchema' in schemas
    assert 'ContactOutSchema' in schemas
