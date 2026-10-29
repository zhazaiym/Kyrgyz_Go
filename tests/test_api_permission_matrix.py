"""Probe every catalogue write operation exposed by the current OpenAPI."""

import re

import pytest

from main import app

CATALOGUE_PREFIXES = {
    'tour-categories',
    'tours',
    'tour-images',
    'tour-programs',
    'hotels',
    'hotel-images',
    'transports',
    'transport-images',
    'helicopter-tours',
    'helicopter-images',
    'trekkings',
    'trekking-images',
    'trekking-programs',
    'countries',
    'regions',
    'districts',
    'abouts',
    'about-sections',
    'contacts',
    'faqs',
}


@pytest.mark.parametrize('authenticated', [False, True], ids=['guest', 'customer'])
def test_all_catalogue_writes_require_administrator(client, customer_headers, authenticated):
    headers = customer_headers if authenticated else {}
    tested_prefixes = set()
    for path, operations in app.openapi()['paths'].items():
        prefix = path.strip('/').split('/')[0]
        if prefix not in CATALOGUE_PREFIXES:
            continue
        for method in operations.keys() & {'post', 'put', 'patch', 'delete'}:
            concrete_path = re.sub(r'\{[^}]+\}', '1', path)
            response = client.request(method.upper(), concrete_path, json={}, headers=headers)
            assert response.status_code in {401, 403}, (
                f'{method.upper()} {path}: {response.status_code} {response.text}'
            )
            tested_prefixes.add(prefix)
    assert tested_prefixes == CATALOGUE_PREFIXES
