"""Public LP with selected database stories exported for fast, anonymous previews."""

import json
from pathlib import Path
from flask import Blueprint, current_app, render_template, request, url_for
from markupsafe import Markup
from .landing_copy import COPY
from .services.languages import LANGUAGES

bp = Blueprint("landing", __name__)

@bp.get("/")
def index():
    language = request.args.get('lang')
    if language not in LANGUAGES:
        language = next((tag.lower().replace('_', '-').split('-')[0]
                         for tag, quality in request.accept_languages
                         if quality > 0 and tag.lower().replace('_', '-').split('-')[0] in LANGUAGES),
                        'en' if request.headers.get('Accept-Language') else 'ja')
    copy = COPY[language]
    catalog_file = Path(__file__).with_name('landing_samples.json')
    catalog = json.loads(catalog_file.read_text(encoding='utf-8')) if catalog_file.exists() else []
    stories = []
    for sample in catalog:
        story = dict(sample['languages'][language])
        story.update(number=f'{len(stories)+1:02d}', icon=sample['icon'],
                     place=sample['places'][language], sources=sample['sources'],
                     audio=url_for('static', filename=story['audio']) if story.get('audio') else None)
        stories.append(story)
    response = current_app.make_response(render_template(
        'landing.html', stories=stories, language=language, language_options=LANGUAGES,
        t=lambda key: Markup(copy[key]),
        player_copy={key: str(copy[key]) for key in (
            'play', 'listen', 'ready', 'stop', 'stopped', 'playing', 'ended', 'audio_error', 'selected', 'next', 'browser_voice')},
    ))
    response.headers['Content-Language'] = language
    response.vary.add('Accept-Language')
    return response


from .landing_export import prepare_samples
bp.cli.command('prepare-samples')(prepare_samples)
