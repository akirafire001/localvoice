(() => {
  'use strict';
  const stories = JSON.parse(document.getElementById('demo-stories').textContent);
  const copy = JSON.parse(document.getElementById('player-copy').textContent);
  const languagePicker = document.getElementById('page-language');
  languagePicker.addEventListener('change', () => languagePicker.form.requestSubmit());
  document.querySelector('.language-apply').hidden = true;
  if (!stories.length) return;

  const choices = [...document.querySelectorAll('[data-story]')];
  const toggle = document.getElementById('speech-toggle');
  const label = document.getElementById('speech-label');
  const status = document.getElementById('speech-status');
  const symbol = document.getElementById('speech-symbol');
  const audio = new Audio();
  audio.preload = 'none';
  let selected = 0;
  let playback = 0;
  let active = false;

  function reset(message = copy.ready) {
    active = false;
    toggle.setAttribute('aria-pressed', 'false');
    toggle.setAttribute('aria-label', copy.play);
    symbol.textContent = '▶';
    label.textContent = copy.listen;
    status.textContent = message;
  }

  function stop(message = copy.stopped) {
    playback += 1;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    reset(message);
  }

  function selectStory(index) {
    stop(copy.selected);
    selected = index;
    const story = stories[index];
    for (const choice of choices) choice.setAttribute('aria-pressed', String(Number(choice.dataset.story) === index));
    for (const field of ['title', 'body', 'place', 'detail']) document.getElementById(`story-${field}`).textContent = story[field];
    document.getElementById('story-number').textContent = `${story.number} / ${String(stories.length).padStart(2, '0')}`;
    document.getElementById('story-details').open = false;
    const sourceList = document.getElementById('story-sources');
    sourceList.replaceChildren();
    for (const source of story.sources) {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.textContent = source.title;
      link.href = source.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      item.append(link);
      sourceList.append(item);
    }
  }

  for (const choice of choices) choice.addEventListener('click', () => selectStory(Number(choice.dataset.story)));
  document.querySelector('.story-choices').hidden = false;
  document.querySelector('.demo-player').hidden = false;
  document.getElementById('next-story').addEventListener('click', () => selectStory((selected + 1) % stories.length));

  toggle.addEventListener('click', async () => {
    if (active) {
      stop();
      return;
    }
    const token = ++playback;
    active = true;
    toggle.setAttribute('aria-pressed', 'true');
    toggle.setAttribute('aria-label', copy.stop);
    symbol.textContent = '■';
    label.textContent = copy.playing;
    status.textContent = copy.ready;
    audio.src = stories[selected].audio;
    try {
      await audio.play();
      if (token === playback) status.textContent = copy.playing;
    } catch {
      if (token === playback) reset(copy.audio_error);
    }
  });

  audio.addEventListener('ended', () => {
    if (active) reset(copy.ended);
  });
  audio.addEventListener('error', () => {
    if (active) reset(copy.audio_error);
  });
  window.addEventListener('pagehide', () => stop());
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && active) stop();
  });
})();
