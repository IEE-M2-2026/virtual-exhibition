import * as THREE from 'three';

/** Shared garage shader: colour/normal/RM on UV0, assembled AO on UV1. */
export function createGarageMaterial({ floor = {}, roughness = {} } = {}) {
  const material = new THREE.MeshStandardMaterial({
    name: 'Garage shared PBR + assembled AO',
    color: 0xffffff, roughness: 0.85, metalness: 0,
    side: THREE.DoubleSide, aoMapIntensity: 1,
  });
  const probe = {
    garageProbePosition: { value: new THREE.Vector3() },
    garageBoxMin: { value: new THREE.Vector3() },
    garageBoxMax: { value: new THREE.Vector3() },
    garageFloorHeight: { value: floor.height ?? 0.2 },
    garageFloorNormalScale: { value: floor.normal_scale ?? 1 },
    garageRoughnessContrast: { value: roughness.contrast ?? 1 },
    garageRoughnessPivot: { value: roughness.pivot ?? 0.5 },
    garageRoughnessMin: { value: roughness.minimum ?? 0 },
    garageRoughnessMax: { value: roughness.maximum ?? 1 },
  };
  material.userData.probeUniforms = probe;
  // Keep Three's lighting, normal mapping and roughness-aware specular occlusion.
  // Our packed G/B surface map needs just one texture fetch for both channels.
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, probe);
    shader.vertexShader = shader.vertexShader.replace('#include <common>', `
      #include <common>
      varying vec3 vGarageWorldPosition;
    `).replace('#include <worldpos_vertex>', `
      #include <worldpos_vertex>
      vGarageWorldPosition = (modelMatrix * vec4(transformed, 1.0)).xyz;
    `);
    shader.fragmentShader = shader.fragmentShader.replace('#include <common>', `
      #include <common>
      varying vec3 vGarageWorldPosition;
      uniform vec3 garageProbePosition;
      uniform vec3 garageBoxMin;
      uniform vec3 garageBoxMax;
      uniform float garageFloorHeight;
      uniform float garageFloorNormalScale;
      uniform float garageRoughnessContrast;
      uniform float garageRoughnessPivot;
      uniform float garageRoughnessMin;
      uniform float garageRoughnessMax;
      float garageRemapRoughness(float source) {
        return clamp(0.5 + (source - garageRoughnessPivot) * garageRoughnessContrast,
          garageRoughnessMin, garageRoughnessMax);
      }
      float garageGroundMask(vec3 worldNormal) {
        return (1.0 - smoothstep(0.01, 0.025, abs(vGarageWorldPosition.y - garageFloorHeight)))
          * smoothstep(0.98, 0.999, worldNormal.y);
      }
      vec3 garageBoxDirection(vec3 direction) {
        // Intersect the reflection ray with the room's proxy box. Clamp tiny
        // protrusions into the box and protect axis-parallel rays from NaNs.
        vec3 origin = clamp(vGarageWorldPosition, garageBoxMin + 0.001, garageBoxMax - 0.001);
        vec3 positive = step(vec3(0.0), direction);
        vec3 safeDirection = mix(vec3(-1.0), vec3(1.0), positive) * max(abs(direction), vec3(0.000001));
        vec3 boundary = mix(garageBoxMin, garageBoxMax, positive);
        vec3 distances = (boundary - origin) / safeDirection;
        float distance = max(0.0, min(min(distances.x, distances.y), distances.z));
        return origin + direction * distance - garageProbePosition;
      }
    `);
    const reflectionLine = 'reflectVec = transformDirectionByInverseViewMatrix( reflectVec, viewMatrix );';
    if (!THREE.ShaderChunk.envmap_physical_pars_fragment.includes(reflectionLine)) {
      throw new Error('Garage box projection requires the pinned Three.js reflection chunk');
    }
    shader.fragmentShader = shader.fragmentShader.replace('#include <envmap_physical_pars_fragment>',
      THREE.ShaderChunk.envmap_physical_pars_fragment.replace(reflectionLine, `${reflectionLine}
        #ifdef GARAGE_BOX_PROJECTION
          reflectVec = normalize(garageBoxDirection(reflectVec));
        #endif
      `));
    // Only the normal-detail adjustment is floor-specific. Roughness contrast
    // uses the original shared map across the entire building.
    shader.fragmentShader = shader.fragmentShader.replace('#include <normal_fragment_begin>', `
      #include <normal_fragment_begin>
      float garageFloorMask = garageGroundMask(transformDirectionByInverseViewMatrix(normal, viewMatrix));
    `).replace('#include <normal_fragment_maps>', THREE.ShaderChunk.normal_fragment_maps.replace(
      'mapN.xy *= normalScale;', 'mapN.xy *= normalScale * mix(1.0, garageFloorNormalScale, garageFloorMask);'));
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
      roughnessFactor = garageRemapRoughness(roughnessFactor);
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
  material.customProgramCacheKey = () => 'garage-shared-rm-ao-box-probe-contrast-v4';
  return material;
}

export function setGarageProbe(material, texture, settings) {
  const uniforms = material.userData.probeUniforms;
  uniforms.garageProbePosition.value.fromArray(settings.position);
  uniforms.garageBoxMin.value.fromArray(settings.box_min);
  uniforms.garageBoxMax.value.fromArray(settings.box_max);
  material.envMap = texture;
  material.envMapIntensity = settings.intensity;
  material.defines = { ...material.defines, GARAGE_BOX_PROJECTION: 1 };
  material.needsUpdate = true;
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
