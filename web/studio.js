"use strict";
const id = name => document.getElementById(name);
const pages = [...document.querySelectorAll("[data-page]")];
const tabs = [...document.querySelectorAll("nav [data-step]")];
const transcript = id("transcript"), script = id("script"), tone = id("tone"), saved = id("saved");
let setup, selected, recording, stream, transcribing, busy = false, uploading = false, exampleIndex = 0, samples;
const tips = [
  ["La intención está en tu voz", "Grabá la lectura con el tono que querés reproducir. La muestra le da a Qwen el timbre y una referencia de cómo hablás."],
  ["Tu voz, nuevas palabras", "Usá la puntuación para sugerir pausas. Los signos de pregunta y exclamación ayudan a marcar la intención del guion."],
  ["Escuchá y compará", "Probá otra referencia si querés explorar una interpretación distinta del mismo texto."]
];

function status(message = "", isError = false) {
  id("status").textContent = message;
  id("status").classList.toggle("error", isError);
}

async function api(path, payload) {
  const options = payload === undefined ? {} : {
    method: "POST",
    headers: {"X-Studio-Token": setup.token, "Content-Type": payload instanceof Blob ? "application/octet-stream" : "application/json"},
    body: payload instanceof Blob ? payload : JSON.stringify(payload)
  };
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "El servidor local no pudo completar la solicitud.");
  return value;
}

function show(index) {
  if (recording && index !== 0) {
    status("Detené la grabación antes de continuar.", true);
    return;
  }
  document.querySelector('.steps').style.setProperty('--step', index);
  pages.forEach((page, n) => page.hidden = index !== n);
  tabs.forEach((tab, n) => n === index ? tab.setAttribute("aria-current", "step") : tab.removeAttribute("aria-current"));
  id("tipTitle").textContent = tips[index][0];
  id("tipBody").textContent = tips[index][1];
  if (index === 2) draw();
}

function update() {
  const ready = Boolean(selected && transcript.value.trim() && !recording && !uploading);
  id("transcribe").disabled = !selected || Boolean(transcribing || recording || uploading);
  id("continue").disabled = !ready || Boolean(transcribing);
  id("saveRef").disabled = !ready || Boolean(transcribing);
  id("generate").disabled = busy || Boolean(transcribing) || !ready || !script.value.trim();
  id("count").textContent = script.value.length + " / 5000";
  saved.disabled = Boolean(recording || uploading || transcribing);
  id("upload").disabled = Boolean(recording || uploading || transcribing);
  id("uploadButton").disabled = id("upload").disabled;
  id("record").disabled = uploading || Boolean(transcribing) || !setup;
}

function pick(item) {
  selected = item;
  id("referenceName").value = "";
  id("sample").hidden = !item;
  if (!item) {
    id("referenceAudio").removeAttribute("src");
    id("referenceAudio").load();
  } else {
    id("sampleName").textContent = item.name;
    id("referenceAudio").src = "/audio/" + encodeURIComponent(item.id);
  }
  update();
}

function refresh() {
  saved.replaceChildren(new Option("Elegí una referencia", ""));
  for (const item of setup.references) {
    const label = setup.tones.find(t => t.id === item.tone)?.label || item.tone;
    saved.add(new Option(item.name + (label ? " · " + label : ""), item.id));
  }
}

function hint() {
  id("hint").textContent = setup.tones.find(t => t.id === tone.value).hint;
}

function chooseSaved() {
  const item = setup.references.find(ref => ref.id === saved.value);
  transcript.value = item?.transcript || "";
  const style = setup.tones.find(t => t.id === item?.tone || t.label === item?.tone);
  if (style) {
    tone.value = style.id;
    exampleIndex = 0;
    hint();
  }
  pick(item);
  status();
}

async function transcribe(confirmReplace = false) {
  if (!selected || transcribing) return;
  const source = selected.id;
  const draft = transcript.value;
  if (confirmReplace && draft.trim() && !confirm("¿Volver a transcribir esta muestra? El resultado reemplazará el texto actual.")) return;
  transcribing = source;
  update();
  status("Transcribiendo tu audio con Whisper…");
  try {
    const job = await api("/api/transcribe", {id: source, language: "Auto"});
    let result;
    do {
      await new Promise(resolve => setTimeout(resolve, 750));
      result = await api("/api/jobs/" + job.id);
    } while (result.state === "running");
    if (result.state === "error") throw new Error(result.message);
    if (selected?.id !== source) return;
    if (transcript.value !== draft) {
      status("Conservé tu edición. Podés volver a transcribir si querés reemplazarla.");
      return;
    }
    transcript.value = result.text;
    status("Transcripción lista. Corregí cualquier palabra antes de seguir.");
  } catch (error) {
    if (selected?.id === source) status(error.message, true);
  } finally {
    transcribing = undefined;
    update();
  }
}
async function upload(blob, name, preserveTranscript) {
  uploading = true;
  update();
  status("Preparando la muestra de voz…");
  try {
    const {id: key} = await api("/api/upload", blob);
    if (!preserveTranscript) transcript.value = "";
    saved.value = "";
    pick({id: key, name, tone: preserveTranscript ? tone.value : ""});
    transcribe();
  } catch (error) {
    status(error.message, true);
  } finally {
    uploading = false;
    update();
  }
}

function stopMic() {
  stream?.getTracks().forEach(track => track.stop());
  stream = undefined;
  recording = undefined;
  id("record").classList.remove("recording");
  id("record").lastElementChild.textContent = "Grabar lectura";
  update();
}

async function toggleRecording() {
  if (recording) {
    if (recording.state === "recording") recording.stop();
    return;
  }
  uploading = true;
  update();
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const activeRecording = new MediaRecorder(stream);
    recording = activeRecording;
    const chunks = [];
    recording.ondataavailable = event => chunks.push(event.data);
    recording.onerror = () => { stopMic(); status("No pude completar la grabación.", true); };
    recording.onstop = () => {
      if (recording !== activeRecording) return;
      const audio = new Blob(chunks, {type: activeRecording.mimeType});
      stopMic();
      upload(audio, "Lectura grabada", true);
    };
    recording.start();
    id("referenceAudio").pause();
    id("record").classList.add("recording");
    id("record").lastElementChild.textContent = "Detener grabación";
    status("Grabando desde el micrófono…");
  } catch {
    stopMic();
    status("No se pudo abrir el micrófono. Revisá el permiso del navegador.", true);
  } finally {
    uploading = false;
    update();
  }
}

function draw() {
  const canvas = id("waveform");
  const {width, height} = canvas.getBoundingClientRect();
  if (!width) return;
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  const gradient = ctx.createLinearGradient(0, 0, width, 0);
  gradient.addColorStop(0, "#ad72df");
  gradient.addColorStop(.55, "#7850d6");
  gradient.addColorStop(1, "#30866d");
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  const bars = Math.min(90, Math.max(24, Math.floor(width / 7)));
  for (let i = 0; i < bars; i++) {
    let peak = 0;
    if (samples) {
      const start = Math.floor(samples.length * i / bars);
      const end = Math.floor(samples.length * (i + 1) / bars);
      for (let j = start; j < end; j += 3) peak = Math.max(peak, Math.abs(samples[j]));
    }
    const x = width * (i + .5) / bars;
    const amplitude = 2 + peak * height * .46;
    ctx.beginPath();
    ctx.moveTo(x, height / 2 - amplitude);
    ctx.lineTo(x, height / 2 + amplitude);
    ctx.stroke();
  }
}

async function generate() {
  const submittedScript = script.value.trim();
  busy = true;
  update();
  samples = undefined;
  id("resultAudio").pause();
  id("resultAudio").hidden = true;
  id("resultScript").hidden = true;
  id("resultScriptText").textContent = "";
  id("download").hidden = true;
  id("resultBox").classList.add("busy");
  show(2);
  status();
  id("resultMessage").textContent = "Preparando la muestra…";
  try {
    const job = await api("/api/generate", {
      id: selected.id, transcript: transcript.value, text: submittedScript, language: id("language").value
    });
    let result;
    do {
      await new Promise(resolve => setTimeout(resolve, 850));
      result = await api("/api/jobs/" + job.id);
      id("resultMessage").textContent = result.message;
    } while (result.state === "running");
    if (result.state === "error") throw new Error(result.message);
    id("resultAudio").src = result.url;
    id("resultAudio").hidden = false;
    id("resultScriptText").textContent = submittedScript;
    id("resultScript").hidden = false;
    id("download").href = result.url;
    id("download").download = result.url.split("/").at(-1);
    id("download").hidden = false;
    id("resultMessage").textContent = "Tu audio está listo.";
    const ctx = new AudioContext();
    try {
      const file = await fetch(result.url);
      const decoded = await ctx.decodeAudioData(await file.arrayBuffer());
      samples = decoded.getChannelData(0);
      id("resultMessage").textContent = decoded.duration.toLocaleString("es-AR", {maximumFractionDigits: 1}) + " s · WAV";
      draw();
    } finally {
      await ctx.close();
    }
  } catch (error) {
    id("resultMessage").textContent = id("resultAudio").hidden ? "No se pudo generar el audio." : "Tu audio está listo.";
    status(error.message, true);
  } finally {
    busy = false;
    id("resultBox").classList.remove("busy");
    update();
  }
}

async function initialize() {
  try {
    setup = await api("/api/setup");
    for (const item of setup.tones) tone.add(new Option(item.label, item.id));
    for (const language of setup.languages) id("language").add(new Option(language === "Spanish" ? "Español" : language, language));
    refresh();
    if (setup.references.length) {
      saved.value = setup.references[0].id;
      chooseSaved();
    }
    hint();
    update();
  } catch {
    status("No pude cargar el estudio local. Volvé a abrir el lanzador.", true);
  }
}

document.querySelectorAll("[data-step]").forEach(button => button.onclick = () => show(Number(button.dataset.step)));
id("continue").onclick = () => { status(); show(1); script.focus(); };
saved.onchange = chooseSaved;
tone.onchange = () => { exampleIndex = 0; hint(); };
transcript.oninput = script.oninput = update;
id("example").onclick = () => {
  if (!setup || recording || uploading || transcribing) return;
  const preset = setup.tones.find(t => t.id === tone.value);
  if (selected && !confirm("¿Preparar esta lectura para una nueva grabación?")) return;
  saved.value = "";
  pick(undefined);
  transcript.value = preset.scripts[exampleIndex++ % preset.scripts.length];
  status("Leé el texto con la intención elegida y grabá tu muestra.");
  update();
};
id("uploadButton").onclick = () => id("upload").click();
id("upload").onchange = event => {
  const file = event.target.files[0];
  if (file) upload(file, file.name, false);
  event.target.value = "";
};
id("record").onclick = toggleRecording;
id("transcribe").onclick = () => transcribe(true);
id("saveRef").onclick = async () => {
  id("saveRef").disabled = true;
  try {
    const reference = selected;
    const text = transcript.value.trim();
    const name = id("referenceName").value.trim();
    if (!name) {
      status("Poné un nombre para guardar esta referencia.", true);
      id("referenceName").focus();
      return;
    }
    const savedFile = await api("/api/reference", {...reference, name, transcript: text});
    const key = savedFile.id;
    const savedCopy = {...reference, id: key, name: savedFile.name, transcript: text};
    setup.references.unshift(savedCopy);
    refresh();
    saved.value = key;
    pick(savedCopy);
    status("Guardados en la biblioteca: " + savedFile.audio + " y " + savedFile.transcripcion + ".");
  } catch (error) {
    status(error.message, true);
  } finally {
    update();
  }
};
id("generate").onclick = generate;
new ResizeObserver(draw).observe(id("waveform"));
update();
initialize();
