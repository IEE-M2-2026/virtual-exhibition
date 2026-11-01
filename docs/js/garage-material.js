import * as THREE from 'three';

/** Shared garage shader: colour/normal/RM on UV0, assembled AO on UV1. */
export function createGarageMaterial() {
  const material = new THREE.MeshStandardMaterial({
    name: 'Garage shared PBR + assembled AO',
    color: 0xffffff, roughness: 0.85, metalness: 0,
    side: THREE.DoubleSide, aoMapIntensity: 1,
  });
  // Keep Three's lighting, normal mapping and roughness-aware specular occlusion.
  // Our packed G/B surface map needs just one texture fetch for both channels.
  material.onBeforeCompile = (shader) => {
    const roughnessChunk = '#include <roughnessmap_fragment>';
    const metalnessChunk = '#include <metalnessmap_fragment>';
    if (!shader.fragmentShader.includes(roughnessChunk) || !shader.fragmentShader.includes(metalnessChunk)) {
      throw new Error('Garage shader requires the pinned Three.js standard material chunks');
    }
    shader.fragmentShader = shader.fragmentShader.replace(roughnessChunk, `
      float roughnessFactor = roughness;
      #ifdef USE_ROUGHNESSMAP
        vec4 garageSurface = texture2D( roughnessMap, vRoughnessMapUv );
        roughnessFactor *= garageSurface.g;
      #endif
    `).replace(metalnessChunk, `
      float metalnessFactor = metalness;
      #ifdef USE_METALNESSMAP
        #ifdef USE_ROUGHNESSMAP
          metalnessFactor *= garageSurface.b;
        #else
          metalnessFactor *= texture2D( metalnessMap, vMetalnessMapUv ).b;
        #endif
      #endif
    `);
  };
  material.customProgramCacheKey = () => 'garage-shared-rm-assembled-ao-v1';
  return material;
}

export function setGarageSurface(material, texture) {
  // These slots MUST share the same texture, channel and transform for our shader.
  material.roughnessMap = material.metalnessMap = texture;
  material.roughness = material.metalness = 1;
  material.needsUpdate = true;
}

export function setGarageAO(material, texture) {
  texture.channel = 1;
  texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.colorSpace = THREE.NoColorSpace;
  material.aoMap = texture;
  material.needsUpdate = true;
}
