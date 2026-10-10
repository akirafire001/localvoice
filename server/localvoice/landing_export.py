"""Explicitly export selected knowledge, never users' histories or private audio."""
import json
from pathlib import Path
import click
from flask import current_app
from sqlalchemy import select


def prepare_samples():
    """Export the LP's three DB stories and prepare six-language audio once."""
    from .db import session_scope
    from .landing_translations import SELECTIONS
    from .models import KnowledgeItem
    from .models import AudioAsset
    from .services import translation, voice
    from .util import now

    result = []
    with session_scope(current_app) as db:
        provider = voice.get_provider()
        if provider is None or provider.name == 'silent':
            raise click.ClickException('Configure a real TTS provider to prepare the LP audio.')
        for spec in SELECTIONS:
            item = db.scalar(select(KnowledgeItem).where(KnowledgeItem.canonical_key == spec['key']))
            if item is None or item.review_status == 'suspended' or (item.valid_until and item.valid_until <= now()):
                raise click.ClickException(f"Selected story missing, suspended or expired: {spec['slug']}")
            if item.content_version != spec['version']:
                raise click.ClickException(f"Source changed; update translations first: {spec['slug']}")
            sample = {'key': item.canonical_key, 'content_version': item.content_version,
                      'review_status': item.review_status, 'icon': spec['icon'], 'places': spec['places'],
                      'sources': [{'title': s.title, 'url': s.url} for s in item.sources if s.url and s.url.startswith('https://')],
                      'languages': {}}
            if not sample['sources']:
                raise click.ClickException(f"No sources for {spec['slug']}")
            from .services.languages import LANGUAGES
            for language in LANGUAGES:
                story = translation.localized_story(item, language) if language in ('ja', 'en') else spec['translations'][language]
                if not story:
                    raise click.ClickException(f"Missing {language} text for {spec['slug']}")
                text = translation.spoken_text(story, 'detailed')
                # Mandarin Chirp's sentence parser can treat full-width stops as one long sentence.
                synthesis_text = text.replace('。', '. ').replace('？', '? ').replace('！', '! ') if language == 'zh' else text
                asset, _ = voice.get_or_create_asset(db, text=synthesis_text, language=language,
                    voice_profile_id=f'{language}-default', scope='shared', content_version=item.content_version,
                    knowledge_item_id=item.id, valid_until=item.valid_until)
                # A background worker may be preparing the same shared cache entry.
                # Wait for its row lock and refresh instead of reporting a false failure.
                db.execute(select(AudioAsset).where(AudioAsset.id == asset.id).with_for_update())
                db.refresh(asset)
                if asset.status != 'ready':
                    voice.synthesize_asset(db, asset, provider)
                if asset.status != 'ready':
                    raise click.ClickException(f"Audio preparation failed: {spec['slug']}/{language}")
                relative = f"landing/samples/{spec['slug']}/{language}.mp3"
                destination = Path(current_app.static_folder) / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(voice.read_audio(asset))
                sample['languages'][language] = {'title': story['title'], 'body': text,
                                                'detail': story['body'], 'audio': relative}
                click.echo(f"Prepared {spec['slug']}/{language}")
            result.append(sample)
        catalog_file = Path(__file__).with_name('landing_samples.json')
        temporary = catalog_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(catalog_file)
