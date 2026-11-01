import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';
import { HDRCubeTextureLoader } from 'three/addons/loaders/HDRCubeTextureLoader.js';
import { createGarageMaterial, setGarageSurface, setGarageAO, setGarageProbe } from './garage-material.js';

const siteRoot = new URL('./', document.baseURI);
const canvas = document.querySelector('#hall-canvas');
const stage = document.querySelector('#hall-stage');
const loading = document.querySelector('#hall-loading');
const loadingLabel = document.querySelector('#hall-loading-label');
const progress = document.querySelector('#hall-progress');
const notice = document.querySelector('#hall-notice');
const select = document.querySelector('#hall-select');
const readLink = document.querySelector('#hall-read');
const title = document.querySelector('#hall-title');
const author = document.querySelector('#hall-author');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const keys = new Set();
const garageMeshes = [];
const panels = [];
const raycaster = new THREE.Raycaster();
const loader = new GLTFLoader();
const textureLoader = new THREE.TextureLoader();
const direction = new THREE.Vector3();
const euler = new THREE.Euler(0, 0, 0, 'YXZ');

let renderer, scene, camera, garageMaterial, manifest;
let yaw = 0, pitch = 0, transition = null, dirty = true, ready = false, contextLost = false;
let selected = -1, pointer = null, previousTime = 0, loadedParts = 0;
let highTexture = null, highIndex = -1, requestedHigh = -1, highRequest = 0;
let walkCheckTime = 0;
let skyTarget, probeTarget, hdrSkyReady = false, probeReady = false;

function assetURL(asset) {
  const url = new URL(asset.src, siteRoot);
  if (url.origin !== siteRoot.origin || !url.pathname.startsWith(siteRoot.pathname)) throw new Error('Invalid local asset');
  url.searchParams.set('v', asset.sha256.slice(0, 8));
  return url.href;
}

async function fetchJSON(path) {
  const response = await fetch(new URL(path, siteRoot), { cache: 'no-cache' });
  if (!response.ok) throw new Error(`Unable to load ${path}: ${response.status}`);
  return response.json();
}

function fatal(message, error) {
  ready = false;
  stage.dataset.state = 'error';
  loading.hidden = true;
  document.querySelector('#hall-error-message').textContent = message;
  document.querySelector('#hall-error').hidden = false;
  for (const control of document.querySelectorAll('#hall-controls button, #hall-select')) control.disabled = true;
  if (error) console.error('3D hall:', error);
}

function warn(message) {
  notice.textContent = message;
  notice.hidden = false;
}

function configureTexture(texture, color = false, gltf = false) {
  texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  texture.flipY = !gltf;
  texture.wrapS = texture.wrapT = gltf ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping;
  texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  return texture;
}

function createLighting() {
  const settings = manifest.lighting;
  scene.background = new THREE.Color(0xb8c7d5);
  scene.fog = new THREE.FogExp2(settings.fog.color, settings.fog.density);
  renderer.toneMappingExposure = settings.exposure;
  scene.add(new THREE.HemisphereLight(settings.ambient.sky, settings.ambient.ground, settings.ambient.intensity));
  const sun = new THREE.DirectionalLight(settings.sun.color, settings.sun.intensity);
  sun.position.fromArray(settings.sun.position);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -24, right: 24, top: 18, bottom: -18, near: 0.5, far: 65 });
  sun.shadow.normalBias = 0.035;
  sun.shadow.bias = -0.0002;
  sun.target.position.set(0, 0, 0);
  scene.add(sun, sun.target);
  // Lightweight fallback while the HDR sky and interior capture stream in.
  const environment = new THREE.Scene();
  environment.background = new THREE.Color(0xc6d5e5);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshBasicMaterial({ color: 0x827c72, side: THREE.DoubleSide }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -8;
  environment.add(ground);
  const generator = new THREE.PMREMGenerator(renderer);
  skyTarget = generator.fromScene(environment, 0.04, 0.1, 100);
  scene.environment = skyTarget.texture;
  scene.environmentIntensity = settings.sky.intensity;
  generator.dispose();
  ground.geometry.dispose();
  ground.material.dispose();
}

async function loadHDRSky() {
  const texture = await new HDRLoader().loadAsync(assetURL(manifest.lighting.sky.texture));
  texture.mapping = THREE.EquirectangularReflectionMapping;
  const generator = new THREE.PMREMGenerator(renderer);
  const next = generator.fromEquirectangular(texture);
  generator.dispose();
  scene.background = texture;
  scene.backgroundIntensity = manifest.lighting.sky.intensity;
  scene.environment = next.texture;
  skyTarget.dispose();
  skyTarget = next;
  hdrSkyReady = true;
  dirty = true;
}

async function loadReflectionProbe() {
  const settings = manifest.lighting.probe;
  const cube = await new HDRCubeTextureLoader().loadAsync(settings.faces.map(assetURL));
  const generator = new THREE.PMREMGenerator(renderer);
  probeTarget = generator.fromCubemap(cube);
  generator.dispose();
  cube.dispose();
  for (const face of cube.images) face.dispose();
  setGarageProbe(garageMaterial, probeTarget.texture, settings);
  probeReady = true;
  dirty = true;
}

async function loadPart(part) {
  const gltf = await loader.loadAsync(assetURL(part));
  gltf.scene.traverse((object) => {
    if (!object.isMesh) return;
    const old = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of old) material.dispose();
    // All five GLBs reference exactly this same material and GPU texture objects.
    object.material = garageMaterial;
    object.castShadow = object.receiveShadow = true;
    garageMeshes.push(object);
  });
  scene.add(gltf.scene);
  loadedParts += 1;
  stage.dataset.loadedParts = String(loadedParts);
  dirty = true;
}

function createPanels(posters) {
  const columns = Math.ceil(posters.length / 2);
  const spacing = columns > 1 ? 26 / (columns - 1) : 0;
  const backingMaterial = new THREE.MeshStandardMaterial({ color: 0x343735, roughness: 0.92 });
  const geometry = new THREE.PlaneGeometry(1, 1);
  select.add(new Option('Vue d’ensemble', ''));
  posters.forEach((poster, index) => {
    const ratio = poster.images.texture.width / poster.images.texture.height;
    const height = Math.min(3.2, columns > 1 ? spacing * 0.72 / ratio : 3.2);
    const width = height * ratio;
    const side = index % 2 === 0 ? -1 : 1;
    const x = columns > 1 ? 13 - Math.floor(index / 2) * spacing : 0;
    const group = new THREE.Group();
    group.position.set(x, manifest.floor_y + 0.35 + height / 2, side * 5.7);
    group.rotation.y = side === -1 ? 0 : Math.PI;
    const backing = new THREE.Mesh(new THREE.BoxGeometry(width + 0.12, height + 0.12, 0.08), backingMaterial);
    backing.castShadow = backing.receiveShadow = true;
    const material = new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false });
    const image = new THREE.Mesh(geometry, material);
    image.scale.set(width, height, 1);
    image.position.z = 0.045;
    image.userData.posterIndex = index;
    group.add(backing, image);
    scene.add(group);
    const normal = new THREE.Vector3(0, 0, -side);
    panels.push({ poster, image, material, group, normal, thumbnail: null });
    select.add(new Option(`${index + 1}. ${poster.metadata.title || 'Affiche sans titre'}`, String(index)));
  });
}

async function loadThumbnails() {
  // Small batches keep the scene usable on slower connections.
  let failed = false;
  for (let offset = 0; offset < panels.length; offset += 3) {
    await Promise.all(panels.slice(offset, offset + 3).map(async (panel) => {
      try {
        panel.thumbnail = configureTexture(await textureLoader.loadAsync(assetURL(panel.poster.images.thumbnail)), true);
        if (panels[highIndex] !== panel) panel.material.map = panel.thumbnail;
        panel.material.needsUpdate = true;
        dirty = true;
      } catch { failed = true; panel.material.color.set(0x777b75); }
    }));
  }
  return failed;
}

async function upgradePoster(index) {
  if (index === requestedHigh) return;
  requestedHigh = index;
  const request = ++highRequest;
  if (index < 0) {
    if (highIndex >= 0) {
      panels[highIndex].material.map = panels[highIndex].thumbnail;
      panels[highIndex].material.needsUpdate = true;
    }
    highTexture?.dispose();
    highTexture = null;
    highIndex = -1;
    dirty = true;
    return;
  }
  try {
    const texture = configureTexture(await textureLoader.loadAsync(assetURL(panels[index].poster.images.texture)), true);
    if (request !== highRequest) { texture.dispose(); return; }
    if (highIndex >= 0 && highIndex !== index) {
      panels[highIndex].material.map = panels[highIndex].thumbnail;
      panels[highIndex].material.needsUpdate = true;
    }
    highTexture?.dispose();
    highTexture = texture;
    highIndex = index;
    panels[index].material.map = texture;
    panels[index].material.needsUpdate = true;
    dirty = true;
  } catch { warn('Une affiche reste en aperçu. Sa version à plat est accessible avec « Lire l’affiche ».'); }
}

function orientation(position, target) {
  const vector = new THREE.Vector3().subVectors(target, position).normalize();
  return { yaw: Math.atan2(-vector.x, -vector.z), pitch: Math.asin(vector.y) };
}

function moveTo(position, target, immediate = false) {
  const angles = orientation(position, target);
  const endYaw = yaw + THREE.MathUtils.euclideanModulo(angles.yaw - yaw + Math.PI, Math.PI * 2) - Math.PI;
  keys.clear();
  if (immediate || reducedMotion.matches) {
    camera.position.copy(position);
    yaw = endYaw;
    pitch = angles.pitch;
    transition = null;
  } else {
    transition = { start: performance.now(), from: camera.position.clone(), to: position, fromYaw: yaw, toYaw: endYaw, fromPitch: pitch, toPitch: angles.pitch };
  }
  dirty = true;
}

function goToPoster(index, updateHash = true) {
  if (!ready) return;
  selected = index;
  if (index < 0) {
    moveTo(new THREE.Vector3(...manifest.overview.position), new THREE.Vector3(...manifest.overview.target));
    select.value = '';
    title.textContent = 'Le garage';
    author.hidden = true;
    readLink.hidden = true;
    document.querySelector('#hall-position').textContent = `${panels.length} affiches`;
    upgradePoster(-1);
    if (updateHash) history.replaceState(null, '', `${location.pathname}${location.search}`);
  } else {
    const panel = panels[index];
    const position = panel.group.position.clone().addScaledVector(panel.normal, 4.8);
    position.y = manifest.floor_y + 1.7;
    moveTo(position, panel.group.position.clone());
    select.value = String(index);
    title.textContent = panel.poster.metadata.title || 'Affiche sans titre';
    author.textContent = panel.poster.metadata.author || '';
    author.hidden = !panel.poster.metadata.author;
    readLink.href = `./index.html#poster=${encodeURIComponent(panel.poster.id)}`;
    readLink.hidden = false;
    document.querySelector('#hall-position').textContent = `${index + 1} / ${panels.length}`;
    upgradePoster(index);
    if (updateHash) history.replaceState(null, '', `#poster=${encodeURIComponent(panel.poster.id)}`);
  }
}

function syncHash() {
  let id;
  try { id = decodeURIComponent(location.hash.replace(/^#poster=/, '')); } catch { id = ''; }
  const index = panels.findIndex((panel) => panel.poster.id === id);
  goToPoster(index, false);
}

function clampPosition() {
  camera.position.x = THREE.MathUtils.clamp(camera.position.x, ...manifest.walk_bounds.x);
  camera.position.z = THREE.MathUtils.clamp(camera.position.z, ...manifest.walk_bounds.z);
}

function walk(forward, sideways) {
  transition = null;
  camera.position.x += -Math.sin(yaw) * forward + Math.cos(yaw) * sideways;
  camera.position.z += -Math.cos(yaw) * forward - Math.sin(yaw) * sideways;
  clampPosition();
  dirty = true;
}

function bindControls() {
  const movementKeys = new Set(['w', 'a', 's', 'd', 'z', 'q', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);
  canvas.addEventListener('keydown', (event) => {
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    if (ready && movementKeys.has(key)) { event.preventDefault(); keys.add(key); }
  });
  window.addEventListener('keyup', (event) => keys.delete(event.key.length === 1 ? event.key.toLowerCase() : event.key));
  canvas.addEventListener('blur', () => keys.clear());
  window.addEventListener('blur', () => { keys.clear(); pointer = null; });
  canvas.addEventListener('pointerdown', (event) => {
    if (!ready || !event.isPrimary || event.button !== 0) return;
    canvas.focus({ preventScroll: true });
    transition = null;
    pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, moved: false };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!pointer || pointer.id !== event.pointerId) return;
    yaw -= (event.clientX - pointer.x) * 0.003;
    pitch = THREE.MathUtils.clamp(pitch - (event.clientY - pointer.y) * 0.003, -0.8, 0.9);
    pointer.moved ||= Math.hypot(event.clientX - pointer.startX, event.clientY - pointer.startY) > 6;
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    dirty = true;
  });
  canvas.addEventListener('pointerup', (event) => {
    if (!pointer || pointer.id !== event.pointerId) return;
    if (!pointer.moved) {
      const rect = canvas.getBoundingClientRect();
      raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
      const first = raycaster.intersectObjects([...garageMeshes, ...panels.map((panel) => panel.image)], false)[0];
      if (first?.object.userData.posterIndex !== undefined) goToPoster(first.object.userData.posterIndex);
    }
    pointer = null;
  });
  canvas.addEventListener('pointercancel', () => { pointer = null; });
  canvas.addEventListener('wheel', (event) => {
    if (!ready) return;
    event.preventDefault();
    walk(THREE.MathUtils.clamp(-event.deltaY * 0.006, -1.5, 1.5), 0);
  }, { passive: false });
  document.querySelector('#hall-overview').addEventListener('click', () => goToPoster(-1));
  document.querySelector('#hall-next').addEventListener('click', () => goToPoster((selected + 1) % panels.length));
  document.querySelector('#hall-previous').addEventListener('click', () => goToPoster((selected < 0 ? panels.length - 1 : selected - 1 + panels.length) % panels.length));
  select.addEventListener('change', () => goToPoster(select.value === '' ? -1 : Number(select.value)));
  window.addEventListener('hashchange', syncHash);
  if (matchMedia('(pointer: coarse)').matches) document.querySelector('#hall-help').textContent = 'Glisser pour regarder · Utiliser les flèches ou la liste pour passer d’une affiche à l’autre';
}

function tick(time) {
  if (contextLost || document.hidden) { previousTime = time; return; }
  const delta = Math.min((time - previousTime) / 1000 || 0, 0.05);
  previousTime = time;
  if (transition) {
    const amount = Math.min(1, (time - transition.start) / 850);
    const eased = amount * amount * (3 - 2 * amount);
    camera.position.lerpVectors(transition.from, transition.to, eased);
    yaw = THREE.MathUtils.lerp(transition.fromYaw, transition.toYaw, eased);
    pitch = THREE.MathUtils.lerp(transition.fromPitch, transition.toPitch, eased);
    if (amount === 1) transition = null;
    dirty = true;
  }
  if (ready && keys.size) {
    const forward = Number(keys.has('w') || keys.has('z') || keys.has('ArrowUp')) - Number(keys.has('s') || keys.has('ArrowDown'));
    const sideways = Number(keys.has('d') || keys.has('ArrowRight')) - Number(keys.has('a') || keys.has('q') || keys.has('ArrowLeft'));
    const scale = 3.2 * delta / Math.max(1, Math.hypot(forward, sideways));
    walk(forward * scale, sideways * scale);
  }
  if (dirty) {
    camera.quaternion.setFromEuler(euler.set(pitch, yaw, 0, 'YXZ'));
    renderer.render(scene, camera);
    dirty = false;
  }
  // Also refine an artwork approached by walking, without loading every large image.
  if (ready && !transition && time - walkCheckTime > 600) {
    walkCheckTime = time;
    camera.getWorldDirection(direction);
    let nearest = -1, distance = 7;
    panels.forEach((panel, index) => {
      const vector = panel.group.position.clone().sub(camera.position);
      const length = vector.length();
      if (length < distance && vector.normalize().dot(direction) > 0.7) { nearest = index; distance = length; }
    });
    if (nearest >= 0) upgradePoster(nearest);
  }
}

async function start() {
  stage.dataset.state = 'loading';
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(68, 1, 0.08, 120);
  const resize = new ResizeObserver(() => {
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    dirty = true;
  });
  resize.observe(canvas);
  renderer.setAnimationLoop(tick);
  const [garage, catalog] = await Promise.all([fetchJSON('./models/garage/manifest.json'), fetchJSON('./data/posters.json')]);
  if (garage.schema_version !== 2 || catalog.schema_version !== 2) throw new Error('Unsupported manifest');
  manifest = garage;
  createLighting();
  moveTo(new THREE.Vector3(...manifest.overview.position), new THREE.Vector3(...manifest.overview.target), true);
  garageMaterial = createGarageMaterial(manifest.lighting);
  loadingLabel.textContent = 'Ouverture du garage…';
  const initial = manifest.parts.filter((part) => manifest.initial_parts.includes(part.id));
  let initialCompleted = 0;
  const initialProgress = () => { progress.value = ++initialCompleted / (initial.length + 1); };
  await Promise.all([
    textureLoader.loadAsync(assetURL(manifest.textures.albedo)).then((texture) => {
      garageMaterial.map = configureTexture(texture, true, true);
      garageMaterial.needsUpdate = true;
      dirty = true;
      initialProgress();
    }),
    ...initial.map((part) => loadPart(part).then(initialProgress)),
  ]);
  createPanels(catalog.posters);
  bindControls();
  ready = true;
  stage.dataset.state = 'ready';
  loading.hidden = true;
  for (const control of document.querySelectorAll('#hall-controls button, #hall-select')) control.disabled = false;
  if (!panels.length) {
    select.disabled = true;
    document.querySelector('#hall-previous').disabled = true;
    document.querySelector('#hall-next').disabled = true;
  }
  syncHash();
  notice.hidden = false;
  notice.textContent = 'Vous pouvez commencer la visite. Les détails du lieu arrivent…';
  const remaining = manifest.parts.filter((part) => manifest.remaining_parts.includes(part.id));
  const results = await Promise.allSettled([
    loadHDRSky(),
    loadReflectionProbe(),
    ...remaining.map(loadPart),
    textureLoader.loadAsync(assetURL(manifest.textures.normal)).then((texture) => {
      garageMaterial.normalMap = configureTexture(texture, false, true);
      garageMaterial.normalScale.set(0.6, 0.6);
      garageMaterial.needsUpdate = true;
      dirty = true;
    }),
    textureLoader.loadAsync(assetURL(manifest.textures.surface)).then((texture) => {
      const shared = configureTexture(texture, false, true);
      setGarageSurface(garageMaterial, shared);
      dirty = true;
    }),
    textureLoader.loadAsync(assetURL(manifest.textures.ao)).then((texture) => {
      setGarageAO(garageMaterial, configureTexture(texture, false, true));
      dirty = true;
    }),
    loadThumbnails().then((failed) => { if (failed) throw new Error('Poster thumbnail unavailable'); }),
  ]);
  if (results.some((result) => result.status === 'rejected')) {
    warn('La visite est ouverte, mais certains détails n’ont pas pu être chargés. Rechargez la page pour réessayer.');
    stage.dataset.state = 'partial';
  } else {
    notice.hidden = true;
    stage.dataset.state = 'complete';
  }
  progress.value = 1;
}

// Read-only diagnostics for asset-sharing and rendering checks during development.
export function getDiagnostics() {
  return {
    state: stage.dataset.state, parts: loadedParts, posters: panels.length,
    garageMaterials: new Set(garageMeshes.map((mesh) => mesh.material)).size,
    sharedSurface: Boolean(garageMaterial?.roughnessMap && garageMaterial.roughnessMap === garageMaterial.metalnessMap),
    aoChannel: garageMaterial?.aoMap?.channel,
    aoMeshes: garageMeshes.filter((mesh) => mesh.geometry.hasAttribute('uv1') && mesh.material.aoMap === garageMaterial.aoMap).length,
    hdrSky: hdrSkyReady, boxProjectedProbe: probeReady && garageMaterial?.defines?.GARAGE_BOX_PROJECTION === 1,
    sunIntensity: manifest?.lighting.sun.intensity, fogDensity: scene?.fog?.density,
    probeIntensity: garageMaterial?.envMapIntensity,
    roughnessContrast: garageMaterial?.userData.probeUniforms.garageRoughnessContrast.value,
    highResolutionPosterTextures: highTexture ? 1 : 0,
    selected, camera: camera?.position.toArray(), triangles: renderer?.info.render.triangles,
    drawCalls: renderer?.info.render.calls, gpuTextures: renderer?.info.memory.textures,
  };
}

document.querySelector('#hall-retry').addEventListener('click', () => location.reload());
canvas.addEventListener('webglcontextlost', (event) => {
  event.preventDefault();
  contextLost = true;
  fatal('La visite 3D a été interrompue. Réessayez ou retrouvez les affiches en 2D.');
});
document.addEventListener('visibilitychange', () => { keys.clear(); dirty = true; });
start().catch((error) => fatal('La halle 3D n’a pas pu s’ouvrir. Réessayez ou consultez les affiches en 2D.', error));
