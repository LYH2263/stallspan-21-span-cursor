import { computed, shallowRef } from 'vue'
import { api } from './api'

export interface Placement {
  vendor_id: number
  vendor_name: string
  start_m: number
  end_m: number
  width_m: number
}
export interface Rejected {
  vendor_id: number
  vendor_name: string
  width_m: number
  reason: string
}
export interface PillarDTO {
  id: number
  segment_id: number
  position_m: number
  thickness_m: number
  label: string
}
export interface Span {
  start_m: number
  end_m: number
}
export interface SegmentDTO {
  id: number
  name: string
  width_m: number
}
export interface AllocResult {
  id: number | null
  live?: boolean
  placements: Placement[]
  rejected: Rejected[]
  free_spans: Span[]
  forbidden: Span[]
  open_intervals: Span[]
  segment: SegmentDTO
  pillars: PillarDTO[]
}
export interface PillarInput {
  segment_id: number
  position_m: number
  thickness_m: number
  label?: string
}

// Single source of truth shared by the map and the rejected page: both render
// THIS object (and its run id), so blocks and the rejected list can never come
// from different allocations.
const result = shallowRef<AllocResult | null>(null)
const loading = shallowRef(false)

async function withLoading<T>(fn: () => Promise<T>): Promise<T> {
  loading.value = true
  try {
    return await fn()
  } finally {
    loading.value = false
  }
}

export const allocation = {
  result: computed(() => result.value),
  loading: computed(() => loading.value),
  runId: computed(() => result.value?.id ?? null),
  rejectedVendorIds: computed(
    () => new Set((result.value?.rejected ?? []).map((r) => r.vendor_id)),
  ),

  // Live recompute from current pillars — never a stale snapshot.
  refreshLatest(segmentId = 1) {
    return withLoading(async () => {
      result.value = await api<AllocResult>(
        `/allocate/latest?segment_id=${segmentId}`,
      )
      return result.value
    })
  },

  // Explicit historical run ("重新分配").
  runAllocate(segmentId = 1) {
    return withLoading(async () => {
      result.value = await api<AllocResult>(
        `/allocate/run?segment_id=${segmentId}`,
        { method: 'POST' },
      )
      return result.value
    })
  },

  // The pillar write and the recompute happen server-side in one transaction;
  // its `allocation` replaces the shared object in this tick, so the map
  // blocks and the rejected list change together.
  addPillar(body: PillarInput) {
    return withLoading(async () => {
      const r = await api<{ pillar: PillarDTO; allocation: AllocResult }>(
        '/pillars',
        { method: 'POST', body: JSON.stringify(body) },
      )
      result.value = r.allocation
      return r.pillar
    })
  },

  removePillar(pillarId: number) {
    return withLoading(async () => {
      const r = await api<{ deleted_id: number; allocation: AllocResult }>(
        `/pillars/${pillarId}`,
        { method: 'DELETE' },
      )
      result.value = r.allocation
      return r.deleted_id
    })
  },
}
