import assert from 'node:assert/strict';

/** Exercise the actual injected GLSL and the Blender/HDRLoader cube convention. */
export async function checkHallLighting(page) {
  const results = await page.evaluate(async () => {
    const THREE = await import('three');
    const { createGarageMaterial } = await import('./js/garage-material.js');
    const { HDRCubeTextureLoader } = await import('three/addons/loaders/HDRCubeTextureLoader.js');
    const { HDRLoader } = await import('three/addons/loaders/HDRLoader.js');
    const manifest = await (await fetch('./models/garage/manifest.json')).json();
    const settings = manifest.lighting.probe;
    const renderer = new THREE.WebGLRenderer();
    renderer.setSize(1, 1);
    const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.FloatType });
    const scene = new THREE.Scene(), camera = new THREE.Camera();
    const base = createGarageMaterial();
    const injected = { uniforms: {}, vertexShader: THREE.ShaderLib.standard.vertexShader,
      fragmentShader: THREE.ShaderLib.standard.fragmentShader };
    base.onBeforeCompile(injected);
    const begin = injected.fragmentShader.indexOf('varying vec3 vGarageWorldPosition;');
    const end = injected.fragmentShader.indexOf('#include <dithering_pars_fragment>', begin);
    if (begin < 0 || end < 0) throw new Error('Projection shader not found');
    const uniforms = {
      ...injected.uniforms,
      point: { value: new THREE.Vector3() }, ray: { value: new THREE.Vector3() },
    };
    uniforms.garageProbePosition.value.fromArray(settings.position);
    uniforms.garageBoxMin.value.fromArray(settings.box_min);
    uniforms.garageBoxMax.value.fromArray(settings.box_max);
    const vertexShader = 'uniform vec3 point; varying vec3 vGarageWorldPosition; void main(){ vGarageWorldPosition=point; gl_Position=vec4(position.xy,0.0,1.0); }';
    const material = new THREE.ShaderMaterial({ uniforms, vertexShader,
      fragmentShader: `${injected.fragmentShader.slice(begin, end)}
        uniform vec3 ray; void main(){gl_FragColor=vec4(garageBoxDirection(normalize(ray)),1.0);}` });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
    plane.frustumCulled = false;
    scene.add(plane);
    const output = new Float32Array(4);
    function render() {
      renderer.setRenderTarget(target);
      renderer.render(scene, camera);
      renderer.readRenderTargetPixels(target, 0, 0, 1, 1, output);
      return Array.from(output.slice(0, 3));
    }
    const box = new THREE.Box3(uniforms.garageBoxMin.value, uniforms.garageBoxMax.value);
    let projectionError = 0;
    for (const [position, direction] of [
      [[0, 3, 0], [1, 0, 0]], [[10, 1, 0], [0.5, 1, 0.1]],
      [[3, 2, 4], [0, -1, 0]], [[22, 3, 0], [1, 0, 0]], [[-8, 5, 6], [-1, 0.2, -1]],
    ]) {
      uniforms.point.value.fromArray(position);
      uniforms.ray.value.fromArray(direction).normalize();
      const origin = uniforms.point.value.clone().clamp(box.min.clone().addScalar(0.001), box.max.clone().addScalar(-0.001));
      const expected = new THREE.Ray(origin, uniforms.ray.value).intersectBox(box, new THREE.Vector3()).sub(uniforms.garageProbePosition.value).toArray();
      const actual = render();
      projectionError = Math.max(projectionError, ...actual.map((value, i) => Math.abs(value - expected[i])));
    }
    material.dispose();

    // Compare GPU lookup against independent camera-ray projection into each
    // original HDR face. Off-centre samples catch mirrored or inverted faces.
    const cube = await new HDRCubeTextureLoader().setDataType(THREE.FloatType)
      .loadAsync(settings.faces.map((face) => face.src));
    const cubeMaterial = new THREE.ShaderMaterial({
      uniforms: { ...uniforms, cube: { value: cube } }, vertexShader,
      fragmentShader: `uniform samplerCube cube; uniform vec3 ray;
        void main(){ gl_FragColor=textureCube(cube,vec3(-ray.x,ray.yz)); }`,
    });
    plane.material = cubeMaterial;
    let cubeError = 0, hdrPeak = 0;
    for (let i = 0; i < settings.faces.length; i++) {
      const face = settings.faces[i], data = cube.images[i].image.data, size = settings.face_size;
      const forward = new THREE.Vector3(...face.world_forward), up = new THREE.Vector3(...face.world_up);
      const right = new THREE.Vector3().crossVectors(forward, up);
      for (const [x, y] of [[127, 383], [255, 255], [383, 127]]) {
        const px = Math.floor(x * size / 512), py = Math.floor(y * size / 512);
        const u = 2 * (px + 0.5) / size - 1, v = 1 - 2 * (py + 0.5) / size;
        uniforms.ray.value.copy(forward).addScaledVector(right, u).addScaledVector(up, v).normalize();
        const actual = render(), offset = (py * size + px) * 4;
        cubeError = Math.max(cubeError, ...actual.map((value, channel) => Math.abs(value - data[offset + channel])));
      }
      for (let j = 0; j < data.length; j++) if (j % 4 !== 3) hdrPeak = Math.max(hdrPeak, data[j]);
    }
    const skyBytes = await (await fetch(manifest.lighting.sky.texture.src)).arrayBuffer();
    const sky = new HDRLoader().setDataType(THREE.FloatType).parse(skyBytes);
    let skyPeak = 0;
    for (let j = 0; j < sky.data.length; j++) if (j % 4 !== 3) skyPeak = Math.max(skyPeak, sky.data[j]);
    cube.dispose();
    for (const image of cube.images) image.dispose();
    cubeMaterial.dispose(); base.dispose(); plane.geometry.dispose(); target.dispose();
    renderer.dispose(); renderer.forceContextLoss();
    return { projectionError, cubeError, hdrPeak, skyPeak };
  });
  assert(results.projectionError < 0.0001, `Box projection GPU error: ${results.projectionError}`);
  assert(results.cubeError < 0.005, `Cube face orientation/sampling error: ${results.cubeError}`);
  assert(results.hdrPeak > 1 && results.skyPeak > 1, 'Capture and sky preserve HDR radiance');
  console.log('Lighting GPU checks:', results);
}
