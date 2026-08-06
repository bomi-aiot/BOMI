import { useEffect, useRef } from 'react'
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  CatmullRomCurve3,
  CircleGeometry,
  DoubleSide,
  Group,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  Points,
  PointsMaterial,
  RingGeometry,
  Scene,
  ShaderMaterial,
  SRGBColorSpace,
  Texture,
  TextureLoader,
  TubeGeometry,
  Vector2,
  Vector3,
  WebGLRenderer,
} from 'three'
import bomiRobotUrl from '../../assets/landing/bomi-robot.webp'

export type BomiSceneStatus = 'ready' | 'fallback'

interface BomiHeroSceneProps {
  onStatusChange: (status: BomiSceneStatus) => void
}

interface NavigatorWithMemory extends Navigator {
  deviceMemory?: number
}

const POINTER_EASE = 0.055

function createRandom(seed = 356) {
  let value = seed
  return () => {
    value = (value * 16807) % 2147483647
    return (value - 1) / 2147483646
  }
}

export default function BomiHeroScene({ onStatusChange }: BomiHeroSceneProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const host = canvas?.parentElement

    if (!canvas || !host) {
      onStatusChange('fallback')
      return
    }

    const memory = (navigator as NavigatorWithMemory).deviceMemory ?? 8
    const lowPower = window.innerWidth < 700 || navigator.hardwareConcurrency <= 4 || memory <= 4
    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    let reducedMotion = reducedMotionQuery.matches
    let disposed = false
    let webglFailed = false
    let frameId = 0
    let inViewport = true
    let pageVisible = !document.hidden
    let scrollProgress = 0
    let pointerX = 0
    let pointerY = 0
    let targetPointerX = 0
    let targetPointerY = 0
    let expression = 0
    let targetExpression = 0
    let texture: Texture | null = null
    let faceMaterial: ShaderMaterial | null = null

    const contextAttributes: WebGLContextAttributes = {
      alpha: true,
      antialias: !lowPower,
      depth: true,
      powerPreference: lowPower ? 'low-power' : 'high-performance',
      premultipliedAlpha: true,
    }
    const context =
      canvas.getContext('webgl2', contextAttributes) ??
      canvas.getContext('webgl', contextAttributes)

    if (!context) {
      onStatusChange('fallback')
      return
    }

    let renderer: WebGLRenderer
    try {
      renderer = new WebGLRenderer({
        canvas,
        context,
        alpha: true,
        antialias: !lowPower,
        powerPreference: lowPower ? 'low-power' : 'high-performance',
      })
    } catch {
      onStatusChange('fallback')
      return
    }

    renderer.outputColorSpace = SRGBColorSpace
    renderer.setClearColor(0x000000, 0)
    renderer.setPixelRatio(lowPower ? 1 : Math.min(window.devicePixelRatio, 1.5))

    const scene = new Scene()
    const camera = new PerspectiveCamera(35, 1, 0.1, 30)
    camera.position.set(0, 0, 7.6)

    const world = new Group()
    const robotGroup = new Group()
    const atmosphereGroup = new Group()
    scene.add(world)
    world.add(atmosphereGroup, robotGroup)

    const shadowMaterial = new MeshBasicMaterial({
      color: 0x7b2448,
      depthWrite: false,
      opacity: 0.13,
      transparent: true,
    })
    const shadow = new Mesh(new CircleGeometry(1, lowPower ? 32 : 64), shadowMaterial)
    shadow.position.set(0, -2.12, -0.24)
    shadow.scale.set(1.42, 0.22, 1)
    robotGroup.add(shadow)

    const random = createRandom()
    const particleCount = lowPower ? 44 : 92
    const particlePositions = new Float32Array(particleCount * 3)
    for (let index = 0; index < particleCount; index += 1) {
      const angle = random() * Math.PI * 2
      const radius = 1.75 + random() * 1.65
      particlePositions[index * 3] = Math.cos(angle) * radius
      particlePositions[index * 3 + 1] = (random() - 0.5) * 4.7
      particlePositions[index * 3 + 2] = -0.35 - random() * 1.3
    }
    const particleGeometry = new BufferGeometry()
    particleGeometry.setAttribute('position', new BufferAttribute(particlePositions, 3))
    const particleMaterial = new PointsMaterial({
      blending: AdditiveBlending,
      color: 0xff76ad,
      depthWrite: false,
      opacity: lowPower ? 0.42 : 0.58,
      size: lowPower ? 0.045 : 0.052,
      sizeAttenuation: true,
      transparent: true,
    })
    const particles = new Points(particleGeometry, particleMaterial)
    atmosphereGroup.add(particles)

    const ribbonCurve = new CatmullRomCurve3(
      [
        new Vector3(-2.8, -1.15, -0.32),
        new Vector3(-2.15, 0.72, -0.08),
        new Vector3(-0.25, 1.98, -0.45),
        new Vector3(2.05, 1.34, -0.78),
        new Vector3(2.85, -0.5, -0.55),
        new Vector3(0.92, -1.82, -0.2),
      ],
      true,
      'catmullrom',
      0.48,
    )
    const ribbonGeometry = new TubeGeometry(
      ribbonCurve,
      lowPower ? 54 : 110,
      lowPower ? 0.012 : 0.018,
      lowPower ? 4 : 6,
      true,
    )
    const ribbonMaterial = new MeshBasicMaterial({
      blending: AdditiveBlending,
      color: 0xff5fa2,
      depthWrite: false,
      opacity: 0.56,
      transparent: true,
    })
    const ribbon = new Mesh(ribbonGeometry, ribbonMaterial)
    atmosphereGroup.add(ribbon)

    const haloMaterial = new MeshBasicMaterial({
      blending: AdditiveBlending,
      color: 0xffd2e1,
      depthWrite: false,
      opacity: 0.2,
      side: DoubleSide,
      transparent: true,
    })
    const halo = new Mesh(new RingGeometry(1.72, 1.77, lowPower ? 64 : 128), haloMaterial)
    halo.position.z = -0.55
    halo.rotation.x = 0.22
    halo.scale.set(1.08, 1.34, 1)
    atmosphereGroup.add(halo)

    const renderFrame = (time: number) => {
      pointerX += (targetPointerX - pointerX) * POINTER_EASE
      pointerY += (targetPointerY - pointerY) * POINTER_EASE
      expression += ((reducedMotion ? 0 : targetExpression) - expression) * 0.09

      if (faceMaterial) {
        faceMaterial.uniforms.uPointer.value.set(pointerX, -pointerY)
        faceMaterial.uniforms.uExpression.value = expression
      }

      const timeSeconds = time * 0.001
      const idleLift = reducedMotion ? 0 : Math.sin(timeSeconds * 0.72) * 0.045
      robotGroup.rotation.x = reducedMotion ? 0 : pointerY * -0.08
      robotGroup.rotation.y = reducedMotion ? 0 : pointerX * 0.12
      robotGroup.rotation.z = reducedMotion ? 0 : pointerX * -0.018
      robotGroup.position.x = reducedMotion ? 0 : pointerX * 0.11
      robotGroup.position.y = idleLift - scrollProgress * 0.22
      const sceneScale = 1 - scrollProgress * 0.055
      robotGroup.scale.setScalar(sceneScale)

      atmosphereGroup.rotation.z = reducedMotion
        ? 0.04
        : timeSeconds * 0.018 + pointerX * 0.025 + scrollProgress * 0.34
      atmosphereGroup.rotation.x = reducedMotion ? 0 : pointerY * 0.025
      particles.rotation.y = reducedMotion ? 0 : timeSeconds * -0.025
      ribbonMaterial.opacity = reducedMotion
        ? 0.44
        : 0.48 + Math.sin(timeSeconds * 0.82) * 0.08

      camera.position.x = reducedMotion ? 0 : pointerX * 0.07
      camera.position.y = scrollProgress * 0.08
      camera.lookAt(0, -scrollProgress * 0.05, 0)
      renderer.render(scene, camera)
    }

    const shouldAnimate = () =>
      !disposed && !webglFailed && !reducedMotion && inViewport && pageVisible && texture

    const tick = (time: number) => {
      frameId = 0
      renderFrame(time)
      if (shouldAnimate()) {
        frameId = window.requestAnimationFrame(tick)
      }
    }

    const scheduleFrame = () => {
      if (disposed || webglFailed || frameId || !texture) return
      if (shouldAnimate()) {
        frameId = window.requestAnimationFrame(tick)
      } else {
        renderFrame(performance.now())
      }
    }

    const stopFrame = () => {
      if (!frameId) return
      window.cancelAnimationFrame(frameId)
      frameId = 0
    }

    const updateSize = () => {
      const width = Math.max(1, host.clientWidth)
      const height = Math.max(1, host.clientHeight)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      renderer.setSize(width, height, false)
      scheduleFrame()
    }

    const updateScrollProgress = () => {
      const hero = host.closest('.landing-hero')
      if (!hero) return
      const rect = hero.getBoundingClientRect()
      scrollProgress = MathUtils.clamp(-rect.top / Math.max(rect.height * 0.72, 1), 0, 1)
    }

    const handlePointerMove = (event: PointerEvent) => {
      if (reducedMotion) return
      const rect = host.getBoundingClientRect()
      targetPointerX = MathUtils.clamp(((event.clientX - rect.left) / rect.width) * 2 - 1, -1, 1)
      targetPointerY = MathUtils.clamp(((event.clientY - rect.top) / rect.height) * 2 - 1, -1, 1)
      targetExpression = 1
    }

    const handlePointerLeave = () => {
      targetPointerX = 0
      targetPointerY = 0
      targetExpression = 0
    }

    const handlePointerEnd = (event: PointerEvent) => {
      if (event.pointerType === 'mouse') return
      targetPointerX = 0
      targetPointerY = 0
      targetExpression = 0
    }

    const handleVisibilityChange = () => {
      pageVisible = !document.hidden
      if (pageVisible) scheduleFrame()
      else stopFrame()
    }

    const handleMotionChange = (event: MediaQueryListEvent) => {
      reducedMotion = event.matches
      targetPointerX = 0
      targetPointerY = 0
      targetExpression = 0
      if (reducedMotion) {
        pointerX = 0
        pointerY = 0
        expression = 0
        faceMaterial?.uniforms.uPointer.value.set(0, 0)
        if (faceMaterial) faceMaterial.uniforms.uExpression.value = 0
        stopFrame()
      }
      scheduleFrame()
    }

    const handleContextLost = () => {
      webglFailed = true
      stopFrame()
      if (!disposed) onStatusChange('fallback')
    }

    let resizeObserver: ResizeObserver | null = null
    let viewportObserver: IntersectionObserver | null = null

    if (typeof ResizeObserver === 'function') {
      resizeObserver = new ResizeObserver(updateSize)
      resizeObserver.observe(host)
    } else {
      window.addEventListener('resize', updateSize, { passive: true })
    }

    if (typeof IntersectionObserver === 'function') {
      viewportObserver = new IntersectionObserver(
        ([entry]) => {
          inViewport = entry.isIntersecting
          if (inViewport) scheduleFrame()
          else stopFrame()
        },
        { rootMargin: '120px 0px', threshold: 0.01 },
      )
      viewportObserver.observe(canvas)
    }
    host.addEventListener('pointermove', handlePointerMove, { passive: true })
    host.addEventListener('pointerleave', handlePointerLeave)
    host.addEventListener('pointerup', handlePointerEnd, { passive: true })
    host.addEventListener('pointercancel', handlePointerEnd, { passive: true })
    window.addEventListener('scroll', updateScrollProgress, { passive: true })
    document.addEventListener('visibilitychange', handleVisibilityChange)
    reducedMotionQuery.addEventListener('change', handleMotionChange)
    canvas.addEventListener('webglcontextlost', handleContextLost)
    updateScrollProgress()
    updateSize()

    const textureLoader = new TextureLoader()
    textureLoader.load(
      bomiRobotUrl,
      (loadedTexture) => {
        if (disposed || webglFailed) {
          loadedTexture.dispose()
          return
        }

        texture = loadedTexture
        texture.colorSpace = SRGBColorSpace
        texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), lowPower ? 2 : 4)

        const robotGeometry = new PlaneGeometry(3.18, 4.3)
        const glowMaterial = new MeshBasicMaterial({
          blending: AdditiveBlending,
          color: 0xff7fb2,
          depthWrite: false,
          map: texture,
          opacity: 0.12,
          transparent: true,
        })
        faceMaterial = new ShaderMaterial({
          uniforms: {
            uExpression: { value: 0 },
            uMap: { value: texture },
            uPointer: { value: new Vector2(0, 0) },
          },
          vertexShader: `
            varying vec2 vUv;

            void main() {
              vUv = uv;
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
          `,
          fragmentShader: `
            uniform sampler2D uMap;
            uniform vec2 uPointer;
            uniform float uExpression;
            varying vec2 vUv;

            vec2 animateEye(
              vec2 uv,
              vec2 sourceCenter,
              vec2 radius,
              vec2 offset,
              float scale
            ) {
              vec2 targetCenter = sourceCenter + offset;
              vec2 normalized = (uv - targetCenter) / radius;
              float mask = 1.0 - smoothstep(0.72, 1.03, length(normalized));
              vec2 sampleUv = sourceCenter + (uv - targetCenter) / scale;
              return mix(uv, sampleUv, mask);
            }

            void main() {
              vec2 uv = vUv;
              float scale = 1.0 + uExpression * 0.14;
              vec2 offset = vec2(uPointer.x * 0.010, uPointer.y * 0.007) * uExpression;

              uv = animateEye(
                uv,
                vec2(0.335, 0.585),
                vec2(0.075, 0.085),
                offset,
                scale
              );
              uv = animateEye(
                uv,
                vec2(0.665, 0.585),
                vec2(0.075, 0.085),
                offset,
                scale
              );

              vec4 color = texture2D(uMap, uv);
              if (color.a < 0.018) discard;
              gl_FragColor = color;
              #include <colorspace_fragment>
            }
          `,
          depthWrite: false,
          side: DoubleSide,
          transparent: true,
        })
        const glow = new Mesh(robotGeometry, glowMaterial)
        glow.position.z = -0.12
        glow.scale.setScalar(1.055)
        glow.renderOrder = 1

        const robot = new Mesh(robotGeometry, faceMaterial)
        robot.renderOrder = 2
        robotGroup.add(glow, robot)

        onStatusChange('ready')
        scheduleFrame()
      },
      undefined,
      () => {
        webglFailed = true
        if (!disposed) onStatusChange('fallback')
      },
    )

    return () => {
      disposed = true
      stopFrame()
      resizeObserver?.disconnect()
      viewportObserver?.disconnect()
      host.removeEventListener('pointermove', handlePointerMove)
      host.removeEventListener('pointerleave', handlePointerLeave)
      host.removeEventListener('pointerup', handlePointerEnd)
      host.removeEventListener('pointercancel', handlePointerEnd)
      window.removeEventListener('resize', updateSize)
      window.removeEventListener('scroll', updateScrollProgress)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      reducedMotionQuery.removeEventListener('change', handleMotionChange)
      canvas.removeEventListener('webglcontextlost', handleContextLost)

      scene.traverse((object) => {
        if (object instanceof Mesh || object instanceof Points) {
          object.geometry.dispose()
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          materials.forEach((material) => material.dispose())
        }
      })
      texture?.dispose()
      renderer.dispose()
    }
  }, [onStatusChange])

  return <canvas ref={canvasRef} className="landing-webgl-canvas" aria-hidden="true" />
}
