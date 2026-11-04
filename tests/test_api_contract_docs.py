from main import app


def test_review_and_request_contracts_are_exposed_in_openapi():
    schema = app.openapi()
    paths = schema['paths']
    assert '/tours/{tour_id}/reviews/' in paths
    assert '/tours/{tour_id}/reviews/{review_id}/' in paths
    assert '/travel-requests/' in paths and 'post' in paths['/travel-requests/']
    assert '/travel-requests/me/' in paths
    assert '/travel-requests/me/{request_id}/' in paths

    card = schema['components']['schemas']['TourCardSchema']['properties']
    assert card['average_rating']['anyOf']
    assert card['review_count']['type'] == 'integer'

    assert 'security' not in paths['/tours/{tour_id}/reviews/']['get']
    assert 'security' in paths['/tours/{tour_id}/reviews/']['post']
    assert 'security' in paths['/travel-requests/me/']['get']
