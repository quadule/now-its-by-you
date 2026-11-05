// The C kernels (kernels.c -> kernels.wasm), instantiated on Pyodide's own memory: their pointers are numpy
// arrays' data addresses, handed over from Python (py/wasm_kernels.py). Math functions come from JS.
//
// Two builds of the same kernels: kernels-simd.wasm (-msimd128) adds matmul_blas, the learned voice's matrix
// product two outputs at a time (py/web_patches.py), and is the one fetched where wasm SIMD validates; elsewhere
// kernels.wasm, and the voice's products stay scipy's dgemm. Either way the same numbers.
export async function loadWasmKernels(bytes, memory) {
  const env = {
    memory, exp: Math.exp, sin: Math.sin, cos: Math.cos, tanh: Math.tanh, log10: Math.log10, pow: Math.pow,
  };
  const { instance } = await WebAssembly.instantiate(bytes, { env });
  return instance.exports;
}

// The smallest module with a SIMD instruction (one function returning i8x16.splat of i32.const 0): it validates
// exactly where wasm SIMD is supported
const SIMD_PROBE = new Uint8Array([
  0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,  // \0asm, version 1
  0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b,        // types: () -> v128
  0x03, 0x02, 0x01, 0x00,                          // functions: one of type 0
  0x0a, 0x08, 0x01, 0x06, 0x00, 0x41, 0x00, 0xfd, 0x0f, 0x0b,  // code: i32.const 0, i8x16.splat, end
]);

export function wasmSimd() {
  try {
    return WebAssembly.validate(SIMD_PROBE);
  } catch {
    return false;
  }
}

// which build to fetch, relative to the app (simd false: the fallback's, as for a browser without SIMD)
export function kernelsFile(simd = wasmSimd()) {
  return simd ? 'wasm/kernels-simd.wasm' : 'wasm/kernels.wasm';
}
