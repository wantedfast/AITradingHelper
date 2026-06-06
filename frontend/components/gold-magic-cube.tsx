"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

type Cubelet = THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial[]>;
type Axis = "x" | "y" | "z";

const cubeletSize = 0.92;
const gap = 0.12;
const spacing = cubeletSize + gap;

function easeInOut(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

function makeNoiseTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 96;
  canvas.height = 96;
  const context = canvas.getContext("2d");
  if (!context) return null;
  const image = context.createImageData(canvas.width, canvas.height);
  for (let i = 0; i < image.data.length; i += 4) {
    const value = 110 + Math.random() * 54;
    image.data[i] = value;
    image.data[i + 1] = value;
    image.data[i + 2] = value;
    image.data[i + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(4, 4);
  return texture;
}

function createMaterials(frostNoise: THREE.Texture | null) {
  const redGlow = new THREE.Color("#D21F3C");
  const options = {
    metalness: 0.7,
    roughness: 0.64,
    clearcoat: 0.34,
    clearcoatRoughness: 0.72,
    roughnessMap: frostNoise ?? undefined,
    bumpMap: frostNoise ?? undefined,
    bumpScale: 0.025
  };
  return [
    new THREE.MeshPhysicalMaterial({ ...options, color: "#08080A" }),
    new THREE.MeshPhysicalMaterial({ ...options, color: "#151419" }),
    new THREE.MeshPhysicalMaterial({ ...options, color: "#8B0F1F", emissive: redGlow, emissiveIntensity: 0.08 }),
    new THREE.MeshPhysicalMaterial({ ...options, color: "#D21F3C", emissive: redGlow, emissiveIntensity: 0.12 }),
    new THREE.MeshPhysicalMaterial({ ...options, color: "#050506" }),
    new THREE.MeshPhysicalMaterial({ ...options, color: "#26040A", emissive: redGlow, emissiveIntensity: 0.04 })
  ];
}

export function GoldMagicCube() {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
    camera.position.set(5.3, 4.2, 6.2);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    mount.appendChild(renderer.domElement);

    const root = new THREE.Group();
    root.rotation.set(-0.34, 0.58, -0.12);
    scene.add(root);

    const cubelets: Cubelet[] = [];
    const geometry = new THREE.BoxGeometry(cubeletSize, cubeletSize, cubeletSize);
    const edgeMaterial = new THREE.LineBasicMaterial({ color: "#FF4D64", transparent: true, opacity: 0.22 });
    const frostNoise = makeNoiseTexture();

    for (let x = -1; x <= 1; x += 1) {
      for (let y = -1; y <= 1; y += 1) {
        for (let z = -1; z <= 1; z += 1) {
          const mesh = new THREE.Mesh(geometry, createMaterials(frostNoise));
          mesh.position.set(x * spacing, y * spacing, z * spacing);
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          mesh.userData.grid = new THREE.Vector3(x, y, z);
          mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edgeMaterial));
          root.add(mesh);
          cubelets.push(mesh);
        }
      }
    }

    scene.add(new THREE.AmbientLight("#2A080C", 0.7));
    scene.add(new THREE.HemisphereLight("#FFE1E6", "#050505", 1.08));

    const key = new THREE.DirectionalLight("#FF4D64", 3.1);
    key.position.set(4.8, 7.2, 5.4);
    key.castShadow = true;
    scene.add(key);

    const softTop = new THREE.SpotLight("#f8fbff", 16, 20, Math.PI / 5, 0.65, 1.5);
    softTop.position.set(-1.6, 6.4, 3.2);
    softTop.target.position.set(0, 0, 0);
    scene.add(softTop);
    scene.add(softTop.target);

    const rim = new THREE.PointLight("#FF123A", 18, 18);
    rim.position.set(-4.6, 1.2, 5.2);
    scene.add(rim);

    const coolEdge = new THREE.PointLight("#ffffff", 3.5, 12);
    coolEdge.position.set(3.8, -1.6, -3.2);
    scene.add(coolEdge);

    const glow = new THREE.Mesh(
      new THREE.CircleGeometry(4.6, 96),
      new THREE.MeshBasicMaterial({ color: "#7A0715", transparent: true, opacity: 0.012, depthWrite: false })
    );
    glow.rotation.x = -Math.PI / 2;
    glow.position.y = -2.25;
    // No floor glow: keep the cube background pure black.

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scratchGroup = new THREE.Group();
    root.add(scratchGroup);

    const axisIndex: Record<Axis, number> = { x: 0, y: 1, z: 2 };
    const layerPlan: Array<{ axis: Axis; layer: number; dir: number }> = [
      { axis: "y", layer: 1, dir: 1 },
      { axis: "x", layer: -1, dir: -1 },
      { axis: "z", layer: 1, dir: 1 },
      { axis: "y", layer: -1, dir: -1 }
    ];

    let frame = 0;
    let twistStart = performance.now();
    let activeLayer = 0;
    let layerAxis: Axis = "y";
    let lastAngle = 0;
    let twisting = false;

    const selectedCubelets = (axis: Axis, layer: number) =>
      cubelets.filter((cubelet) => Math.round(cubelet.userData.grid.getComponent(axisIndex[axis])) === layer);

    const startTwist = (now: number) => {
      const plan = layerPlan[activeLayer % layerPlan.length];
      layerAxis = plan.axis;
      lastAngle = 0;
      twisting = true;
      twistStart = now;
      scratchGroup.rotation.set(0, 0, 0);
      selectedCubelets(plan.axis, plan.layer).forEach((cubelet) => scratchGroup.attach(cubelet));
    };

    const rotateGrid = (grid: THREE.Vector3, axis: Axis, dir: number) => {
      const next = grid.clone();
      if (axis === "x") {
        next.y = -dir * grid.z;
        next.z = dir * grid.y;
      } else if (axis === "y") {
        next.x = dir * grid.z;
        next.z = -dir * grid.x;
      } else {
        next.x = -dir * grid.y;
        next.y = dir * grid.x;
      }
      next.x = Math.round(next.x);
      next.y = Math.round(next.y);
      next.z = Math.round(next.z);
      return next;
    };

    const finishTwist = () => {
      const plan = layerPlan[activeLayer % layerPlan.length];
      selectedCubelets(plan.axis, plan.layer).forEach((cubelet) => {
        const nextGrid = rotateGrid(cubelet.userData.grid, plan.axis, plan.dir);
        root.attach(cubelet);
        cubelet.userData.grid = nextGrid;
        cubelet.position.set(nextGrid.x * spacing, nextGrid.y * spacing, nextGrid.z * spacing);
      });
      scratchGroup.rotation.set(0, 0, 0);
      activeLayer += 1;
      twisting = false;
      twistStart = performance.now();
    };

    const animate = (now: number) => {
      frame = requestAnimationFrame(animate);
      if (!reduceMotion) {
        root.rotation.y += 0.0032;
        root.rotation.x = -0.34 + Math.sin(now * 0.00055) * 0.055;

        if (!twisting && now - twistStart > 2300) startTwist(now);

        if (twisting) {
          const plan = layerPlan[activeLayer % layerPlan.length];
          const progress = Math.min(1, (now - twistStart) / 1300);
          const angle = easeInOut(progress) * (Math.PI / 2) * plan.dir;
          const delta = angle - lastAngle;
          scratchGroup.rotation[layerAxis] += delta;
          lastAngle = angle;
          if (progress >= 1) finishTwist();
        }
      }
      renderer.render(scene, camera);
    };

    resize();
    window.addEventListener("resize", resize);
    frame = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      geometry.dispose();
      edgeMaterial.dispose();
      frostNoise?.dispose();
      cubelets.forEach((cubelet) => cubelet.material.forEach((material) => material.dispose()));
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div ref={mountRef} className="magic-cube-canvas" aria-label="Black and gold rotating Three.js magic cube" />;
}

