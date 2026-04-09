"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

import styles from "./webgl-backdrop.module.css";

const MAX_PIXEL_RATIO = 1;
const TARGET_FPS = 24;

export function WebGLBackdrop() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: "low-power",
    });

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, MAX_PIXEL_RATIO));

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(56, 1, 0.1, 20);
    camera.position.z = 4.8;

    const uniforms = {
      uTime: { value: 0 },
      uResolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
      uScroll: { value: 0 },
    };

    const geometry = new THREE.PlaneGeometry(12, 12, 1, 1);
    const material = new THREE.ShaderMaterial({
      uniforms,
      transparent: true,
      vertexShader: `
        varying vec2 vUv;

        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        precision mediump float;

        varying vec2 vUv;

        uniform float uTime;
        uniform vec2 uResolution;
        uniform float uScroll;

        float hash(vec2 p) {
          return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
        }

        float softCircle(vec2 uv, vec2 center, float radius, float blur) {
          float d = distance(uv, center);
          return smoothstep(radius + blur, radius, d);
        }

        void main() {
          vec2 uv = vUv;
          float t = uTime * 0.35;
          float zoom = 1.0 + uScroll * 0.16;
          vec2 zUv = (uv - 0.5) * zoom + 0.5;
          vec2 zP = zUv * 2.0 - 1.0;
          zP.x *= uResolution.x / max(uResolution.y, 1.0);

          vec3 darkA = vec3(0.33, 0.35, 0.39);
          vec3 darkB = vec3(0.27, 0.29, 0.33);
          vec3 base = mix(darkA, darkB, smoothstep(0.0, 1.0, zUv.y));

          vec3 coolA = vec3(0.42, 0.45, 0.5);
          vec3 coolB = vec3(0.74, 0.78, 0.84);
          vec3 color = base;

          for (int i = 0; i < 8; i++) {
            float fi = float(i);
            float seed = 0.19 + fi * 0.137;
            vec2 center = vec2(
              0.5 + sin(t * (0.18 + seed * 0.33) + seed * 11.0 + uScroll * 2.4) * (0.16 + seed * 0.22),
              0.5 + cos(t * (0.16 + seed * 0.27) + seed * 8.0 + uScroll * 1.8) * (0.14 + seed * 0.18)
            );
            float radius = 0.07 + fract(seed * 8.1) * 0.11;
            float blob = softCircle(zUv, center, radius, 0.2);
            vec3 tint = mix(coolA, coolB, fract(seed * 7.1));
            color += tint * blob * (0.085 + fract(seed * 4.7) * 0.05);
          }

          float stars = 0.0;
          for (int j = 0; j < 52; j++) {
            float fj = float(j);
            float sx = fract(sin(fj * 17.13 + 0.72) * 43758.5453);
            float sy = fract(cos(fj * 23.71 + 1.38) * 31217.8917);
            float aSeed = fract(sin(fj * 41.37 + 2.11) * 91231.337);
            float sSeed = fract(cos(fj * 29.83 + 0.57) * 77241.119);
            float angle = aSeed * 6.28318530718;
            float speed = 0.006 + sSeed * 0.024;
            vec2 dir = vec2(cos(angle), sin(angle));
            vec2 starPos = fract(vec2(sx, sy) + dir * (t * speed));
            float twinkle = smoothstep(
              0.7,
              1.0,
              sin(t * (0.7 + fract(fj * 0.17)) + fj * 3.1) * 0.5 + 0.5
            );
            float star = softCircle(zUv, starPos, 0.0017 + fract(fj * 0.23) * 0.0025, 0.01);
            stars += star * twinkle;
          }
          color += vec3(0.88, 0.9, 0.95) * stars * 0.48;

          float grain = hash(zUv * uResolution.xy * 0.25 + t) - 0.5;
          color += grain * 0.008;

          float vignette = smoothstep(1.04, 0.28, length(zP * vec2(1.0, 1.2)));
          color *= mix(0.87, 1.0, vignette);

          gl_FragColor = vec4(color, 0.88);
        }
      `,
    });

    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    let rafId = 0;
    let active = !document.hidden;
    let last = performance.now();
    const frameBudget = 1000 / TARGET_FPS;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let scrollTarget = 0;
    let scrollValue = 0;

    const updateScrollTarget = () => {
      const maxScroll = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
      scrollTarget = Math.min(Math.max(window.scrollY / maxScroll, 0), 1);
    };

    const updateSize = () => {
      const { innerWidth, innerHeight } = window;
      renderer.setSize(innerWidth, innerHeight, false);
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      uniforms.uResolution.value.set(innerWidth, innerHeight);
    };

    const renderFrame = (now: number) => {
      if (!active) return;

      rafId = requestAnimationFrame(renderFrame);
      if (now - last < frameBudget) return;

      const delta = (now - last) / 1000;
      last = now;

      if (!prefersReducedMotion) {
        uniforms.uTime.value += delta;
      }

      scrollValue = THREE.MathUtils.lerp(scrollValue, scrollTarget, 0.065);
      uniforms.uScroll.value = scrollValue;
      mesh.scale.setScalar(1.02 + scrollValue * 0.24);
      camera.position.z = 4.8 - scrollValue * 1.05;

      renderer.render(scene, camera);
    };

    const onVisibility = () => {
      active = !document.hidden;
      if (active) {
        last = performance.now();
        rafId = requestAnimationFrame(renderFrame);
      } else {
        cancelAnimationFrame(rafId);
      }
    };

    updateSize();
    updateScrollTarget();
    rafId = requestAnimationFrame(renderFrame);

    window.addEventListener("resize", updateSize);
    window.addEventListener("scroll", updateScrollTarget, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", updateSize);
      window.removeEventListener("scroll", updateScrollTarget);
      document.removeEventListener("visibilitychange", onVisibility);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div className={styles.backdrop} aria-hidden="true">
      <canvas ref={canvasRef} className={styles.canvas} />
    </div>
  );
}
