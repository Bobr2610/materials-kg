async function postJson(url, payload = {}) {
  const r = await fetch(url, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
  if (!r.ok) {
    const text = await r.text();
    let message = text || r.statusText;
    try {
      const body = JSON.parse(text);
      message = body.detail || body.error || message;
    } catch {
      // Keep plain-text HTTP errors readable.
    }
    throw new Error(message);
  }
  return r.json();
}

function endpointWithParams(path, params = {}) {
  const search = new URLSearchParams(params).toString();
  return search ? path + "?" + search : path;
}

async function downloadFromPost(url, payload, filename) {
  const r = await fetch(url, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  if (!r.ok) throw new Error(await r.text() || r.statusText);
  const blob = await r.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
