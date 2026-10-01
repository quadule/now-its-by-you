// WORLD's Harvest and CheapTrick for the browser (web/studio-wasm/world/world.wasm; docs/WEB-SINGING.md, "On the
// device"). WORLD's sources in src/ are pyworld 0.3.5's own, unmodified; this file only gives them a C interface
// the page's Python can call through the instance's exports (py/world_wasm.py), with an allocator of its own
// (alloc.h) and zig's libc for the maths.
//
// CheapTrick is run a range of frames at a time (so the spectrogram is never whole in this module's memory) and
// gives the same numbers as one call over every frame: each frame is computed from the signal, its f0 and its
// time alone, except for the infinitesimal noise CheapTrick adds from one seeded generator whose state runs on
// from frame to frame; that state is kept here between calls, from world_cheaptrick_begin to _end.

#include "alloc.h"
#include "src/cheaptrick.cpp"  // its own anonymous namespace (CheapTrickGeneralBody) is then reachable here
#include "world/harvest.h"

// C++'s allocation operators (no C++ runtime is linked; WORLD uses new[] and delete[] only), counting what WORLD
// holds at once (world_peak_bytes)
namespace {
size_t live_bytes = 0, peak_bytes = 0;

void *counted(size_t n) {
  void *p = walloc::allocate(n ? n : 1);
  if (!p) __builtin_trap();  // out of memory: the call fails in JS, which py/world_wasm.py says
  live_bytes += walloc::usable(p);
  if (live_bytes > peak_bytes) peak_bytes = live_bytes;
  return p;
}

void uncounted(void *p) {
  if (!p) return;
  live_bytes -= walloc::usable(p);
  walloc::deallocate(p);
}
}  // namespace

void *operator new(size_t n) { return counted(n); }
void *operator new[](size_t n) { return counted(n); }
void operator delete(void *p) noexcept { uncounted(p); }
void operator delete[](void *p) noexcept { uncounted(p); }
void operator delete(void *p, size_t) noexcept { uncounted(p); }
void operator delete[](void *p, size_t) noexcept { uncounted(p); }

namespace {

struct CheapTrickRun {
  int fft_size;
  double f0_floor;
  double q1;
  double *spectral_envelope;
  ForwardRealFFT forward_real_fft;
  InverseRealFFT inverse_real_fft;
  RandnState randn_state;
};

CheapTrickRun run = {};
bool running = false;

}  // namespace

#define EXPORT(name) __attribute__((export_name(#name)))

extern "C" {

// buffers for the arguments (0 if there is no memory for them)
EXPORT(world_alloc) void *world_alloc(int bytes) { return walloc::allocate(bytes > 0 ? bytes : 1); }
EXPORT(world_free) void world_free(void *p) { walloc::deallocate(p); }

// the most WORLD itself has held at once since the last reset (its arrays, not the memory's size)
EXPORT(world_peak_bytes) double world_peak_bytes() { return static_cast<double>(peak_bytes); }
EXPORT(world_reset_peak) void world_reset_peak() { peak_bytes = live_bytes; }

// pyworld.harvest: how many frames, then the f0 contour and each frame's time
EXPORT(world_harvest_length) int world_harvest_length(int fs, int x_length, double frame_period) {
  return GetSamplesForHarvest(fs, x_length, frame_period);
}

EXPORT(world_harvest) void world_harvest(const double *x, int x_length, int fs, double f0_floor, double f0_ceil,
                                         double frame_period, double *temporal_positions, double *f0) {
  HarvestOption option;
  InitializeHarvestOption(&option);
  option.f0_floor = f0_floor;
  option.f0_ceil = f0_ceil;
  option.frame_period = frame_period;
  Harvest(x, x_length, fs, &option, temporal_positions, f0);
}

// pyworld.cheaptrick: its FFT size for a floor, as pyworld chooses it when none is given
EXPORT(world_cheaptrick_fft_size) int world_cheaptrick_fft_size(int fs, double f0_floor) {
  CheapTrickOption option;
  InitializeCheapTrickOption(fs, &option);
  option.f0_floor = f0_floor;
  return GetFFTSizeForCheapTrick(fs, &option);
}

// CheapTrick() itself, cut in three: what it sets up before its loop over frames, the loop over frames
// [0, f0_length) of the arrays given (any range of the whole contour, in order), and what it frees after
EXPORT(world_cheaptrick_begin) int world_cheaptrick_begin(int fs, int fft_size, double q1) {
  if (running) return 0;
  run.fft_size = fft_size;
  run.q1 = q1;
  run.randn_state = RandnState();
  randn_reseed(&run.randn_state);
  run.f0_floor = GetF0FloorForCheapTrick(fs, fft_size);
  run.spectral_envelope = new double[fft_size];
  run.forward_real_fft = ForwardRealFFT();
  InitializeForwardRealFFT(fft_size, &run.forward_real_fft);
  run.inverse_real_fft = InverseRealFFT();
  InitializeInverseRealFFT(fft_size, &run.inverse_real_fft);
  running = true;
  return 1;
}

EXPORT(world_cheaptrick_frames) void world_cheaptrick_frames(const double *x, int x_length, int fs,
                                                             const double *temporal_positions, const double *f0,
                                                             int f0_length, double *spectrogram) {
  int bins = run.fft_size / 2 + 1;
  double current_f0;
  for (int i = 0; i < f0_length; ++i) {
    current_f0 = f0[i] <= run.f0_floor ? world::kDefaultF0 : f0[i];
    CheapTrickGeneralBody(x, x_length, fs, current_f0, run.fft_size, temporal_positions[i], run.q1,
                          &run.forward_real_fft, &run.inverse_real_fft, run.spectral_envelope, &run.randn_state);
    for (int j = 0; j < bins; ++j) spectrogram[i * bins + j] = run.spectral_envelope[j];
  }
}

EXPORT(world_cheaptrick_end) void world_cheaptrick_end() {
  if (!running) return;
  DestroyForwardRealFFT(&run.forward_real_fft);
  DestroyInverseRealFFT(&run.inverse_real_fft);
  delete[] run.spectral_envelope;
  running = false;
}

// The allocator tried on its own (tests/test_world_wasm.cjs): blocks of every size from 1 byte to 24 MB made and
// freed in a random order, each filled with its own pattern and checked when freed; 0 if every one held
// (else the round that failed), and the memory's size against the most held at once in *grown_held.
EXPORT(world_alloc_selftest) int world_alloc_selftest(uint32_t seed, int rounds, double *grown_held) {
  const int kSlots = 512;
  unsigned char *slot[kSlots] = {};
  uint32_t len[kSlots] = {}, salt[kSlots] = {};
  uint32_t s = seed ? seed : 1;
  double held = 0, most = 0;
  size_t before = __builtin_wasm_memory_size(0);
  for (int r = 1; r <= rounds; ++r) {
    s ^= s << 13; s ^= s >> 17; s ^= s << 5;
    int k = static_cast<int>(s % kSlots);
    if (slot[k]) {
      for (uint32_t i = 0; i < len[k]; ++i)
        if (slot[k][i] != static_cast<unsigned char>(salt[k] + i * 31)) return r;
      walloc::deallocate(slot[k]);
      held -= len[k];
      slot[k] = nullptr;
      continue;
    }
    s ^= s << 13; s ^= s >> 17; s ^= s << 5;
    uint32_t kind = s % 100;
    uint32_t n = kind < 70 ? 1 + s % 1100 : kind < 95 ? 1 + s % 300000 : 1 + s % 24000000;
    slot[k] = static_cast<unsigned char *>(walloc::allocate(n));
    if (!slot[k] || (reinterpret_cast<uintptr_t>(slot[k]) & 15)) return r;
    len[k] = n;
    salt[k] = s;
    for (uint32_t i = 0; i < n; ++i) slot[k][i] = static_cast<unsigned char>(salt[k] + i * 31);
    held += n;
    if (held > most) most = held;
  }
  for (int k = 0; k < kSlots; ++k) {
    if (!slot[k]) continue;
    for (uint32_t i = 0; i < len[k]; ++i)
      if (slot[k][i] != static_cast<unsigned char>(salt[k] + i * 31)) return rounds + 1;
    walloc::deallocate(slot[k]);
  }
  grown_held[0] = static_cast<double>(__builtin_wasm_memory_size(0) - before) * walloc::kPage;
  grown_held[1] = most;
  return 0;
}

}  // extern "C"
