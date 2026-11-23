"use strict";
const el = key => document.getElementById(key);
let config, scenes = [], cards = [], busy = false, repeatIndex, downloading = false;

function announce(text, error = false) {
  el("status").textContent = text;
  el("status").classList.toggle("error", error);
}

async function request(path, data) {
  const response = await fetch(path, data ? {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Studio-Token": config.token},
    body: JSON.stringify(data)
  } : {});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "No se pudo completar la solicitud.");
  return value;
}

function control(tag, text, parent, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  parent.append(node);
  return node;
}

function update() {
  const ready = !!(config && el("voice").value && scenes.length && scenes.every(scene => scene.texto.trim()));
  el("run").disabled = !ready || busy || downloading;
  el("downloadAll").disabled = busy || downloading || !cards.length || cards.some(card => card.download.hidden);
  const target = scenes[repeatIndex];
  el("repeatAudio").disabled = !target || !ready || busy || downloading;
  el("repeatTarget").textContent = target
    ? `Reel ${target.reel} · diálogo ${target.id}`
    : "Escuchá un diálogo o generá un piloto para elegir el audio.";
  for (const key of ["file", "voice", "language", "output"]) el(key).disabled = busy || downloading;
  for (const card of cards) {
    card.button.disabled = !ready || busy || downloading;
    card.editor.readOnly = busy || downloading;
  }
}

function draw() {
  el("sceneList").replaceChildren();
  cards = [];
  const groups = new Map();
  scenes.forEach((scene, index) => {
    const reel = String(scene.reel);
    if (!groups.has(reel)) {
      const group = control("section", "", el("sceneList"), "reel-group");
      control("h2", "Reel " + reel, group);
      groups.set(reel, group);
    }
    const card = control("article", "", groups.get(reel), "scene workspace");
    const play = control("button", "▶", card, "soft scene-play");
    play.type = "button";
    play.disabled = true;
    play.title = "Reproducir";
    play.setAttribute("aria-label", "Reproducir reel " + reel + ", diálogo " + scene.id);
    const block = control("div", "", card, "scene-text");
    const label = control("label", "Diálogo " + scene.id, block);
    label.htmlFor = "scene-" + index;
    const editor = control("textarea", "", block);
    editor.id = label.htmlFor;
    editor.value = scene.texto;
    editor.maxLength = 5000;
    editor.rows = 2;
    editor.oninput = () => {
      scene.texto = editor.value;
      setScene(index, {estado: "editado"});
      update();
    };
    const info = control("div", "", block, "scene-meta");
    const indicator = control("div", "Pendiente", info, "indicator");
    control("small", scene.archivo, info);
    const failure = control("div", "", info, "error");
    const actions = control("div", "", card, "scene-actions");
    const button = control("button", "Generar piloto", actions, "soft");
    button.onclick = () => generate(index);
    const download = control("a", "", actions, "button ghost scene-download");
    const downloadLabel = "Descargar reel " + reel + ", diálogo " + scene.id;
    download.title = downloadLabel;
    download.setAttribute("aria-label", downloadLabel);
    download.download = scene.archivo.split("/").at(-1);
    download.hidden = true;
    download.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3v12m-5-5 5 5 5-5M5 16v4h14v-4"/></svg>';
    const audio = control("audio", "", block);
    audio.preload = "none";
    play.onclick = async () => {
      if (!audio.paused) {
        audio.pause();
        return;
      }
      for (const other of cards) {
        if (other.audio !== audio) other.audio.pause();
      }
      try { await audio.play(); }
      catch { announce("No se pudo reproducir el audio de este diálogo.", true); }
    };
    function playback(isPlaying) {
      play.textContent = isPlaying ? "Ⅱ" : "▶";
      play.title = isPlaying ? "Pausar" : "Reproducir";
      play.setAttribute("aria-label", play.title + " reel " + reel + ", diálogo " + scene.id);
    }
    audio.addEventListener("pause", () => playback(false));
    audio.addEventListener("ended", () => playback(false));
    audio.addEventListener("play", () => {
      playback(true);
      repeatIndex = index;
      update();
    });
    audio.hidden = true;
    cards.push({card, indicator, failure, button, audio, editor, play, download});
  });
  update();
}

function setScene(index, scene, batch) {
  const {card, indicator, failure, audio, button, play, download} = cards[index];
  card.dataset.state = scene.estado;
  indicator.textContent = scene.estado === "listo"
    ? (scene.reutilizado ? "Reutilizado" : "Listo") + " · " + scene.duracion_real.toFixed(2) + " s"
    : ({editado: "Texto editado", pendiente: "Pendiente", error: "Error", generando: "Generando…", "en cola": "En cola"})[scene.estado];
  failure.textContent = scene.error || "";
  button.textContent = scene.estado === "listo" ? "Regenerar frase" : "Generar piloto";
  if (scene.estado === "listo" && batch) {
    const url = "/api/reels/audio/" + batch + "/" + index;
    if (audio.getAttribute("src") !== url) audio.src = url;
    play.disabled = false;
    download.href = url;
    download.hidden = false;
  } else if (!play.disabled) {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    play.disabled = true;
    download.hidden = true;
    download.removeAttribute("href");
  }
}

async function generate(index) {
  busy = true;
  update();
  announce("Enviando guion al motor local…");
  const payload = {guion: scenes, voz: el("voice").value, idioma: el("language").value,
    salida: el("output").value.trim() || undefined};
  if (index !== undefined) {
    payload.solo = [{reel: scenes[index].reel, id: scenes[index].id}];
    payload.regenerar = true;
  }
  try {
    const batch = await request("/api/reels", payload);
    el("output").value = batch.salida;
    if (index !== undefined) repeatIndex = index;
    let job;
    do {
      await new Promise(resolve => setTimeout(resolve, 850));
      job = await request("/api/jobs/" + batch.id);
      if (job.manifest) {
        const entries = job.manifest.escenas;
        entries.forEach((scene, n) => setScene(n, scene, batch.id));
        const ready = entries.filter(scene => scene.estado === "listo").length;
        el("summary").textContent = ready + " / " + entries.length + " listos";
        const warnings = el("warnings");
        warnings.replaceChildren();
        job.manifest.avisos.forEach(warning => control("p", warning, warnings));
        warnings.hidden = !job.manifest.avisos.length;
      }
      announce(job.message, job.state === "error" || job.state === "partial");
    } while (job.state === "running");
    if (job.state === "done") announce("Lote " + batch.id + " · WAV y manifiesto guardados en la carpeta de salida.");
  } catch (error) {
    announce(error.message, true);
  } finally {
    busy = false;
    update();
  }
}

el("file").onchange = async () => {
  try {
    const file = el("file").files[0];
    if (!file) return;
    const data = JSON.parse(await file.text());
    if (!Array.isArray(data) || !data.length || data.length > 250 || data.some(scene => !scene ||
        scene.reel === undefined || scene.id === undefined || typeof scene.texto !== "string" ||
        typeof scene.archivo !== "string" || scene.inicio === undefined || scene.duracion === undefined)) {
      throw new Error("Importá un JSON con reel, id, texto, inicio, duracion y archivo en cada diálogo.");
    }
    scenes = data;
    repeatIndex = undefined;
    el("output").value = "";
    el("summary").textContent = "";
    el("warnings").hidden = true;
    el("fileDetail").textContent = scenes.length + " diálogos en " + new Set(scenes.map(scene => scene.reel)).size + " reels";
    announce("");
    draw();
  } catch (error) {
    announce(error.message, true);
  }
};
el("voice").onchange = () => {
  const item = config.references.find(voice => voice.id === el("voice").value);
  const audio = el("voiceAudio");
  audio.hidden = !item;
  if (item) audio.src = "/audio/" + encodeURIComponent(item.id);
  else { audio.removeAttribute("src"); audio.load(); }
  cards.forEach((_, index) => setScene(index, {estado: "pendiente"}));
  update();
};
el("language").onchange = () => cards.forEach((_, index) => setScene(index, {estado: "pendiente"}));
const crcTable = Uint32Array.from({length: 256}, (_, value) => {
  for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);
  return value;
});

function zipFiles(files) {
  const encoder = new TextEncoder();
  const local = [], central = [];
  let offset = 0, directorySize = 0;
  for (const {path, bytes} of files) {
    const name = encoder.encode(path);
    let crc = 0xffffffff;
    for (const byte of bytes) crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 255];
    crc = (crc ^ 0xffffffff) >>> 0;
    const header = new DataView(new ArrayBuffer(30));
    const index = new DataView(new ArrayBuffer(46));
    header.setUint32(0, 0x04034b50, true);
    header.setUint16(4, 20, true);
    header.setUint16(6, 0x0800, true);
    header.setUint16(12, 0x21, true);
    header.setUint32(14, crc, true);
    header.setUint32(18, bytes.length, true);
    header.setUint32(22, bytes.length, true);
    header.setUint16(26, name.length, true);
    index.setUint32(0, 0x02014b50, true);
    index.setUint16(4, 20, true);
    new Uint8Array(index.buffer, 6, 26).set(new Uint8Array(header.buffer, 4, 26));
    index.setUint32(42, offset, true);
    local.push(header.buffer, name, bytes);
    central.push(index.buffer, name);
    offset += 30 + name.length + bytes.length;
    directorySize += 46 + name.length;
    if (offset + directorySize > 0xffffffff) throw new Error("El ZIP supera el tamaño máximo. Descargá los WAV por separado.");
  }
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.length, true);
  end.setUint16(10, files.length, true);
  end.setUint32(12, directorySize, true);
  end.setUint32(16, offset, true);
  return new Blob([...local, ...central, end.buffer], {type: "application/zip"});
}

el("downloadAll").onclick = async () => {
  const links = cards.map((card, index) => ({url: card.download.href, path: scenes[index].archivo}));
  downloading = true;
  update();
  announce("Preparando el ZIP de audios…");
  try {
    const files = [];
    for (const {url, path} of links) {
      const response = await fetch(url);
      if (!response.ok) throw new Error("No se pudo descargar " + path + ".");
      files.push({path, bytes: new Uint8Array(await response.arrayBuffer())});
    }
    const href = URL.createObjectURL(zipFiles(files));
    const link = document.createElement("a");
    link.href = href;
    link.download = "audios-del-guion.zip";
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 30000);
    announce("ZIP listo con " + files.length + " audios.");
  } catch (error) {
    announce(error.message, true);
  } finally {
    downloading = false;
    update();
  }
};
el("run").onclick = () => generate();
el("repeatAudio").onclick = () => {
  if (repeatIndex !== undefined) generate(repeatIndex);
};
request("/api/setup").then(data => {
  config = data;
  for (const item of data.references) {
    el("voice").add(new Option([item.name, item.tone, item.id].filter(Boolean).join(" · "), item.id));
  }
  for (const language of data.languages) el("language").add(new Option(language === "Spanish" ? "Español" : language, language));
  update();
}).catch(error => announce(error.message, true));
