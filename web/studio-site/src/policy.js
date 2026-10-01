// The headers the studio's pages are served with: the static page (tools/prepare.mjs writes them into _headers) and
// /v/<id> (the Worker). As strict as the studio's own, with what the browser's renderer needs: Pyodide compiles
// WebAssembly ('wasm-unsafe-eval', never 'unsafe-eval'), and a song made in the browser plays from a Blob (blob:
// media). Scripts, workers and requests only from here; no frames, forms or base. The microphone is left to the
// page itself (Permissions-Policy names only what it never uses).
export const PAGE_POLICY = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' data:; " +
  "media-src 'self' blob:; connect-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

export const SECURITY = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Strict-Transport-Security": "max-age=15552000",
};

export const PAGE = { "Content-Security-Policy": PAGE_POLICY, ...SECURITY, "Permissions-Policy": "camera=(), geolocation=(), payment=(), usb=()" };
