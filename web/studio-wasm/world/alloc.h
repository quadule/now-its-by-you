// The memory allocator WORLD's new[] and delete[] use in world.wasm (glue.cpp). zig's libc for wasm allocates with
// std.heap.WasmAllocator, which never splits a freed block for a smaller request nor joins neighbours: Harvest
// frees a few 12 MB buffers and then makes tens of thousands of 1 kB rows, so with it the memory grew to 2.5 times
// what WORLD held at once (485 MB for 206 MB, on 35 s of singing). This one is the usual kind: boundary tags,
// neighbours joined when freed, free blocks kept in lists by size (exact below 1 kB, eight to each power of two
// above) and the first that fits taken and split; the memory grows only when no free block fits.
//
// Blocks: an 8-byte header (the size of the block before, valid while that one is free; this block's size and two
// flags) and the payload, 16-byte aligned. A segment of the memory ends in an 8-byte sentinel that is always in use.
#pragma once

#include <stdint.h>

namespace walloc {

typedef uint32_t u32;
const u32 kInUse = 1, kPrevInUse = 2, kMinBlock = 32, kPage = 65536, kClasses = 256;

struct Block {
  u32 prev_size;  // the block before's size, while it is free
  u32 head;       // this block's size (a multiple of 16) | kInUse | kPrevInUse
  Block *next;    // the free list, while this block is free
  Block *prev;
};

Block *lists[kClasses];
u32 bitmap[kClasses / 32];
char *heap_end = nullptr;  // the end of the last segment

inline u32 size_of(const Block *b) { return b->head & ~15u; }
inline Block *at(void *p, u32 offset) { return reinterpret_cast<Block *>(static_cast<char *>(p) + offset); }
inline Block *after(Block *b) { return at(b, size_of(b)); }

inline u32 class_of(u32 size) {
  if (size < 1024) return size >> 4;
  u32 top = 31 - __builtin_clz(size);
  return 64 + (top - 10) * 8 + ((size >> (top - 3)) & 7);
}

inline void insert(Block *b) {
  u32 c = class_of(size_of(b));
  b->prev = nullptr;
  b->next = lists[c];
  if (lists[c]) lists[c]->prev = b;
  lists[c] = b;
  bitmap[c >> 5] |= 1u << (c & 31);
}

inline void unlink(Block *b) {
  u32 c = class_of(size_of(b));
  if (b->prev) b->prev->next = b->next; else lists[c] = b->next;
  if (b->next) b->next->prev = b->prev;
  if (!lists[c]) bitmap[c >> 5] &= ~(1u << (c & 31));
}

// b (not in use, not listed) as one free block with whichever neighbours are free, listed
inline void release(Block *b) {
  u32 size = size_of(b);
  Block *n = at(b, size);
  if (!(n->head & kInUse)) {
    unlink(n);
    size += size_of(n);
  }
  if (!(b->head & kPrevInUse)) {
    Block *p = reinterpret_cast<Block *>(reinterpret_cast<char *>(b) - b->prev_size);
    unlink(p);
    size += size_of(p);
    b = p;
  }
  b->head = size | (b->head & kPrevInUse);
  Block *n2 = at(b, size);
  n2->prev_size = size;
  n2->head &= ~kPrevInUse;
  insert(b);
}

inline int first_listed(u32 from) {
  for (u32 w = from >> 5; w < kClasses / 32; ++w) {
    u32 bits = bitmap[w] & (w == (from >> 5) ? ~0u << (from & 31) : ~0u);
    if (bits) return static_cast<int>(w * 32 + __builtin_ctz(bits));
  }
  return -1;
}

// more memory, at least need bytes of block, made one free block (joined to the last if they touch)
inline bool grow(u32 need) {
  u32 pages = (need + 16 + kPage - 1) / kPage;
  size_t old = __builtin_wasm_memory_grow(0, pages);
  if (old == static_cast<size_t>(-1)) return false;
  char *start = reinterpret_cast<char *>(old * kPage), *end = start + static_cast<size_t>(pages) * kPage;
  Block *b;
  if (start == heap_end) {  // the old sentinel becomes the new block's header
    b = reinterpret_cast<Block *>(heap_end - 8);
    b->head = static_cast<u32>(end - heap_end) | (b->head & kPrevInUse) | kInUse;
  } else {  // a segment of its own (8 bytes lost before its first block, for the alignment)
    b = reinterpret_cast<Block *>(start + 8);
    b->head = static_cast<u32>(end - start - 16) | kPrevInUse | kInUse;
  }
  Block *sentinel = reinterpret_cast<Block *>(end - 8);
  sentinel->prev_size = 0;
  sentinel->head = kInUse | kPrevInUse;
  heap_end = end;
  b->head &= ~kInUse;
  release(b);
  return true;
}

inline void *allocate(size_t n) {
  if (n > 0x7ff00000u) return nullptr;
  u32 size = (static_cast<u32>(n) + 8 + 15) & ~15u;
  if (size < kMinBlock) size = kMinBlock;
  for (int attempt = 0; attempt < 2; ++attempt) {
    u32 c = class_of(size);
    Block *b = nullptr;
    if (c < 64) {
      b = lists[c];  // a list of blocks of exactly this size
    } else {
      for (Block *q = lists[c]; q; q = q->next)
        if (size_of(q) >= size) { b = q; break; }
    }
    if (!b) {
      int k = first_listed(c + 1);  // every block in a later list is bigger
      if (k >= 0) b = lists[k];
    }
    if (b) {
      unlink(b);
      u32 whole = size_of(b);
      if (whole - size >= kMinBlock) {
        b->head = size | (b->head & kPrevInUse) | kInUse;
        Block *rest = at(b, size);
        rest->head = (whole - size) | kPrevInUse;
        Block *n2 = at(rest, whole - size);
        n2->prev_size = whole - size;
        n2->head &= ~kPrevInUse;
        insert(rest);
      } else {
        b->head |= kInUse;
        after(b)->head |= kPrevInUse;
      }
      return reinterpret_cast<char *>(b) + 8;
    }
    if (!grow(size)) return nullptr;
  }
  return nullptr;
}

inline void deallocate(void *p) {
  if (!p) return;
  Block *b = reinterpret_cast<Block *>(static_cast<char *>(p) - 8);
  b->head &= ~kInUse;
  release(b);
}

inline size_t usable(void *p) { return size_of(reinterpret_cast<Block *>(static_cast<char *>(p) - 8)) - 8; }

}  // namespace walloc
