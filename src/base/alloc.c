/* The allocator facade: per-subsystem accounting, a leak registry in debug
 * builds, guard bytes, a free-quarantine, and fault injection.
 *
 * Block layout. Every block is one malloc; the caller gets `payload`.
 *
 *   release:  | AllocHeader | payload | 
 *   debug:    | DebugLinks | (pad) | front guard | AllocHeader | payload | rear guard |
 *
 * The header always sits directly in front of the payload, so cdin_free finds
 * the tag and size without being told. In a debug build the front guard sits in
 * front of the header (never inside it: an earlier layout overlapped the two, so
 * every free of a clean block reported an overflow), and DebugLinks threads
 * every live block on a doubly linked list, which makes unregistering a block
 * O(1) instead of a walk of the whole list.
 *
 * Alignment comes from rounding the payload's offset up to alignof(max_align_t)
 * (PAYLOAD_OFFSET), not from the header's size. The one assumption made of the
 * system allocator is that malloc returns max-aligned memory.
 *
 * Detecting bad frees. cdin_free reads the header at `p - sizeof(AllocHeader)`.
 * For a pointer this module returned, that is exact. For a pointer it did not
 * return, the read is outside any object the caller owns, so detection of
 * foreign pointers is best effort and the pointer must at least have readable
 * memory in front of it. Double frees are detected reliably in debug builds
 * only: freed blocks are held in a small quarantine with their magic cleared
 * (and, under AddressSanitizer, their payload poisoned) before they go back
 * to malloc, so the second free reads memory that is still valid. A release
 * build returns the block to malloc at once, and a double free there is the
 * caller's undefined behaviour, as with free().
 *
 * Ownership: this module owns every block it returns. Only cdin_free may
 * release them.
 *
 * Threads: main thread only. Counters, registry, quarantine and the fault
 * injector are plain statics. Phase 3 must decide how workers account for the
 * blocks they free; see alloc.h.
 */

#include "alloc.h"

#include <stdalign.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "../core/logger.h"

#if defined(__SANITIZE_ADDRESS__)
#  define ALLOC_HAVE_ASAN 1
#elif defined(__has_feature)
#  if __has_feature(address_sanitizer)
#    define ALLOC_HAVE_ASAN 1
#  endif
#endif

#ifdef ALLOC_HAVE_ASAN
#  include <sanitizer/asan_interface.h>
#  define ASAN_POISON(p, n)   ASAN_POISON_MEMORY_REGION((p), (n))
#  define ASAN_UNPOISON(p, n) ASAN_UNPOISON_MEMORY_REGION((p), (n))
#else
#  define ASAN_POISON(p, n)   ((void)(p), (void)(n))
#  define ASAN_UNPOISON(p, n) ((void)(p), (void)(n))
#endif

_Static_assert((alignof(max_align_t) & (alignof(max_align_t) - 1)) == 0,
               "ALIGN_UP requires a power-of-two alignment");

/* The registry, guards and quarantine are on in any build without NDEBUG, and
 * on request with CDIN_ALLOC_DEBUG. */
#if defined(CDIN_ALLOC_DEBUG) || (!defined(NDEBUG) && !defined(CDIN_ALLOC_NO_DEBUG))
#  define ALLOC_DEBUG 1
#else
#  define ALLOC_DEBUG 0
#endif

#define ALLOC_MAGIC 0x43444E4Eu   /* "CDIN" */

typedef struct {
  size_t   size;      /* payload bytes, as requested               */
  uint32_t magic;     /* ALLOC_MAGIC while live, 0 once freed      */
  uint16_t tag;       /* CdinMemTag                                */
  uint16_t flags;     /* reserved                                  */
} AllocHeader;

#define ALIGN_UP(v, a)  (((v) + ((size_t)(a) - 1)) & ~((size_t)(a) - 1))

#if ALLOC_DEBUG
#  define FRONT_GUARD_BYTES  16
#  define REAR_GUARD_BYTES   8
#  define GUARD_PATTERN      0xA5
#  define FREED_PATTERN      0xDD
typedef struct DebugLinks {
  struct DebugLinks *prev;
  struct DebugLinks *next;
} DebugLinks;
#  define PRE_HEADER_BYTES (sizeof(DebugLinks) + FRONT_GUARD_BYTES)
#else
#  define REAR_GUARD_BYTES   0
#  define PRE_HEADER_BYTES   0
#endif

#define PAYLOAD_OFFSET \
  ALIGN_UP(PRE_HEADER_BYTES + sizeof(AllocHeader), alignof(max_align_t))
#define BLOCK_OVERHEAD (PAYLOAD_OFFSET + REAR_GUARD_BYTES)

_Static_assert((PAYLOAD_OFFSET % alignof(max_align_t)) == 0,
               "the payload offset must preserve max alignment");
_Static_assert(PAYLOAD_OFFSET >= PRE_HEADER_BYTES + sizeof(AllocHeader),
               "header and guards must fit in front of the payload");

#define BLOCK_OF(p) ((unsigned char *)(p) - PAYLOAD_OFFSET)

typedef struct {
  size_t live;
  size_t peak;
  size_t count;      /* allocations currently live, not allocations made */
} TagCounters;

/* Owned by this module, main thread only. total_peak is its own high-water
 * mark: the per-tag peaks rarely coincide, so their sum was never reached. */
static TagCounters counters[CDIN_MEM_COUNT];
static size_t total_live;
static size_t total_peak;

static size_t bad_frees;
static size_t guard_violations;

#if ALLOC_DEBUG
static DebugLinks *live_head;
static size_t      live_blocks;

#  define QUARANTINE_SLOTS      256
#  define QUARANTINE_MAX_BYTES  ((size_t)4 << 20)
#  define FREED_POISON_BYTES    64

typedef struct {
  unsigned char *raw;
  size_t         size;      /* payload bytes */
} QuarantineSlot;

static QuarantineSlot q_ring[QUARANTINE_SLOTS];
static size_t q_oldest;
static size_t q_count;
static size_t q_bytes;
#endif

static int           fail_armed;
static unsigned long fail_allow;    /* allocations still to be allowed */
static unsigned long fail_refused;  /* refusals since the last arm      */

static const char *const TAG_NAMES[CDIN_MEM_COUNT] = {
  "base", "buffer", "syntax", "font", "gfx",
  "lua_bind", "platform", "loop", "fs", "edit",
};

static int tag_is_valid(CdinMemTag tag) {
  return (int)tag >= 0 && (int)tag < (int)CDIN_MEM_COUNT;
}

const char *cdin_mem_tag_name(CdinMemTag subsystem) {
  return tag_is_valid(subsystem) ? TAG_NAMES[subsystem] : "unknown";
}

static AllocHeader *header_of(void *payload) {
  return (AllocHeader *)((unsigned char *)payload - sizeof(AllocHeader));
}

static void account_add(CdinMemTag tag, size_t size) {
  TagCounters *c = &counters[tag];
  c->live += size;
  c->count++;
  if (c->live > c->peak) c->peak = c->live;

  total_live += size;
  if (total_live > total_peak) total_peak = total_live;
}

/* Clamped rather than allowed to wrap: a wrapped counter makes every later
 * number nonsense, a clamped one is wrong in a way the leak report shows. */
static void account_remove(CdinMemTag tag, size_t size) {
  TagCounters *c = &counters[tag];
  c->live = (c->live >= size) ? c->live - size : 0;
  if (c->count > 0) c->count--;
  total_live = (total_live >= size) ? total_live - size : 0;
}

#if ALLOC_DEBUG

static void registry_link(unsigned char *raw) {
  DebugLinks *l = (DebugLinks *)raw;
  l->prev = NULL;
  l->next = live_head;
  if (live_head) live_head->prev = l;
  live_head = l;
  live_blocks++;
}

static void registry_unlink(unsigned char *raw) {
  DebugLinks *l = (DebugLinks *)raw;
  if (l->prev) l->prev->next = l->next;
  else         live_head = l->next;
  if (l->next) l->next->prev = l->prev;
  l->prev = l->next = NULL;
  live_blocks--;
}

static unsigned char *front_guard_of(void *payload) {
  return (unsigned char *)header_of(payload) - FRONT_GUARD_BYTES;
}

static void guards_write(void *payload, size_t size) {
  memset(front_guard_of(payload), GUARD_PATTERN, FRONT_GUARD_BYTES);
  memset((unsigned char *)payload + size, GUARD_PATTERN, REAR_GUARD_BYTES);
}

static int guards_intact(void *payload, size_t size) {
  const unsigned char *front = front_guard_of(payload);
  const unsigned char *rear  = (const unsigned char *)payload + size;
  for (int i = 0; i < FRONT_GUARD_BYTES; i++) {
    if (front[i] != GUARD_PATTERN) return 0;
  }
  for (int i = 0; i < REAR_GUARD_BYTES; i++) {
    if (rear[i] != GUARD_PATTERN) return 0;
  }
  return 1;
}

static void quarantine_release(QuarantineSlot *s) {
  ASAN_UNPOISON(s->raw + PAYLOAD_OFFSET, s->size);
  free(s->raw);
  s->raw = NULL;
}

static void quarantine_pop_oldest(void) {
  QuarantineSlot *s = &q_ring[q_oldest];
  q_bytes -= s->size;
  quarantine_release(s);
  q_oldest = (q_oldest + 1) % QUARANTINE_SLOTS;
  q_count--;
}

/* Holds a freed block instead of returning it to malloc, so a second free of
 * the same pointer reads a header that is still there (magic 0) rather than
 * memory malloc may already have handed to someone else. Bounded in both
 * slots and bytes; a block larger than the byte cap is released at once. */
static void quarantine_push(unsigned char *raw, size_t size) {
  unsigned char *payload = raw + PAYLOAD_OFFSET;

  if (size > QUARANTINE_MAX_BYTES) {
    free(raw);
    return;
  }
  while (q_count == QUARANTINE_SLOTS || q_bytes + size > QUARANTINE_MAX_BYTES) {
    quarantine_pop_oldest();
  }
  memset(payload, FREED_PATTERN, size < FREED_POISON_BYTES ? size : FREED_POISON_BYTES);
  ASAN_POISON(payload, size);

  QuarantineSlot *s = &q_ring[(q_oldest + q_count) % QUARANTINE_SLOTS];
  s->raw  = raw;
  s->size = size;
  q_count++;
  q_bytes += size;
}

static void quarantine_drain(void) {
  while (q_count > 0) quarantine_pop_oldest();
}

#endif /* ALLOC_DEBUG */

/* Returns 1 when this allocation must be refused: "let n through, refuse every
 * one after". Every entry point that can ask the system for memory calls this,
 * realloc included, or the growth path could not be tested under OOM. */
static int should_refuse(void) {
  if (!fail_armed) return 0;
  if (fail_allow > 0) {
    fail_allow--;
    return 0;
  }
  fail_refused++;
  return 1;
}

void *cdin_alloc(CdinMemTag subsystem, size_t size) {
  if (!tag_is_valid(subsystem)) {
    log_error("alloc: invalid subsystem tag %d for a %zu byte allocation",
              (int)subsystem, size);
    return NULL;
  }
  if (should_refuse()) return NULL;

  if (size > (size_t)-1 - BLOCK_OVERHEAD) {
    log_error("alloc: %zu byte request overflows a size_t once the %zu byte "
              "block overhead is added", size, (size_t)BLOCK_OVERHEAD);
    return NULL;
  }

  unsigned char *raw = (unsigned char *)malloc(size + BLOCK_OVERHEAD);
  if (!raw) {
    log_error("alloc: out of memory for a %zu byte %s allocation",
              size, cdin_mem_tag_name(subsystem));
    return NULL;
  }

  void *payload = raw + PAYLOAD_OFFSET;
  AllocHeader *h = header_of(payload);
  h->size  = size;
  h->magic = ALLOC_MAGIC;
  h->tag   = (uint16_t)subsystem;
  h->flags = 0;

#if ALLOC_DEBUG
  guards_write(payload, size);
  registry_link(raw);
#endif
  account_add(subsystem, size);
  return payload;
}

void *cdin_calloc(CdinMemTag subsystem, size_t count, size_t size) {
  if (count != 0 && size > (size_t)-1 / count) {
    log_error("alloc: calloc(%zu, %zu) overflows a size_t", count, size);
    return NULL;
  }
  size_t total = count * size;

  void *p = cdin_alloc(subsystem, total);
  if (p && total > 0) memset(p, 0, total);
  return p;
}

void *cdin_realloc(CdinMemTag subsystem, void *p, size_t size) {
  if (!p) return cdin_alloc(subsystem, size);

  AllocHeader *h = header_of(p);
  if (h->magic != ALLOC_MAGIC) {
    bad_frees++;
    log_error("alloc: realloc of a pointer this allocator did not hand out "
              "(%p) — refusing rather than corrupting the heap", p);
    return NULL;
  }

  CdinMemTag old_tag = (CdinMemTag)h->tag;
  size_t old_size = h->size;

  /* Every refusal below happens before the block, the registry or the counters
   * are touched, so a refused realloc leaves `p` live, accounted and writable. */
  if (should_refuse()) return NULL;
  if (size > (size_t)-1 - BLOCK_OVERHEAD) {
    log_error("alloc: realloc to %zu bytes overflows a size_t", size);
    return NULL;
  }

#if ALLOC_DEBUG
  if (!guards_intact(p, old_size)) {
    guard_violations++;
    log_error("alloc: realloc of %p — the guard bytes around the %zu byte "
              "payload are clobbered; the block has already overflowed",
              p, old_size);
  }
  registry_unlink(BLOCK_OF(p));
#endif

  unsigned char *resized = (unsigned char *)realloc(BLOCK_OF(p), size + BLOCK_OVERHEAD);
  if (!resized) {
    log_error("alloc: out of memory reallocating %zu -> %zu bytes", old_size, size);
#if ALLOC_DEBUG
    registry_link(BLOCK_OF(p));   /* realloc left the original block alone */
#endif
    return NULL;
  }

  void *np = resized + PAYLOAD_OFFSET;
  AllocHeader *nh = header_of(np);
  nh->size = size;                 /* magic, tag and flags came across with the copy */

  account_remove(old_tag, old_size);
  account_add(old_tag, size);
#if ALLOC_DEBUG
  guards_write(np, size);
  registry_link(resized);
#endif
  return np;
}

void cdin_free(void *p) {
  if (!p) return;

  AllocHeader *h = header_of(p);
  if (h->magic != ALLOC_MAGIC) {
    bad_frees++;
    log_error("alloc: free of %p, which this allocator did not hand out "
              "(already freed, or never ours) — not freeing it", p);
    return;
  }

  CdinMemTag tag = (CdinMemTag)h->tag;
  size_t size = h->size;

#if ALLOC_DEBUG
  if (!guards_intact(p, size)) {
    guard_violations++;
    log_error("alloc: free of %p — guard bytes around the %zu byte payload "
              "are clobbered; the block overflowed before it was released",
              p, size);
  }
  registry_unlink(BLOCK_OF(p));
#endif

  h->magic = 0;
  account_remove(tag, size);

#if ALLOC_DEBUG
  quarantine_push(BLOCK_OF(p), size);
#else
  free(BLOCK_OF(p));
#endif
}

size_t cdin_mem_live(CdinMemTag subsystem) {
  return tag_is_valid(subsystem) ? counters[subsystem].live : 0;
}

size_t cdin_mem_peak(CdinMemTag subsystem) {
  return tag_is_valid(subsystem) ? counters[subsystem].peak : 0;
}

size_t cdin_mem_alloc_count(CdinMemTag subsystem) {
  return tag_is_valid(subsystem) ? counters[subsystem].count : 0;
}

size_t cdin_mem_total_live(void) { return total_live; }
size_t cdin_mem_total_peak(void) { return total_peak; }

CdinMemTag cdin_mem_tag_of(const void *p) {
  if (!p) return CDIN_MEM_COUNT;
  const AllocHeader *h =
      (const AllocHeader *)((const unsigned char *)p - sizeof(AllocHeader));
  if (h->magic != ALLOC_MAGIC) return CDIN_MEM_COUNT;
  CdinMemTag tag = (CdinMemTag)h->tag;
  return tag_is_valid(tag) ? tag : CDIN_MEM_COUNT;
}

size_t cdin_mem_bad_frees(void)        { return bad_frees; }
size_t cdin_mem_guard_violations(void) { return guard_violations; }

int cdin_mem_debug_enabled(void) { return ALLOC_DEBUG; }

/* Arming resets the refusal counter, so cdin_alloc_failures() answers "how many
 * did THIS arm refuse" and tells an injector that fired from one never armed. */
void cdin_alloc_fail_after(unsigned long n) {
  fail_armed   = 1;
  fail_allow   = n;
  fail_refused = 0;
}

void cdin_alloc_fail_disable(void) {
  fail_armed   = 0;
  fail_allow   = 0;
  fail_refused = 0;
}

int cdin_alloc_fail_is_armed(void) { return fail_armed; }

unsigned long cdin_alloc_fail_after_get(void) {
  return fail_armed ? fail_allow : 0;
}

unsigned long cdin_alloc_failures(void) { return fail_refused; }

void cdin_mem_quarantine_drain(void) {
#if ALLOC_DEBUG
  quarantine_drain();
#endif
}

size_t cdin_mem_leak_report(void) {
#if ALLOC_DEBUG
  quarantine_drain();
  if (live_blocks == 0) return 0;

  log_error("alloc: %zu block(s) still live at exit:", live_blocks);
  for (const DebugLinks *l = live_head; l; l = l->next) {
    void *payload = (unsigned char *)l + PAYLOAD_OFFSET;
    const AllocHeader *h = header_of(payload);
    log_error("alloc:   %8zu bytes  %-10s  %p",
              h->size, cdin_mem_tag_name((CdinMemTag)h->tag), payload);
  }
  return live_blocks;
#else
  /* Returning 0 silently would claim "no leaks" about a build that checked
   * nothing. */
  log_info("alloc: leak report unavailable — this build has no live-block "
           "registry (compiled without CDIN_ALLOC_DEBUG)");
  return 0;
#endif
}

size_t cdin_mem_live_blocks(void) {
#if ALLOC_DEBUG
  return live_blocks;
#else
  return 0;
#endif
}
