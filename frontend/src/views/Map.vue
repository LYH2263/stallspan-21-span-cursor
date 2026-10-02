<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { allocation, type PillarDTO, type Placement, type Span } from '../allocation'

const vendors = ref<any[]>([])
const data = allocation.result
const loading = allocation.loading
const runId = allocation.runId
const rejectedVendorIds = allocation.rejectedVendorIds
const NARROW_PCT = 3

onMounted(async () => {
  vendors.value = await api('/vendors')
  await allocation.refreshLatest()
})

const colors = ['#e8a87c', '#85dcb8', '#e27d60', '#c38d9e', '#41b3a3', '#f4a261', '#e76f51']
const colorOf = (vendorId: number) => colors[(vendorId - 1) % colors.length]

interface AbsCell {
  key: string
  label: string
  leftPct: number
  widthPct: number
  narrow: boolean
  title: string
}

function placeCells(list: Span[] | PillarDTO[] | Placement[], width: number, kind: string): AbsCell[] {
  return list.map((item: any) => {
    const start = kind === 'pillar' ? item.position_m - item.thickness_m / 2 : item.start_m
    const w =
      kind === 'pillar' ? item.thickness_m : item.width_m ?? item.end_m - item.start_m
    const label = kind === 'pillar' ? item.label : kind === 'stall' ? item.vendor_name : '空档'
    const widthPct = (w / width) * 100
    return {
      key: `${kind}-${item.id ?? item.vendor_id ?? `${start}-${w}`}`,
      label,
      leftPct: (start / width) * 100,
      widthPct,
      narrow: widthPct < NARROW_PCT,
      title: `${label} · ${start.toFixed(2)}–${(start + w).toFixed(2)} m`,
    }
  })
}

const freeCells = computed<AbsCell[]>(() =>
  data.value ? placeCells(data.value.free_spans, data.value.segment.width_m, 'free') : [],
)
const pillarCells = computed<AbsCell[]>(() =>
  data.value ? placeCells(data.value.pillars, data.value.segment.width_m, 'pillar') : [],
)
const stallCells = computed<(AbsCell & { color: string; vendorId: number })[]>(() => {
  if (!data.value) return []
  return placeCells(data.value.placements, data.value.segment.width_m, 'stall').map((c, i) => ({
    ...c,
    vendorId: data.value!.placements[i].vendor_id,
    color: colorOf(data.value!.placements[i].vendor_id),
  }))
})
</script>
<template>
  <div class="ss-street-wrap">
    <h1>街段分配带</h1>
    <p class="sub">柱列表 → 禁入并集 → 可用开区间 → 按优先序从左填空 · 色块与放不下页同一次分配</p>
    <div class="ss-actions">
      <button class="btn" :disabled="loading" @click="allocation.runAllocate()">
        重新分配
      </button>
      <span class="muted">
        {{ runId ? `同一次分配 #${runId}` : '实时结果（未存历史）' }}
      </span>
    </div>
    <div class="ss-band-ruler" v-if="data">
      <span>0 m</span>
      <span>{{ data.segment.name }} · {{ data.segment.width_m }} m</span>
      <span>{{ data.segment.width_m }} m</span>
    </div>
    <div class="ss-street-band" v-if="data">
      <div class="ss-street-track">
        <!-- 最终未占用的开区间：真实米数比例的空挡底纹 -->
        <div
          v-for="c in freeCells"
          :key="c.key"
          class="ss-abs ss-free"
          :class="{ 'ss-narrow': c.narrow }"
          :style="{ left: c.leftPct + '%', width: c.widthPct + '%' }"
          :title="c.title"
        >{{ c.narrow ? '' : c.label }}</div>
        <!-- 灯柱 -->
        <div
          v-for="c in pillarCells"
          :key="c.key"
          class="ss-abs ss-pillar"
          :class="{ 'ss-narrow': c.narrow }"
          :style="{ left: c.leftPct + '%', width: c.widthPct + '%' }"
          :title="c.title"
        >{{ c.label }}</div>
        <!-- 摊位：绝对米数定位，颜色按摊主稳定取色 -->
        <div
          v-for="c in stallCells"
          :key="c.key"
          class="ss-abs ss-stall"
          :class="{ 'ss-narrow': c.narrow }"
          :style="{ left: c.leftPct + '%', width: c.widthPct + '%', background: c.color }"
          :title="c.title"
        >{{ c.label }}</div>
      </div>
    </div>
    <div class="ss-vendor-queue">
      <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
        <span v-if="rejectedVendorIds.has(v.id)" class="badge badge-bad">放不下</span>
      </div>
    </div>
    <div class="card" v-if="data">
      <table>
        <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
        <tbody>
          <tr v-for="p in data.placements" :key="p.vendor_id">
            <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
