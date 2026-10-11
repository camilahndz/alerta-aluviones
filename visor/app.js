"use strict";
/* Vigía de quebradas: lee visor/datos/ (escrito por src/m6_visor.py) y dibuja
   el relieve, las provincias con su nivel y el repaso de cada temporal. */
(() => {
  const D = "datos/";
  const PROVINCIAS = ["Elqui", "Limari", "Choapa"];
  const NOMBRE = { Elqui: "Elqui", Limari: "Limarí", Choapa: "Choapa" };
  const COLOR_PROV = { Elqui: "#9cc3e6", Limari: "#d3a6e0", Choapa: "#a7d9ae" };
  const NIVEL = ["sin alerta", "amarilla", "naranja", "roja"];
  const COLOR_NIVEL = [[59, 74, 80], [242, 201, 76], [240, 138, 60], [229, 72, 77]];
  const FRASE_NIVEL = [
    "Es poco probable que se activen quebradas.",
    "Es posible que se activen quebradas: una de cada cuatro veces pasó.",
    "Es probable que se activen quebradas: una de cada dos veces pasó.",
    "Es muy probable que se activen quebradas: tres de cada cuatro veces pasó.",
  ];
  const EXAG = 3;             // el relieve se exagera 3 veces en altura
  const TELEFONO = window.matchMedia("(max-width: 900px)").matches;
  const K = TELEFONO ? 0.6 : 1;   // en un mapa chico, puntos más chicos
  const SOBRE = 140;          // metros (ya exagerados) sobre el terreno para líneas y puntos
  const TIPO_VIA = {
    motorway: "autopista", trunk: "ruta troncal", primary: "ruta principal",
    secondary: "ruta secundaria", tertiary: "ruta terciaria", unclassified: "camino local",
    residential: "calle", living_street: "calle", service: "camino de servicio", track: "huella",
    road: "camino", motorway_link: "enlace de autopista", trunk_link: "enlace",
    primary_link: "enlace", secondary_link: "enlace", tertiary_link: "enlace",
  };
  const EVIDENCIA = {
    aluvion: "Aluvión", activacion: "Quebrada activada", activacion_menor: "Activación menor",
    escurrimiento: "Escurrimiento de agua, sin barro", alerta_preventiva: "Alerta preventiva, sin activación",
  };
  const CLASE = {
    flujo_detritos: "flujo de detritos, el más violento: barro y bloques",
    crecida_detritos: "crecida con barro y sedimento",
    tronco: "quebrada grande, de más de 50 km²",
    inundacion: "crecida de agua",
  };
  const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

  const $ = (id) => document.getElementById(id);
  const estado = { esc: null, i: 0, timer: null, sel: null, texturas: new Map() };
  let datos, alto, componer, mapa, todosLosCruces, quebradasGrandes, quebradasChicas, rutas, bordes;

  // --------------------------------------------------------------- utilidades
  const fmtNum = (v, d = 0) => v == null ? "—" : v.toLocaleString("es-CL", { maximumFractionDigits: d, minimumFractionDigits: d });
  const fmtPct = (v) => v == null ? "—" : `${Math.round(v * 100)} %`;
  function fecha(t, conHora = true) {
    const [d, h] = t.split("T");
    const [a, m, dia] = d.split("-").map(Number);
    return `${dia} ${MESES[m - 1]} ${a}` + (conHora && h ? `, ${h.slice(0, 5)}` : "");
  }
  function duracion(desde, hasta) {
    const h = (new Date(hasta) - new Date(desde)) / 3.6e6;
    if (h < 36) return `${Math.round(h)} horas`;
    return `${fmtNum(h / 24, 1)} días`;
  }
  const lista = (xs) => xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} y ${xs[xs.length - 1]}`;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  async function json(n) {
    const r = await fetch(D + n);
    if (!r.ok) throw new Error(`No se pudo leer ${n}`);
    return r.json();
  }
  function imagen(n) {
    return new Promise((ok, mal) => {
      const im = new Image();
      im.onload = () => ok(im);
      im.onerror = () => mal(new Error(`No se pudo leer ${n}`));
      im.src = D + n;
    });
  }
  function pixeles(im, escala = 1, suave = true) {
    const c = document.createElement("canvas");
    c.width = Math.round(im.naturalWidth * escala); c.height = Math.round(im.naturalHeight * escala);
    const x = c.getContext("2d", { willReadFrequently: true });
    x.imageSmoothingEnabled = suave;
    x.drawImage(im, 0, 0, c.width, c.height);
    return x.getImageData(0, 0, c.width, c.height);
  }

  // ------------------------------------------------------- relieve y textura
  // La malla 3D se arma aquí, con un vértice por píxel de elevacion.png. El
  // TerrainLayer de deck.gl lo haría solo, pero en la versión del CDN su
  // decodificador corre únicamente en un Web Worker que esta página no puede
  // cargar. En un teléfono se usa un vértice cada dos píxeles.
  let malla;
  function prepararAltura(im, [W, S, E, N]) {
    const { width: w, height: h, data } = pixeles(im);
    const z = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) z[i] = -10000 + (data[4 * i] * 65536 + data[4 * i + 1] * 256 + data[4 * i + 2]) * 0.1;

    const paso = TELEFONO ? 2 : 1;
    const cols = Math.floor((w - 1) / paso) + 1, filas = Math.floor((h - 1) / paso) + 1;
    const pos = new Float32Array(cols * filas * 3), uv = new Float32Array(cols * filas * 2);
    for (let f = 0, k = 0; f < filas; f++) {
      for (let c = 0; c < cols; c++, k++) {
        const px = c * paso, py = f * paso;
        const lon = W + (px + 0.5) / w * (E - W), lat = N - (py + 0.5) / h * (N - S);
        pos[3 * k] = lon; pos[3 * k + 1] = lat; pos[3 * k + 2] = Math.max(0, z[py * w + px]) * EXAG;
        uv[2 * k] = (lon - W) / (E - W); uv[2 * k + 1] = (N - lat) / (N - S);
      }
    }
    const idx = new Uint32Array((cols - 1) * (filas - 1) * 6);
    for (let f = 0, k = 0; f < filas - 1; f++) {
      for (let c = 0; c < cols - 1; c++) {
        const a = f * cols + c, b = a + 1, d = a + cols, e = d + 1;
        idx[k++] = a; idx[k++] = d; idx[k++] = b; idx[k++] = b; idx[k++] = d; idx[k++] = e;
      }
    }
    malla = { attributes: { POSITION: { value: pos, size: 3 }, TEXCOORD_0: { value: uv, size: 2 } },
              indices: { value: idx, size: 1 } };

    return (lon, lat) => {
      let x = (lon - W) / (E - W) * w - 0.5, y = (N - lat) / (N - S) * h - 0.5;
      x = Math.max(0, Math.min(w - 1.001, x)); y = Math.max(0, Math.min(h - 1.001, y));
      const x0 = Math.floor(x), y0 = Math.floor(y), fx = x - x0, fy = y - y0, i = y0 * w + x0;
      const v = (z[i] * (1 - fx) + z[i + 1] * fx) * (1 - fy) + (z[i + w] * (1 - fx) + z[i + w + 1] * fx) * fy;
      return Math.max(0, v) * EXAG + SOBRE;
    };
  }

  function prepararTextura(relieve, provincias) {
    // En un teléfono, la textura va a la mitad: son cuatro veces menos píxeles
    // que pintar cada vez que cambia un nivel. La máscara de provincias se
    // reduce sin suavizar, para no inventar números de provincia en los bordes.
    const escala = TELEFONO ? 0.5 : 1;
    const base = pixeles(relieve, escala), p = pixeles(provincias, escala, false);
    const n = base.width * base.height, id = new Uint8Array(n);
    for (let i = 0; i < n; i++) id[i] = Math.round(p.data[4 * i] / 60);
    // Cada combinacion de niveles se pinta una vez y se guarda como
    // ImageBitmap. Se le entrega a deck.gl ya decodificada: si se le pasara
    // una URL data:, la cargaria con fetch, y la pagina publicada no deja
    // hacer fetch de nada que no sea un archivo propio.
    return async (niveles) => {
      const clave = niveles.join("");
      if (estado.texturas.has(clave)) return estado.texturas.get(clave);
      const salida = new ImageData(base.width, base.height);
      const b = base.data, o = salida.data;
      for (let i = 0, j = 0; i < n; i++, j += 4) {
        let r = b[j], g = b[j + 1], bl = b[j + 2];
        const k = id[i];
        if (k === 0) { r *= 0.5; g *= 0.5; bl *= 0.5; }       // fuera de la región: atenuado
        else if (niveles[k] > 0) {
          const c = COLOR_NIVEL[niveles[k]], lum = (r * 0.3 + g * 0.59 + bl * 0.11) / 255;
          const f = 0.35 + lum, a = 0.46;
          r = r * (1 - a) + c[0] * f * a; g = g * (1 - a) + c[1] * f * a; bl = bl * (1 - a) + c[2] * f * a;
        }
        o[j] = r; o[j + 1] = g; o[j + 2] = bl; o[j + 3] = 255;
      }
      const bitmap = await createImageBitmap(salida);
      estado.texturas.set(clave, bitmap);
      return bitmap;
    };
  }

  // ------------------------------------------------------------ las capas
  function trazos(fuente, filtro, atributos) {
    const out = [];
    fuente.c.forEach((c, k) => {
      if (filtro && !filtro(k)) return;
      const path = [];
      for (let i = 0; i < c.length; i += 2) path.push([c[i], c[i + 1], alto(c[i], c[i + 1])]);
      const o = { path };
      for (const a of atributos) o[a] = fuente[a][k];
      out.push(o);
    });
    return out;
  }

  function prepararCapas() {
    const q = datos.quebradas;
    quebradasGrandes = trazos(q, (k) => q.clase[k] === "tronco", ["clase", "area_km2", "nombre_osm"]);
    quebradasChicas = trazos(q, (k) => q.clase[k] !== "tronco", ["clase", "area_km2", "nombre_osm"]);
    rutas = trazos(datos.rutas, null, ["highway", "name"]);
    bordes = datos.provincias.c.map((c, k) => {
      const path = [];
      for (let i = 0; i < c.length; i += 2) path.push([c[i], c[i + 1], alto(c[i], c[i + 1]) + 60]);
      return { path, provincia: datos.provincias.provincia[k] };
    });
    const x = datos.cruces;
    todosLosCruces = x.lon.map((lon, i) => ({ i, position: [lon, x.lat[i], alto(lon, x.lat[i])] }));
    const e = datos.estaciones;
    datos.est = e.codigo.map((c, i) => ({ i, position: [e.lon[i], e.lat[i], alto(e.lon[i], e.lat[i]) + 40] }));
    datos.act = datos.activaciones.map((a) => ({ ...a, position: [a.lon, a.lat, alto(a.lon, a.lat) + 60] }));
    const l = datos.localidades;
    datos.loc = l.nombre.map((n, i) => ({ nombre: n, position: [l.lon[i], l.lat[i], alto(l.lon[i], l.lat[i]) + 300] }));
  }

  // Los tramos a vigilar: el primer cruce de cada quebrada con cada vía, en
  // las provincias con alerta. Es la misma regla del boletín en vivo.
  function tramosAVigilar(paso) {
    const x = datos.cruces, salida = [];
    for (const p of PROVINCIAS) {
      if (paso.prov[p][0] === 0) continue;
      const vistos = new Set();
      for (let i = 0; i < x.rank.length && vistos.size < 10; i++) {
        if (x.provincia[i] !== p) continue;
        const clave = `${x.id_cuenca[i]}|${x.via[i]}|${x.tipo[i]}`;
        if (vistos.has(clave)) continue;
        vistos.add(clave);
        salida.push({ i, provincia: p, nivel: paso.prov[p][0], position: todosLosCruces[i].position });
      }
    }
    return salida;
  }

  function reportesHasta(paso) {
    const e = estado.esc, hoy = paso.t.slice(0, 10);
    const desde = new Date(new Date(e.pasos[0].t.slice(0, 10)) - 864e5).toISOString().slice(0, 10);
    const hasta = e.vivo ? hoy : new Date(+new Date(e.pasos[e.pasos.length - 1].t.slice(0, 10)) + 864e5).toISOString().slice(0, 10);
    return datos.act.filter((a) => a.fecha >= desde && a.fecha <= hasta && a.fecha <= hoy);
  }

  function colorFraccion(f) {
    const u = datos.resumen.umbrales;
    if (f == null || f < 0.05) return [150, 160, 160, 200];
    if (f < u.amarilla) return [210, 210, 190, 230];
    if (f < u.naranja) return [...COLOR_NIVEL[1], 255];
    if (f < u.roja) return [...COLOR_NIVEL[2], 255];
    return [...COLOR_NIVEL[3], 255];
  }

  function capas(paso, textura) {
    const { SimpleMeshLayer, PathLayer, ScatterplotLayer, TextLayer } = deck;
    const lluvia = new Map(paso.est.map(([i, mm, f]) => [i, { mm, f }]));
    const vigilar = tramosAVigilar(paso);
    const reportes = reportesHasta(paso);
    const ver = (id) => $(id).checked;
    return [
      // _instanced: false hace que las posiciones de la malla sean
      // coordenadas del mapa y no desplazamientos desde un punto.
      new SimpleMeshLayer({
        id: "relieve", data: [0], mesh: malla, texture: textura, _instanced: false,
        getPosition: [0, 0, 0], getColor: [255, 255, 255], material: false,
      }),
      new PathLayer({
        id: "rutas", data: rutas, visible: ver("capa-rutas"), getPath: (d) => d.path,
        getColor: [214, 204, 188, 150], widthUnits: "pixels",
        getWidth: (d) => ({ motorway: 2.6, trunk: 2.4, primary: 1.8 }[d.highway] || 1.1),
        pickable: true, parameters: { depthTest: true },
      }),
      new PathLayer({
        id: "chicas", data: quebradasChicas, visible: ver("capa-chicas"), getPath: (d) => d.path,
        getColor: (d) => d.clase === "inundacion" ? [98, 198, 230, 70] : [98, 198, 230, 120],
        widthUnits: "pixels", getWidth: 1, pickable: true,
      }),
      new PathLayer({
        id: "grandes", data: quebradasGrandes, visible: ver("capa-quebradas"), getPath: (d) => d.path,
        getColor: [98, 198, 230, 235], widthUnits: "pixels", getWidth: 2.4, pickable: true,
      }),
      new PathLayer({
        id: "bordes", data: bordes, getPath: (d) => d.path, getColor: [235, 230, 220, 150],
        widthUnits: "pixels", getWidth: 1.4, getDashArray: [4, 3],
      }),
      new ScatterplotLayer({
        id: "cruces", data: todosLosCruces, visible: ver("capa-cruces"), getPosition: (d) => d.position,
        radiusUnits: "pixels", getRadius: 2 * K, getFillColor: [240, 236, 228, 140], pickable: true,
      }),
      new ScatterplotLayer({
        id: "vigilar", data: vigilar, getPosition: (d) => d.position, radiusUnits: "pixels",
        getRadius: 6.5 * K, stroked: true, lineWidthUnits: "pixels", getLineWidth: 2 * K,
        getLineColor: [255, 255, 255, 255], getFillColor: (d) => [...COLOR_NIVEL[d.nivel], 255], pickable: true,
        updateTriggers: { getFillColor: estado.i },
      }),
      new ScatterplotLayer({
        id: "estaciones", data: datos.est, visible: ver("capa-estaciones"), getPosition: (d) => d.position,
        radiusUnits: "pixels", stroked: true, lineWidthUnits: "pixels", getLineWidth: 1,
        getLineColor: [13, 18, 21, 220],
        getRadius: (d) => { const v = lluvia.get(d.i); return K * (v ? Math.min(13, 3 + Math.sqrt(v.mm) * 0.75) : 2.5); },
        getFillColor: (d) => { const v = lluvia.get(d.i); return v ? colorFraccion(v.f) : [110, 120, 122, 160]; },
        pickable: true, updateTriggers: { getRadius: estado.i, getFillColor: estado.i },
      }),
      new ScatterplotLayer({
        id: "reportes", data: reportes, visible: ver("capa-reportes"), getPosition: (d) => d.position,
        radiusUnits: "pixels", getRadius: 7 * K, stroked: true, lineWidthUnits: "pixels", getLineWidth: 2.5 * K,
        getLineColor: [255, 255, 255, 255],
        getFillColor: (d) => d.evidencia === "aluvion" || d.evidencia === "activacion" ? [229, 72, 77, 255]
          : d.evidencia === "activacion_menor" ? [240, 138, 60, 255] : [120, 130, 132, 255],
        pickable: true, updateTriggers: { getFillColor: estado.i },
      }),
      new TextLayer({
        id: "localidades", data: datos.loc, getPosition: (d) => d.position, getText: (d) => d.nombre,
        characterSet: "auto", fontFamily: "Overpass, Arial, sans-serif", fontWeight: 600,
        getSize: TELEFONO ? 11 : 13, getColor: [240, 236, 228, 255], fontSettings: { sdf: true },
        outlineWidth: 4, outlineColor: [13, 18, 21, 230], getPixelOffset: [0, -10],
        billboard: true,
      }),
    ];
  }

  // -------------------------------------------------------------- el panel
  function relato(paso) {
    if (!paso.temporal) return "No hay un temporal en curso: ninguna estación junta 5 mm de lluvia en las últimas 24 horas.";
    const porNivel = [3, 2, 1].map((n) => PROVINCIAS.filter((p) => paso.prov[p][0] === n).map((p) => NOMBRE[p]));
    let s = `Llueve desde el ${fecha(paso.temporal)} (${duracion(paso.temporal, paso.t)}). `;
    const partes = [];
    if (porNivel[0].length) partes.push(`${lista(porNivel[0])} en alerta roja`);
    if (porNivel[1].length) partes.push(`${lista(porNivel[1])} en naranja`);
    if (porNivel[2].length) partes.push(`${lista(porNivel[2])} en amarilla`);
    if (!partes.length) return s + "Ninguna provincia llega todavía al primer corte.";
    return s + partes.join(", ") + ".";
  }

  function tarjetas(paso) {
    const u = datos.resumen.umbrales, tope = Math.max(0.5, u.roja * 1.6);
    $("provincias").innerHTML = PROVINCIAS.map((p) => {
      const [nv, prob, frac, mm, estacion, sig, falta, estSig, transm, insuf] = paso.prov[p];
      const ancho = Math.min(100, (frac || 0) / tope * 100);
      const marcas = ["amarilla", "naranja", "roja"].map((n, k) =>
        `<span class="corte" style="left:${u[n] / tope * 100}%;background:rgb(${COLOR_NIVEL[k + 1].join(",")})"></span>`).join("");
      let detalle = mm == null ? "Sin lluvia en el temporal." :
        `${fmtNum(mm)} mm en ${esc(estacion)}: el ${fmtPct(frac)} de un año normal.`;
      if (sig && falta != null && paso.temporal) detalle += ` Faltan ${fmtNum(falta)} mm para ${sig}.`;
      if (insuf) detalle += " Pocas estaciones transmitiendo.";
      return `<div class="prov nivel-${nv}">
        <span class="franja"></span>
        <span class="nombre">${NOMBRE[p]}</span>
        <span class="chip">${NIVEL[nv]}</span>
        <span class="detalle">${FRASE_NIVEL[nv]} ${detalle}</span>
        <span class="barra"><span class="relleno" style="width:${ancho}%"></span>${marcas}</span>
      </div>`;
    }).join("");
  }

  function panel(paso) {
    const e = estado.esc;
    $("etiqueta-hora").textContent = e.vivo ? "Último boletín" : `${e.titulo} · repaso, paso ${estado.i + 1} de ${e.pasos.length}`;
    $("hora").textContent = fecha(paso.t);
    $("relato").textContent = relato(paso);
    tarjetas(paso);

    const d = $("deshielo");
    d.hidden = !paso.desh;
    d.innerHTML = paso.desh ? "<strong>Aviso de deshielo (experimental).</strong> Hay nieve acumulada en la cordillera y la temperatura está sobre su borde inferior. Con lluvia encima, las quebradas pueden activarse con menos lluvia de la que indican los niveles." : "";

    const vigilar = tramosAVigilar(paso);
    const x = datos.cruces;
    $("tramos").innerHTML = vigilar.length ? vigilar.slice(0, 8).map((t) => `
      <li><button type="button" data-cruce="${t.i}">
        <span class="principal">${esc(x.via[t.i] || "Camino sin nombre")}</span>
        <span class="fecha">${NOMBRE[t.provincia]}</span>
        <span class="secundario">${TIPO_VIA[x.tipo[t.i]] || x.tipo[t.i]} · ${esc(x.comuna[t.i])} · drenan ${fmtNum(x.area[t.i])} km²</span>
      </button></li>`).join("") + (vigilar.length > 8 ? `<li class="vacio">Y ${vigilar.length - 8} más en el mapa (puntos con borde blanco).</li>` : "")
      : `<li class="vacio">Ninguna provincia con alerta: no hay tramos que destacar.</li>`;

    const rep = reportesHasta(paso).slice().sort((a, b) => b.fecha.localeCompare(a.fecha));
    $("reportes").innerHTML = rep.length ? rep.slice(0, 6).map((a, k) => `
      <li><button type="button" data-reporte="${datos.act.indexOf(a)}">
        <span class="principal">${esc(a.quebrada ? `Quebrada ${a.quebrada}` : "Quebrada sin nombre")}</span>
        <span class="fecha">${fecha(a.fecha, false)}</span>
        <span class="secundario">${EVIDENCIA[a.evidencia] || a.evidencia} · ${esc(a.comuna || "")}${a.via ? " · " + esc(a.via) : ""}</span>
      </button></li>`).join("") + (rep.length > 6 ? `<li class="vacio">Y ${rep.length - 6} más en el mapa.</li>` : "")
      : `<li class="vacio">${e.vivo ? "Este boletín es de hoy: las activaciones se conocen después." : "Ninguna reportada hasta este momento del temporal."}</li>`;
  }

  // ------------------------------------------------------ la línea de tiempo
  function grafico() {
    const e = estado.esc, svg = $("grafico");
    const w = Math.max(200, svg.clientWidth), h = 70;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const u = datos.resumen.umbrales, n = e.pasos.length;
    const max = Math.max(0.5, ...e.pasos.flatMap((p) => PROVINCIAS.map((q) => p.prov[q][2] || 0)));
    const y = (v) => h - 4 - Math.sqrt(Math.max(0, v) / max) * (h - 12);
    const x = (i) => n === 1 ? w / 2 : 4 + i / (n - 1) * (w - 8);
    let s = "";
    for (const [k, nombre] of ["amarilla", "naranja", "roja"].entries()) {
      s += `<line x1="0" x2="${w}" y1="${y(u[nombre])}" y2="${y(u[nombre])}" stroke="rgb(${COLOR_NIVEL[k + 1].join(",")})" stroke-opacity=".55" stroke-dasharray="3 3" stroke-width="1"/>`;
    }
    s += `<text x="${w - 2}" y="${y(max) + 9}" text-anchor="end" font-size="9" fill="#6f7a7b" font-family="Overpass Mono, monospace">${Math.round(max * 100)} % de un año</text>`;
    for (const p of PROVINCIAS) {
      const pts = e.pasos.map((ps, i) => `${x(i).toFixed(1)},${y(ps.prov[p][2] || 0).toFixed(1)}`).join(" ");
      s += `<polyline points="${pts}" fill="none" stroke="${COLOR_PROV[p]}" stroke-width="1.8" stroke-linejoin="round"/>`;
    }
    // las activaciones reportadas, como marcas abajo
    if (!e.vivo) {
      const t0 = new Date(e.pasos[0].t), t1 = new Date(e.pasos[n - 1].t);
      const vistas = new Set();
      for (const a of datos.act) {
        const t = new Date(a.fecha + "T12:00");
        if (t < t0 || t > t1 || vistas.has(a.fecha)) continue;
        vistas.add(a.fecha);
        const xi = 4 + (t - t0) / (t1 - t0) * (w - 8);
        s += `<path d="M${xi - 4},${h} L${xi},${h - 7} L${xi + 4},${h} Z" fill="#e5484d"/>`;
      }
    }
    s += `<line id="cursor" x1="${x(estado.i)}" x2="${x(estado.i)}" y1="0" y2="${h}" stroke="#ebe6dc" stroke-width="1.5"/>`;
    svg.innerHTML = s;
    const ej = n === 1 ? [e.pasos[0].t] : [e.pasos[0].t, e.pasos[Math.floor(n / 2)].t, e.pasos[n - 1].t];
    $("ejes").innerHTML = ej.map((t) => `<span>${fecha(t)}</span>`).join("");
  }

  function moverCursor() {
    const e = estado.esc, svg = $("grafico"), c = svg.querySelector("#cursor");
    if (!c) return;
    const w = Math.max(200, svg.clientWidth), n = e.pasos.length;
    const xi = n === 1 ? w / 2 : 4 + estado.i / (n - 1) * (w - 8);
    c.setAttribute("x1", xi); c.setAttribute("x2", xi);
  }

  // ------------------------------------------------------------ las fichas
  function ficha(html) {
    const f = $("ficha");
    f.hidden = !html;
    f.innerHTML = html ? `<button class="cerrar" type="button" aria-label="Cerrar ficha">×</button>${html}` : "";
    if (html) f.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function fichaCruce(i) {
    const x = datos.cruces, clase = CLASE[x.clase[i]] || x.clase[i];
    return `<h3>${esc(x.via[i] || "Camino sin nombre en OpenStreetMap")}</h3>
      <p>${TIPO_VIA[x.tipo[i]] || x.tipo[i]} en ${esc(x.comuna[i])}. Aquí cruza el cauce de una quebrada: ${esc(clase)}.</p>
      <p>Hasta este punto drenan ${fmtNum(x.area[i], x.area[i] < 10 ? 1 : 0)} km² de cuenca. Es el cruce número ${fmtNum(x.rank[i])} de ${fmtNum(x.total)} en la lista de prioridad de la región.</p>
      <p>Es un candidato a corte, no un corte anunciado.</p>`;
  }
  function fichaEstacion(i, paso) {
    const e = datos.estaciones, v = paso.est.find((r) => r[0] === i);
    return `<h3>Pluviómetro ${esc(e.nombre[i])}</h3>
      <p>A ${fmtNum(e.altitud[i])} m de altura${e.normal[i] ? `. En un año normal llueven aquí ${fmtNum(e.normal[i])} mm` : ""}.</p>
      <p>${v ? `En este temporal: ${fmtNum(v[1], 1)} mm, el ${fmtPct(v[2])} de un año normal.` : "En este temporal no ha registrado lluvia válida."}</p>`;
  }
  function fichaReporte(a) {
    return `<h3>${esc(a.quebrada ? `Quebrada ${a.quebrada}` : "Quebrada sin nombre")}${a.comuna ? `, ${esc(a.comuna)}` : ""}</h3>
      <p>${fecha(a.fecha, false)}. ${EVIDENCIA[a.evidencia] || a.evidencia}${a.via ? `, ${esc(a.via)}` : ""}.</p>
      <p>Ubicación: ${esc(a.precision)}.${a.url ? ` <a href="${esc(a.url)}" target="_blank" rel="noopener">Ver la fuente${a.fuente ? ` (${esc(a.fuente)})` : ""}</a>` : ""}</p>`;
  }
  function fichaQuebrada(d) {
    const clase = CLASE[d.clase] || d.clase;
    return `<h3>${esc(d.nombre_osm || "Quebrada sin nombre en OpenStreetMap")}</h3>
      <p>${esc(clase)}. Cuenca de ${fmtNum(d.area_km2, d.area_km2 < 10 ? 1 : 0)} km².</p>`;
  }

  function alTocar({ layer, object }) {
    if (!object || !layer) { ficha(""); return; }
    const paso = estado.esc.pasos[estado.i];
    if (layer.id === "cruces" || layer.id === "vigilar") ficha(fichaCruce(object.i));
    else if (layer.id === "estaciones") ficha(fichaEstacion(object.i, paso));
    else if (layer.id === "reportes") ficha(fichaReporte(object));
    else if (layer.id === "grandes" || layer.id === "chicas") ficha(fichaQuebrada(object));
    else if (layer.id === "rutas") ficha(`<h3>${esc(object.name || "Ruta sin nombre")}</h3><p>${TIPO_VIA[object.highway] || object.highway}.</p>`);
  }

  function etiqueta({ layer, object }) {
    if (!object || !layer) return null;
    let t = null;
    if (layer.id === "cruces" || layer.id === "vigilar") t = datos.cruces.via[object.i] || "Camino sin nombre";
    else if (layer.id === "estaciones") t = datos.estaciones.nombre[object.i];
    else if (layer.id === "reportes") t = `${object.quebrada ? "Quebrada " + object.quebrada : "Quebrada sin nombre"} · ${fecha(object.fecha, false)}`;
    else if (layer.id === "grandes") t = object.nombre_osm || "Quebrada grande";
    if (!t) return null;
    return { text: t, style: { background: "#121a1e", color: "#ebe6dc", font: "13px Atkinson Hyperlegible, sans-serif", border: "1px solid #263239", borderRadius: "6px", padding: "4px 8px" } };
  }

  function volarA(position, zoom = 10.2) {
    mapa.setProps({ initialViewState: { ...vistaActual, longitude: position[0], latitude: position[1], zoom, pitch: 55, transitionDuration: 1400, transitionInterpolator: new deck.FlyToInterpolator() } });
  }

  // ---------------------------------------------------------- el control
  let vistaActual, vistaInicial;
  // La flecha roja apunta al norte: con la costa adelante, el norte queda a la izquierda.
  const girarBrujula = (rumbo) => { $("brujula").querySelector("svg").style.transform = `rotate(${-rumbo}deg)`; };
  // La textura se pinta de forma asincrona. Si mientras tanto se pidio otro
  // paso, el resultado viejo se descarta para no dibujar un nivel atrasado.
  let pedido = 0;
  async function dibujar() {
    const paso = estado.esc.pasos[estado.i], mio = ++pedido;
    const textura = await componer([0, ...PROVINCIAS.map((p) => paso.prov[p][0])]);
    if (mio !== pedido) return;
    mapa.setProps({ layers: capas(paso, textura) });
    panel(paso);
    $("deslizador").value = estado.i;
    moverCursor();
  }

  function elegir(id, momento) {
    detener();
    estado.esc = datos.escenarios.find((e) => e.id === id);
    const pasos = estado.esc.pasos;
    let i = pasos.length - 1;
    if (momento) { const k = pasos.findIndex((p) => p.t === momento); if (k >= 0) i = k; }
    else if (!estado.esc.vivo) i = 0;
    estado.i = i;
    for (const b of $("escenarios").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.id === id));
    $("deslizador").max = pasos.length - 1;
    $("deslizador").disabled = pasos.length === 1;
    $("reproducir").disabled = pasos.length === 1;
    ficha("");
    grafico();
    dibujar();
  }

  const ICONO_PLAY = '<svg viewBox="0 0 16 16"><path d="M3 1.5v13l11-6.5z" fill="currentColor"/></svg>';
  const ICONO_PAUSA = '<svg viewBox="0 0 16 16"><path d="M3 1.5h3.5v13H3zM9.5 1.5H13v13H9.5z" fill="currentColor"/></svg>';
  function detener() {
    clearInterval(estado.timer); estado.timer = null;
    $("reproducir").innerHTML = ICONO_PLAY; $("reproducir").setAttribute("aria-label", "Reproducir");
  }
  function reproducir() {
    if (estado.timer) { detener(); return; }
    const n = estado.esc.pasos.length;
    if (estado.i >= n - 1) estado.i = 0;
    $("reproducir").innerHTML = ICONO_PAUSA; $("reproducir").setAttribute("aria-label", "Pausar");
    estado.timer = setInterval(() => {
      if (estado.i >= n - 1) { detener(); return; }
      estado.i += 1; dibujar();
    }, 650);
  }

  // ------------------------------------------------------------- arranque
  async function iniciar() {
    const [quebradas, rutasJ, provincias, cruces, estaciones, localidades, activaciones, resumen, escenarios,
      imAltura, imRelieve, imProv] = await Promise.all([
      json("quebradas.json"), json("rutas.json"), json("provincias.json"), json("cruces.json"),
      json("estaciones.json"), json("localidades.json"), json("activaciones.json"), json("resumen.json"),
      json("escenarios.json"), imagen("elevacion.png"), imagen("relieve.png"), imagen("provincias.png")]);
    datos = { quebradas, rutas: rutasJ, provincias, cruces, estaciones, localidades, activaciones, resumen, escenarios };
    alto = prepararAltura(imAltura, resumen.caja);
    componer = prepararTextura(imRelieve, imProv);
    prepararCapas();

    // cifras de la explicación, desde los datos
    $("n-cruces").textContent = fmtNum(cruces.total);
    $("n-estaciones").textContent = fmtNum(resumen.estaciones);
    $("n-cuencas").textContent = fmtNum(resumen.cuencas);
    const u = resumen.umbrales, pr = resumen.prueba_2026;
    $("tabla-niveles").innerHTML = ["amarilla", "naranja", "roja"].map((n, k) =>
      `<div style="background:rgb(${COLOR_NIVEL[k + 1].join(",")})"><b>${n}</b><span>${Math.round(u[n] * 100)} %</span><small>${["una de cada cuatro", "una de cada dos", "tres de cada cuatro"][k]} veces hubo activaciones</small></div>`).join("");
    $("confianza").textContent = `Los cortes salen de tres inviernos (2024-2026), en los que ${resumen.positivos_calibracion} veces una provincia tuvo quebradas activadas durante un temporal. En 2026, que el modelo no conocía al ajustarse, de las ${pr.naranja_o_roja} provincias que puso en naranja o roja, ${pr.con_activaciones} tuvieron quebradas activadas; de las ${pr.sin_nivel} que dejó sin alerta, ${pr.sin_nivel_con_activaciones === 0 ? "ninguna" : pr.sin_nivel_con_activaciones}. Con tan pocos casos, es una herramienta de apoyo y no un pronóstico.`;

    $("escenarios").innerHTML = escenarios.map((e) =>
      `<button type="button" data-id="${e.id}" aria-pressed="false" title="${esc(e.resumen)}">${e.vivo ? '<span class="vivo"></span>' : ""}${esc(e.titulo)}</button>`).join("");
    $("escenarios").addEventListener("click", (ev) => { const b = ev.target.closest("button"); if (b) elegir(b.dataset.id); });

    vistaActual = TELEFONO
      ? { longitude: -70.85, latitude: -30.65, zoom: 6.25, pitch: 45, bearing: -12, maxPitch: 75 }
      : { longitude: -70.55, latitude: -31.2, zoom: 7.3, pitch: 56, bearing: 90, maxPitch: 75 };
    vistaInicial = { ...vistaActual };
    $("cargando").remove();
    mapa = new deck.Deck({
      // En un teléfono la rueda no hace zoom: así deslizar la página no queda
      // atrapado dentro del mapa.
      parent: $("mapa"), initialViewState: vistaActual, controller: TELEFONO ? { scrollZoom: false } : true,
      onViewStateChange: ({ viewState }) => { vistaActual = viewState; girarBrujula(viewState.bearing); },
      getTooltip: etiqueta, onClick: alTocar, layers: [],
      parameters: { clearColor: [13 / 255, 18 / 255, 21 / 255, 1] },
    });

    girarBrujula(vistaActual.bearing);
    $("brujula").addEventListener("click", () => {
      mapa.setProps({ initialViewState: { ...vistaInicial, transitionDuration: 1200, transitionInterpolator: new deck.FlyToInterpolator() } });
    });
    $("deslizador").addEventListener("input", (ev) => { detener(); estado.i = +ev.target.value; dibujar(); });
    $("reproducir").addEventListener("click", reproducir);
    for (const id of ["capa-quebradas", "capa-chicas", "capa-rutas", "capa-cruces", "capa-estaciones", "capa-reportes"])
      $(id).addEventListener("change", dibujar);
    $("panel").addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      if (b.classList.contains("cerrar")) { ficha(""); return; }
      if (b.dataset.cruce) { const i = +b.dataset.cruce; ficha(fichaCruce(i)); volarA(todosLosCruces[i].position); }
      if (b.dataset.reporte) { const a = datos.act[+b.dataset.reporte]; ficha(fichaReporte(a)); volarA(a.position, 9.6); }
    });
    $("abrir-explicacion").addEventListener("click", () => {
      $("explicacion").hidden = false;
      $("explicacion").querySelector(".caja").scrollTop = 0;
      $("cerrar-explicacion").focus({ preventScroll: true });
    });
    $("cerrar-explicacion").addEventListener("click", () => { $("explicacion").hidden = true; });
    $("explicacion").addEventListener("click", (ev) => { if (ev.target.id === "explicacion") $("explicacion").hidden = true; });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") $("explicacion").hidden = true; });
    window.addEventListener("resize", () => { grafico(); });

    // Se abre en el temporal de julio de 2026, a la hora en que las tres
    // provincias ya estaban en roja: el primer cuadro cuenta la historia.
    const julio = escenarios.find((e) => e.id === "julio-2026");
    if (julio) elegir("julio-2026", "2026-07-17T09:00");
    else elegir(escenarios[0].id);
  }

  iniciar().catch((err) => {
    const c = $("cargando");
    if (c) c.textContent = `No se pudo cargar el visor: ${err.message}`;
    console.error(err);
  });
})();
