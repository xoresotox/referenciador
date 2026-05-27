const form = document.getElementById("ref-form");
const submitBtn = document.getElementById("submit-btn");
const resultBox = document.getElementById("result");
const refPre = document.getElementById("reference");
const metaTable = document.getElementById("meta-table");
const errorBox = document.getElementById("error");
const errorMsg = document.getElementById("error-msg");
const copyBtn = document.getElementById("copy-btn");

const META_LABELS = {
  title: "Título",
  authors: "Autores",
  year: "Año",
  publisher: "Editor",
  institution: "Institución",
  type: "Tipo",
  language: "Idioma",
  handle: "Handle",
  doi: "DOI",
  advisor: "Asesor",
  degree: "Grado",
};

function showError(msg) {
  resultBox.hidden = true;
  errorBox.hidden = false;
  errorMsg.textContent = msg;
}

function showResult(data) {
  errorBox.hidden = true;
  resultBox.hidden = false;
  refPre.textContent = data.reference;

  metaTable.innerHTML = "";
  for (const [key, label] of Object.entries(META_LABELS)) {
    const value = data.metadata[key];
    if (!value || (Array.isArray(value) && value.length === 0)) continue;
    const tr = document.createElement("tr");
    const tdK = document.createElement("td");
    tdK.textContent = label;
    const tdV = document.createElement("td");
    tdV.textContent = Array.isArray(value) ? value.join("; ") : value;
    tr.appendChild(tdK);
    tr.appendChild(tdV);
    metaTable.appendChild(tr);
  }
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const url = document.getElementById("url").value.trim();
  const style = document.querySelector('input[name="style"]:checked').value;

  submitBtn.disabled = true;
  submitBtn.textContent = "Generando…";
  errorBox.hidden = true;
  resultBox.hidden = true;

  try {
    const resp = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, style }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      showError(data.error || `Error HTTP ${resp.status}`);
    } else {
      showResult(data);
    }
  } catch (err) {
    showError("No se pudo contactar al servidor: " + err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Generar referencia";
  }
});

copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(refPre.textContent);
    copyBtn.textContent = "¡Copiado!";
    copyBtn.classList.add("copied");
    setTimeout(() => {
      copyBtn.textContent = "Copiar";
      copyBtn.classList.remove("copied");
    }, 1800);
  } catch {
    /* clipboard no disponible */
  }
});
