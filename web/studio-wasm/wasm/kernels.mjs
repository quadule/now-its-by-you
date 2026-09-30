// The C kernels (kernels.c -> kernels.wasm), instantiated on Pyodide's own memory: their pointers are numpy
// arrays' data addresses, handed over from Python (py/wasm_kernels.py). Math functions come from JS.
export async function loadWasmKernels(bytes, memory) {
  const env = {
    memory, exp: Math.exp, sin: Math.sin, cos: Math.cos, tanh: Math.tanh, log10: Math.log10, pow: Math.pow,
  };
  const { instance } = await WebAssembly.instantiate(bytes, { env });
  return instance.exports;
}
