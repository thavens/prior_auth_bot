(() => {
  const canvas = document.getElementById('particle-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let width, height, particles, mouse, dpr;
  let spawnTimer = 0;

  const CONFIG = {
    maxCount: 240,
    spawnInterval: 100,
    fadeInDuration: 2000,
    baseRadius: 1.5,
    maxRadius: 3.5,
    baseSpeed: 0.3,
    mouseRadius: 200,
    mouseForce: 0.45,
    lineDistance: 140,
    lineOpacity: 0.08,
    friction: 0.90,
    crowdRadius: 60,
    crowdForce: 0.02,
    colors: [
      { r: 85, g: 204, b: 88 },
      { r: 62, g: 119, b: 241 },
      { r: 255, g: 255, b: 255 },
    ],
    colorWeights: [0.3, 0.25, 0.45],
  };

  mouse = { x: -9999, y: -9999 };

  function pickColor() {
    const r = Math.random();
    let cumulative = 0;
    for (let i = 0; i < CONFIG.colorWeights.length; i++) {
      cumulative += CONFIG.colorWeights[i];
      if (r < cumulative) return CONFIG.colors[i];
    }
    return CONFIG.colors[CONFIG.colors.length - 1];
  }

  function createParticle() {
    const color = pickColor();
    const targetOpacity = 0.15 + Math.random() * 0.35;
    const radius = CONFIG.baseRadius + Math.random() * (CONFIG.maxRadius - CONFIG.baseRadius);
    const angle = Math.random() * Math.PI * 2;
    const speed = CONFIG.baseSpeed * (0.5 + Math.random() * 0.5);
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      baseVx: Math.cos(angle) * speed,
      baseVy: Math.sin(angle) * speed,
      vx: 0,
      vy: 0,
      radius,
      color,
      opacity: 0,
      targetOpacity,
      spawnTime: performance.now(),
      flickerPhase: Math.random() * Math.PI * 2,
      flickerSpeed: 0.8 + Math.random() * 2.4,
      flickerDepth: 0.3 + Math.random() * 0.5,
    };
  }

  function init() {
    dpr = window.devicePixelRatio || 1;
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    particles = [];
    spawnTimer = performance.now();
  }

  function trySpawn(now) {
    if (particles.length >= CONFIG.maxCount) return;
    if (now - spawnTimer < CONFIG.spawnInterval) return;
    spawnTimer = now;
    particles.push(createParticle());
  }

  function update() {
    const now = performance.now();
    trySpawn(now);

    for (const p of particles) {
      const age = now - p.spawnTime;
      const fadeIn = age < CONFIG.fadeInDuration ? age / CONFIG.fadeInDuration : 1;
      const flicker = 1 - p.flickerDepth * (0.5 + 0.5 * Math.sin(now * 0.001 * p.flickerSpeed + p.flickerPhase));
      p.opacity = p.targetOpacity * fadeIn * flicker;

      const dx = p.x - mouse.x;
      const dy = p.y - mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < CONFIG.mouseRadius && dist > 0) {
        const force = (1 - dist / CONFIG.mouseRadius) * CONFIG.mouseForce;
        p.vx += (dx / dist) * force;
        p.vy += (dy / dist) * force;
      }

      for (const other of particles) {
        if (other === p) continue;
        const cdx = p.x - other.x;
        const cdy = p.y - other.y;
        const cdist = Math.sqrt(cdx * cdx + cdy * cdy);
        if (cdist < CONFIG.crowdRadius && cdist > 0) {
          const push = (1 - cdist / CONFIG.crowdRadius) * CONFIG.crowdForce;
          p.vx += (cdx / cdist) * push;
          p.vy += (cdy / cdist) * push;
        }
      }

      p.vx *= CONFIG.friction;
      p.vy *= CONFIG.friction;

      const maxVel = 15;
      if (p.vx > maxVel) p.vx = maxVel;
      if (p.vx < -maxVel) p.vx = -maxVel;
      if (p.vy > maxVel) p.vy = maxVel;
      if (p.vy < -maxVel) p.vy = -maxVel;

      p.x += p.baseVx + p.vx;
      p.y += p.baseVy + p.vy;

      const wrapW = width + 20;
      const wrapH = height + 20;
      p.x = ((p.x + 10) % wrapW + wrapW) % wrapW - 10;
      p.y = ((p.y + 10) % wrapH + wrapH) % wrapH - 10;
    }
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);

    for (let i = 0; i < particles.length; i++) {
      const a = particles[i];
      if (a.opacity < 0.01) continue;
      for (let j = i + 1; j < particles.length; j++) {
        const b = particles[j];
        if (b.opacity < 0.01) continue;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < CONFIG.lineDistance) {
          const alpha = (1 - dist / CONFIG.lineDistance) * CONFIG.lineOpacity
            * Math.min(a.opacity, b.opacity) / 0.5;

          const mouseDx = (a.x + b.x) / 2 - mouse.x;
          const mouseDy = (a.y + b.y) / 2 - mouse.y;
          const mouseDist = Math.sqrt(mouseDx * mouseDx + mouseDy * mouseDy);
          const mouseBoost = mouseDist < CONFIG.mouseRadius
            ? 1 + (1 - mouseDist / CONFIG.mouseRadius) * 3
            : 1;

          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = `rgba(85, 204, 88, ${alpha * mouseBoost})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }

    for (const p of particles) {
      if (p.opacity < 0.01) continue;

      const dx = p.x - mouse.x;
      const dy = p.y - mouse.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      let glow = 0;
      let radiusMult = 1;
      if (dist < CONFIG.mouseRadius) {
        const proximity = 1 - dist / CONFIG.mouseRadius;
        glow = proximity * 0.6;
        radiusMult = 1 + proximity * 0.8;
      }

      const { r, g, b } = p.color;

      if (glow > 0.1) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius * radiusMult * 3, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${glow * 0.15 * p.opacity / p.targetOpacity})`;
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius * radiusMult, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${p.opacity + glow * 0.3})`;
      ctx.fill();
    }
  }

  function loop() {
    update();
    draw();
    requestAnimationFrame(loop);
  }

  document.addEventListener('mousemove', (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  });

  document.addEventListener('mouseleave', () => {
    mouse.x = -9999;
    mouse.y = -9999;
  });

  window.addEventListener('resize', () => {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  });

  init();
  loop();
})();
