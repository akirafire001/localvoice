"""Public LP: locale negotiation and prepared content, without DB/TTS requests."""
import json
from pathlib import Path
import pytest
from localvoice import create_app
from localvoice.config import Config
from localvoice.landing_copy import COPY
from localvoice.services.languages import LANGUAGES


@pytest.fixture
def lp_client():
    return create_app(Config(DATABASE_URL='sqlite://', LLM_PROVIDER='disabled')).test_client()


@pytest.mark.parametrize('header,expected', [
    ('ja-JP,en;q=0.8', 'ja'), ('en-US', 'en'), ('zh-TW', 'zh'), ('ko-KR', 'ko'),
    ('es-MX', 'es'), ('fr-CA', 'fr'), ('de-DE,en;q=0.8', 'en'),
    ('en;q=0,ja;q=0.8', 'ja'), ('fr-CA;q=0.4,ko-KR;q=0.9', 'ko'),
])
def test_browser_language(lp_client, header, expected):
    response = lp_client.get('/', headers={'Accept-Language': header})
    assert response.status_code == 200
    assert response.headers['Content-Language'] == expected
    assert 'Accept-Language' in response.headers['Vary']
    assert f'<html lang="{expected}">'.encode() in response.data


def test_explicit_language_wins(lp_client):
    response = lp_client.get('/?lang=fr', headers={'Accept-Language': 'ja-JP'})
    assert response.headers['Content-Language'] == 'fr'
    assert b'Chaque lieu.' in response.data


def test_prepared_samples_are_complete_and_public(lp_client):
    base = Path(__file__).parents[1] / 'localvoice'
    samples = json.loads((base / 'landing_samples.json').read_text(encoding='utf-8'))
    assert len(samples) == 3
    assert all('d7a3d1d9ca14' not in sample['key'] for sample in samples)
    assert set(COPY) == set(LANGUAGES)
    for sample in samples:
        assert set(sample['languages']) == set(LANGUAGES)
        assert sample['sources']
        for lang, story in sample['languages'].items():
            assert story['title'] and story['body']
            assert story['audio'].startswith('landing/samples/')
            path = base / 'static' / story['audio']
            assert path.stat().st_size > 1000
            response = lp_client.get('/static/' + story['audio'], headers={'Range': 'bytes=0-99'})
            assert response.status_code == 206
            assert len(response.data) == 100
            assert response.content_type.startswith('audio/')


def test_player_does_not_call_tts_or_browser_speech(lp_client):
    script = lp_client.get('/static/landing/landing.js').get_data(as_text=True)
    assert 'speechSynthesis' not in script
    assert 'SpeechSynthesisUtterance' not in script
    assert 'fetch(' not in script
    assert 'new Audio()' in script
