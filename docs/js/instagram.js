const root = new URL('./', document.baseURI);
const next = document.querySelector('#next-post');
const imageButton = document.querySelector('#post-image-button');
const imageStatus = document.querySelector('#image-status');
const position = document.querySelector('#feed-position');
const error = document.querySelector('#feed-error');
const retry = document.querySelector('#retry-feed');
const track = document.querySelector('.post-track');
const currentPost = document.querySelector('.feed-post');
let posters = [];
let order = [];
let index = -1;
let upcoming = null;
let busy = false;

// Use the visitor's local clock, including after returning from a background tab.
const clockFormat = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });
function updateClock() {
  document.querySelector('#phone-clock').textContent = clockFormat.format(new Date());
}
updateClock();
setInterval(updateClock, 1000);
document.addEventListener('visibilitychange', updateClock);

function shuffle(items) {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

function assetURL(asset) {
  const url = new URL(asset.src, root);
  if (url.origin !== root.origin || !url.pathname.startsWith(`${root.pathname}posters/`)) {
    throw new Error('Invalid poster URL');
  }
  url.searchParams.set('v', asset.sha256.slice(0, 8));
  return url.href;
}

function prepare(nextOrder, nextIndex) {
  const slot = { order: nextOrder, index: nextIndex, poster: nextOrder[nextIndex], image: new Image() };
  slot.image.className = 'post-image';
  slot.image.decoding = 'async';
  slot.image.fetchPriority = 'high';
  slot.image.src = assetURL(slot.poster.images.texture);
  // decode() waits for both download and pixels; no empty frame during a slide.
  slot.ready = slot.image.decode().then(() => slot, () => {
    slot.image = null;
    return slot; // A failed image remains a traversable post with an error message.
  });
  return slot;
}

function preloadNext() {
  let nextOrder = order;
  let nextIndex = index + 1;
  if (nextIndex >= order.length) {
    nextOrder = shuffle(posters);
    if (nextOrder.length > 1 && nextOrder[0].id === order[index]?.id) {
      [nextOrder[0], nextOrder[1]] = [nextOrder[1], nextOrder[0]];
    }
    nextIndex = 0;
  }
  upcoming = prepare(nextOrder, nextIndex);
}

function fillPost(post, slot, live = false) {
  const title = slot.poster.metadata.title || 'Affiche sans titre';
  post.querySelector('.post-title').textContent = title;
  post.querySelector('.post-author').textContent = slot.poster.metadata.author || 'Auteurice non renseigné·e';
  const oldImage = post.querySelector('.post-image');
  const status = post.querySelector('.image-status');
  if (slot.image) {
    slot.image.alt = `Affiche de ${title}${slot.poster.metadata.author ? `, ${slot.poster.metadata.author}` : ''}`;
    slot.image.hidden = false;
    if (live) slot.image.id = 'post-image';
    oldImage.replaceWith(slot.image);
    status.hidden = true;
  } else {
    oldImage.hidden = true;
    oldImage.removeAttribute('src');
    status.hidden = false;
    status.textContent = 'Image indisponible. Cliquez pour passer à la suivante.';
  }
  if (live) {
    imageButton.dataset.posterId = slot.poster.id;
    imageButton.setAttribute('aria-label', `Affiche « ${title} ». Afficher l’affiche suivante`);
  }
}

function setBusy(value) {
  busy = value;
  // Keep keyboard focus on either control while ignoring repeat clicks.
  next.setAttribute('aria-disabled', String(value));
  imageButton.setAttribute('aria-disabled', String(value));
  track.parentElement.setAttribute('aria-busy', String(value));
}

async function slideTo(slot) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
    fillPost(currentPost, slot, true);
    return;
  }
  const preview = currentPost.cloneNode(true);
  preview.inert = true;
  preview.setAttribute('aria-hidden', 'true');
  for (const node of preview.querySelectorAll('[id], [aria-live]')) {
    node.removeAttribute('id');
    node.removeAttribute('aria-live');
  }
  fillPost(preview, slot);
  track.append(preview);
  track.classList.add('is-moving');
  const animation = track.animate([
    { transform: 'translateY(0)', offset: 0, easing: 'ease-out' },
    { transform: 'translateY(4px)', offset: .1, easing: 'cubic-bezier(.45, 0, .15, 1)' },
    { transform: 'translateY(calc(-100% + 8px))', offset: .86, easing: 'steps(2, end)' },
    { transform: 'translateY(-100%)', offset: .98 },
    { transform: 'translateY(-100%)', offset: 1 },
  ], { duration: 640, fill: 'forwards' });
  try {
    await animation.finished;
  } finally {
    // Commit and remove the animation in the same frame, retaining the decoded image.
    fillPost(currentPost, slot, true);
    animation.cancel();
    preview.remove();
    track.classList.remove('is-moving');
  }
}

async function advance() {
  if (!upcoming || busy) return;
  setBusy(true);
  const slot = upcoming;
  position.textContent = 'Préparation de l’affiche suivante…';
  try {
    await slot.ready;
    await slideTo(slot);
    order = slot.order;
    index = slot.index;
    preloadNext();
    position.textContent = `Affiche ${index + 1} sur ${order.length} · Ordre aléatoire`;
  } finally {
    setBusy(false);
  }
}

async function load() {
  next.disabled = true;
  imageButton.disabled = true;
  error.hidden = true;
  retry.hidden = true;
  position.textContent = 'Chargement du fil…';
  try {
    const response = await fetch(new URL('./data/posters.json', root), { cache: 'no-cache' });
    if (!response.ok) throw new Error('Catalogue unavailable');
    const data = await response.json();
    if (data.schema_version !== 2 || !Array.isArray(data.posters) || !data.posters.length) throw new Error('Invalid catalogue');
    const ids = new Set();
    for (const poster of data.posters) {
      if (!poster.id || ids.has(poster.id) || !poster.metadata || !poster.images?.texture || typeof poster.images.texture.sha256 !== 'string') throw new Error('Invalid poster');
      assetURL(poster.images.texture);
      ids.add(poster.id);
    }
    posters = data.posters;
    order = shuffle(posters);
    index = 0;
    const first = await prepare(order, index).ready;
    preloadNext();
    fillPost(currentPost, first, true);
    position.textContent = `Affiche 1 sur ${order.length} · Ordre aléatoire`;
    next.disabled = false;
    imageButton.disabled = false;
  } catch {
    error.textContent = 'Le fil n’a pas pu être chargé. Réessayez pour découvrir les affiches.';
    error.hidden = false;
    retry.hidden = false;
    position.textContent = 'Fil indisponible';
    imageStatus.textContent = 'Les affiches sont momentanément indisponibles.';
  }
}

next.addEventListener('click', advance);
imageButton.addEventListener('click', advance);
retry.addEventListener('click', load);
load();
