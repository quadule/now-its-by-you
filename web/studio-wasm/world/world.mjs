// WORLD's Harvest and CheapTrick (world.wasm, built from glue.cpp and pyworld 0.3.5's sources by build.sh), for
// py/world_wasm.py, the browser's pyworld. The module is compiled once; every analysis gets an instance of its
// own, with its own memory, which is dropped (and its memory with it) when the analysis is done.
//
//   py.registerJsModule('songbird_world', await loadWorld(bytes))
export async function loadWorld(bytes) {
  const module = await WebAssembly.compile(bytes);
  return {
    instance() {
      const { exports } = new WebAssembly.Instance(module, {});
      exports._initialize();
      return exports;
    },
  };
}
