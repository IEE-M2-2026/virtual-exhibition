const root = new URL('./', document.baseURI);
const next = document.querySelector('#next-post');
const imageButton = document.querySelector('#post-image-button');
const image = document.querySelector('#post-image');
const imageStatus = document.querySelector('#image-status');
const position = document.querySelector('#feed-position');
const error = document.querySelector('#feed-error');
const retry = document.querySelector('#retry-feed');
let posters = [];
let order = [];
let index = -1;
let requestId = 0;

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

function advance() {
  if (!posters.length) return;
  if (index + 1 >= order.length) {
    const previousId = order[index]?.id;
    order = shuffle(posters);
    // A new cycle cannot immediately repeat the last poster of the previous one.
    if (order.length > 1 && order[0].id === previousId) {
      [order[0], order[1]] = [order[1], order[0]];
    }
    index = -1;
  }
  index += 1;
  const poster = order[index];
  const title = poster.metadata.title || 'Affiche sans titre';
  document.querySelector('#post-title').textContent = title;
  document.querySelector('#post-author').textContent = poster.metadata.author || 'Auteurice non renseigné·e';
  imageButton.dataset.posterId = poster.id;
  imageButton.setAttribute('aria-label', `Affiche « ${title} ». Afficher l’affiche suivante`);
  position.textContent = `Affiche ${index + 1} sur ${order.length} · Ordre aléatoire`;
  const token = ++requestId;
  image.hidden = true;
  image.removeAttribute('src');
  imageStatus.hidden = false;
  imageStatus.textContent = 'Chargement de l’affiche…';
  const pending = new Image();
  pending.onload = () => {
    if (token !== requestId) return;
    image.src = pending.src;
    image.alt = `Affiche de ${title}${poster.metadata.author ? `, ${poster.metadata.author}` : ''}`;
    image.hidden = false;
    imageStatus.hidden = true;
  };
  pending.onerror = () => {
    if (token !== requestId) return;
    imageStatus.textContent = 'Image indisponible. Cliquez pour passer à la suivante.';
  };
  pending.src = assetURL(poster.images.texture);
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
    order = [];
    index = -1;
    advance();
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
