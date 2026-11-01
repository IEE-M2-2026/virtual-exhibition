const siteRoot = new URL('./', document.baseURI);
const grid = document.querySelector('#poster-grid');
const count = document.querySelector('#poster-count');
const sortControl = document.querySelector('#sort-order');
const status = document.querySelector('#gallery-status');
const errorPanel = document.querySelector('#gallery-error');
const dialog = document.querySelector('#poster-dialog');
const viewport = document.querySelector('#detail-viewport');
const detailImage = document.querySelector('#detail-image');
const detailStatus = document.querySelector('#detail-status');
const zoomButton = document.querySelector('#zoom-button');
const collator = new Intl.Collator('fr', { numeric: true, sensitivity: 'base' });

let posters = [];
let orderedPosters = [];
let randomPosters = [];
let selectedId = null;
let sortOrder = 'random';
let returnFocus = null;
let imageRequest = 0;

function imageURL(asset) {
  const url = new URL(asset.src, siteRoot);
  if (url.origin !== siteRoot.origin || !url.pathname.startsWith(`${siteRoot.pathname}posters/`)) {
    throw new Error('Invalid poster asset URL');
  }
  url.searchParams.set('v', asset.sha256.slice(0, 8));
  return url.href;
}

function titleOf(poster) {
  return poster.metadata.title || 'Affiche sans titre';
}

function makeCard(poster, index) {
  const card = document.createElement('li');
  card.className = 'poster-card';
  const link = document.createElement('a');
  link.className = 'poster-link';
  link.href = `#poster=${encodeURIComponent(poster.id)}`;
  link.dataset.posterId = poster.id;
  link.setAttribute('aria-label', `Voir l’affiche « ${titleOf(poster)} »${poster.metadata.author ? `, ${poster.metadata.author}` : ''}`);
  link.addEventListener('click', (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    returnFocus = link;
    // A repeated click on an already selected hash must still open the viewer.
    if (location.hash === link.hash) showPoster(poster.id);
  });

  const frame = document.createElement('div');
  frame.className = 'poster-image';
  const image = document.createElement('img');
  const { thumbnail, texture } = poster.images;
  image.src = imageURL(thumbnail);
  image.srcset = `${imageURL(thumbnail)} ${thumbnail.width}w, ${imageURL(texture)} ${texture.width}w`;
  image.sizes = '(min-width: 1280px) 20vw, (min-width: 1024px) 25vw, (min-width: 768px) 33vw, (min-width: 360px) 50vw, 100vw';
  image.width = thumbnail.width;
  image.height = thumbnail.height;
  image.alt = ''; // The link and adjacent heading identify this artwork once.
  image.loading = index < 5 ? 'eager' : 'lazy';
  image.decoding = 'async';
  image.addEventListener('error', () => {
    image.hidden = true;
    frame.classList.add('image-unavailable');
    frame.textContent = 'Image indisponible';
  }, { once: true });
  frame.append(image);

  const caption = document.createElement('div');
  caption.className = 'poster-caption';
  const title = document.createElement('h2');
  title.className = 'poster-title';
  title.textContent = titleOf(poster);
  caption.append(title);
  if (poster.metadata.author) {
    const author = document.createElement('p');
    author.className = 'poster-author';
    author.textContent = poster.metadata.author;
    caption.append(author);
  }
  link.append(frame, caption);
  card.append(link);
  return card;
}

function renderGrid() {
  sortControl.value = sortOrder;
  orderedPosters = sortOrder === 'random' ? [...randomPosters] : [...posters];
  if (sortOrder !== 'random') {
    const sortDirection = sortOrder === 'title-asc' ? 1 : -1;
    orderedPosters.sort((a, b) => sortDirection * collator.compare(titleOf(a), titleOf(b)));
  }
  grid.replaceChildren(...orderedPosters.map(makeCard));
  count.textContent = `Toutes les affiches (${posters.length})`;
}

function shuffle(items) {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

function resetZoom() {
  viewport.classList.remove('is-zoomed');
  viewport.scrollTo(0, 0);
  zoomButton.setAttribute('aria-pressed', 'false');
  zoomButton.textContent = 'Agrandir';
}

function showPoster(id) {
  const index = orderedPosters.findIndex((poster) => poster.id === id);
  if (index < 0) return false;
  const poster = orderedPosters[index];
  selectedId = id;
  resetZoom();
  document.querySelector('#detail-title').textContent = titleOf(poster);
  const author = document.querySelector('#detail-author');
  author.textContent = poster.metadata.author || '';
  author.hidden = !poster.metadata.author;
  const year = document.querySelector('#detail-year');
  year.textContent = poster.metadata.premiere_year ? `Création scénique · ${poster.metadata.premiere_year}` : '';
  year.hidden = !poster.metadata.premiere_year;
  document.querySelector('#detail-position').textContent = `${index + 1} / ${orderedPosters.length}`;
  document.querySelector('#previous-poster').disabled = orderedPosters.length < 2;
  document.querySelector('#next-poster').disabled = orderedPosters.length < 2;

  if (!dialog.open) {
    if (!returnFocus) returnFocus = document.activeElement;
    dialog.showModal();
    document.body.classList.add('dialog-open');
    document.querySelector('#close-dialog').focus();
  }

  const request = ++imageRequest;
  detailImage.hidden = true;
  detailImage.removeAttribute('src');
  detailStatus.hidden = false;
  detailStatus.textContent = 'Chargement de l’affiche…';
  zoomButton.disabled = true;
  const image = new Image();
  image.onload = () => {
    if (request !== imageRequest || !dialog.open) return;
    detailImage.src = image.src;
    detailImage.alt = `Affiche de ${titleOf(poster)}`;
    detailImage.width = poster.images.detail.width;
    detailImage.height = poster.images.detail.height;
    detailImage.hidden = false;
    detailStatus.hidden = true;
    zoomButton.disabled = false;
  };
  image.onerror = () => {
    if (request !== imageRequest || !dialog.open) return;
    detailStatus.textContent = 'Cette affiche n’a pas pu être chargée. Fermez-la puis réessayez.';
  };
  image.src = imageURL(poster.images.detail);
  return true;
}

function closeViewer(clearHash = true) {
  imageRequest += 1;
  selectedId = null;
  if (clearHash && location.hash.startsWith('#poster=')) {
    history.replaceState(null, '', `${location.pathname}${location.search}#les-affiches`);
  }
  if (dialog.open) dialog.close();
  document.body.classList.remove('dialog-open');
  if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
  returnFocus = null;
}

function syncHash() {
  if (location.hash.startsWith('#poster=')) {
    let id;
    try { id = decodeURIComponent(location.hash.slice(8)); } catch { id = ''; }
    if (showPoster(id)) return;
  }
  if (dialog.open) closeViewer(false);
}

function stepPoster(direction) {
  const index = orderedPosters.findIndex((poster) => poster.id === selectedId);
  const next = orderedPosters[(index + direction + orderedPosters.length) % orderedPosters.length];
  if (next) {
    history.replaceState(null, '', `#poster=${encodeURIComponent(next.id)}`);
    showPoster(next.id);
  }
}

async function loadGallery() {
  errorPanel.hidden = true;
  status.hidden = false;
  status.textContent = 'Chargement des affiches…';
  sortControl.disabled = true;
  try {
    const response = await fetch(new URL('./data/posters.json', siteRoot), { cache: 'no-cache' });
    if (!response.ok) throw new Error(`Catalogue: HTTP ${response.status}`);
    const catalog = await response.json();
    if (catalog.schema_version !== 2 || !Array.isArray(catalog.posters)) throw new Error('Invalid catalogue');
    for (const poster of catalog.posters) {
      if (typeof poster.id !== 'string' || !poster.metadata) throw new Error('Invalid poster');
      for (const variant of ['thumbnail', 'texture', 'detail']) imageURL(poster.images[variant]);
    }
    posters = catalog.posters;
    // Shuffle once per load; reading, closing and sorting never move cards at random.
    randomPosters = shuffle(posters);
    renderGrid();
    status.hidden = posters.length > 0;
    status.textContent = posters.length ? '' : 'Les affiches seront bientôt disponibles.';
    sortControl.disabled = posters.length < 2;
    syncHash();
  } catch (error) {
    status.hidden = true;
    errorPanel.hidden = false;
    document.querySelector('#gallery-error-message').textContent = 'Les affiches n’ont pas pu être chargées. Veuillez réessayer.';
    console.error('Gallery loading failed:', error);
  }
}

sortControl.addEventListener('change', () => {
  sortOrder = sortControl.value;
  renderGrid();
});
document.querySelector('#retry-button').addEventListener('click', loadGallery);
document.querySelector('#close-dialog').addEventListener('click', () => closeViewer());
document.querySelector('#previous-poster').addEventListener('click', () => stepPoster(-1));
document.querySelector('#next-poster').addEventListener('click', () => stepPoster(1));
zoomButton.addEventListener('click', () => {
  const zoomed = viewport.classList.toggle('is-zoomed');
  zoomButton.setAttribute('aria-pressed', String(zoomed));
  zoomButton.textContent = zoomed ? 'Vue entière' : 'Agrandir';
});
dialog.addEventListener('cancel', (event) => {
  event.preventDefault();
  closeViewer();
});
dialog.addEventListener('keydown', (event) => {
  if (viewport.classList.contains('is-zoomed')) return; // Arrow keys scroll the zoomed artwork.
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault();
    stepPoster(event.key === 'ArrowLeft' ? -1 : 1);
  }
});
dialog.addEventListener('click', (event) => {
  if (event.target !== dialog) return;
  const bounds = dialog.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeViewer();
});
window.addEventListener('hashchange', syncHash);
loadGallery();
