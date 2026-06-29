/* CHRONOS ambient WebGL background.
   A slow domain-warped flow field in near-black ink with faint amber/teal
   energy and a breathing blueprint grid. Pure WebGL (no libraries). Degrades
   gracefully: if WebGL is unavailable or the user prefers reduced motion, the
   CSS background remains and this does nothing harmful. */
(function () {
  "use strict";
  const canvas = document.getElementById("bg");
  if (!canvas) return;

  let gl;
  try {
    gl = canvas.getContext("webgl", { antialias: false, alpha: true, depth: false })
       || canvas.getContext("experimental-webgl");
  } catch (e) { gl = null; }
  if (!gl) return; // CSS fallback stays

  const VERT = "attribute vec2 a;void main(){gl_Position=vec4(a,0.0,1.0);}";
  const FRAG = `
  precision mediump float;
  uniform vec2 u_res; uniform float u_time; uniform vec2 u_mouse;
  float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
  float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
    float a=hash(i),b=hash(i+vec2(1.0,0.0)),c=hash(i+vec2(0.0,1.0)),d=hash(i+vec2(1.0,1.0));
    return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}
  float fbm(vec2 p){float v=0.0,a=0.5;for(int i=0;i<4;i++){v+=a*noise(p);p*=2.03;a*=0.5;}return v;}
  void main(){
    vec2 uv=gl_FragCoord.xy/u_res.xy;
    vec2 p=uv; p.x*=u_res.x/u_res.y;
    float t=u_time*0.025;
    vec2 m=(u_mouse-0.5)*0.25;
    vec2 q=vec2(fbm(p*1.4+t+m), fbm(p*1.4-t+5.0));
    float f=fbm(p*2.0+q*1.6+t);
    vec3 ink=vec3(0.039,0.047,0.063);
    vec3 amber=vec3(0.97,0.66,0.20);
    vec3 teal=vec3(0.33,0.84,0.75);
    float am=smoothstep(0.58,0.98,f)*(0.11+0.05*sin(t*1.7+p.x*2.0));
    float te=smoothstep(0.52,0.92,fbm(p*1.7-q+t*0.7))*0.07;
    vec3 col=ink+amber*am+teal*te;
    vec2 g=fract(uv*vec2(u_res.x/34.0,u_res.y/34.0));
    float line=min(g.x,g.y);
    float grid=1.0-smoothstep(0.0,0.06,line);
    col+=grid*0.010*(0.6+0.4*sin(t*2.0));
    col*=1.0-0.28*length(uv-0.5);
    gl_FragColor=vec4(col,1.0);
  }`;

  function compile(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) return null;
    return s;
  }
  const vs = compile(gl.VERTEX_SHADER, VERT);
  const fs = compile(gl.FRAGMENT_SHADER, FRAG);
  if (!vs || !fs) return;
  const prog = gl.createProgram();
  gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
  gl.useProgram(prog);

  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "a");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  const uRes = gl.getUniformLocation(prog, "u_res");
  const uTime = gl.getUniformLocation(prog, "u_time");
  const uMouse = gl.getUniformLocation(prog, "u_mouse");

  const SCALE = 0.6;                 // render at 60% for soft, cheap background
  function resize() {
    const w = Math.max(2, Math.floor(window.innerWidth * SCALE));
    const h = Math.max(2, Math.floor(window.innerHeight * SCALE));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w; canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
  }
  window.addEventListener("resize", resize);
  resize();

  const mouse = [0.5, 0.5], target = [0.5, 0.5];
  window.addEventListener("pointermove", e => {
    target[0] = e.clientX / window.innerWidth;
    target[1] = 1 - e.clientY / window.innerHeight;
  }, { passive: true });

  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let running = true;
  document.addEventListener("visibilitychange", () => {
    running = !document.hidden;
    if (running && !reduced) requestAnimationFrame(loop);
  });

  function draw(timeSec) {
    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform1f(uTime, timeSec);
    mouse[0] += (target[0] - mouse[0]) * 0.05;
    mouse[1] += (target[1] - mouse[1]) * 0.05;
    gl.uniform2f(uMouse, mouse[0], mouse[1]);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  const start = performance.now();
  function loop() {
    if (!running) return;
    draw((performance.now() - start) / 1000);
    requestAnimationFrame(loop);
  }
  if (reduced) draw(8.0); else requestAnimationFrame(loop);
})();
