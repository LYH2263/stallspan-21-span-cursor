<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const vendors = ref<any[]>([])
const err = ref('')

// 主图色块与放不下必须同一次产出：整页只认这一个 data（/allocate/run），
// 禁入块画 data.blocked_spans，放不下读 data.rejected，二者一起变。
async function run() {
  err.value = ''
  try {
    data.value = await api('/allocate/run?segment_id=1', { method: 'POST' })
  } catch (e: any) {
    err.value = String(e?.message || e)
  }
}
onMounted(async () => {
  vendors.value = await api('/vendors')
  await run()
})
const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']

// 柱心位置 -> 名称：禁入块本身只带端点，标注按 ±厚/2 对回本次柱表
const pillarLabel = computed(() => {
  const m = new Map<number, string>()
  for (const p of data.value?.pillars || []) {
    m.set(Math.round(p.position_m * 1000) / 1000, p.label || '挡柱')
  }
  return m
})

// 同一次结果里的禁入并集 + 落位，按起点排序；空档不画，露出沥青底
const cells = computed(() => {
  if (!data.value) return []
  const width = data.value.segment.width_m
  const out: any[] = []
  for (const b of data.value.blocked_spans || []) {
    const center = Math.round(((b.start_m + b.end_m) / 2) * 1000) / 1000
    out.push({
      type: 'pillar',
      start: b.start_m, w: b.end_m - b.start_m,
      label: pillarLabel.value.get(center) || '挡柱',
    })
  }
  for (const [i, p] of (data.value.placements || []).entries()) {
    out.push({ type: 'stall', start: p.start_m, w: p.width_m, label: p.vendor_name, color: colors[i % colors.length] })
  }
  return out.sort((a, b) => a.start - b.start).map(c => ({
    ...c,
    leftPct: (c.start / width) * 100,
    wPct: (c.w / width) * 100,
  }))
})
</script>
<template>
  <div class="ss-street-wrap">
    <h1>街段分配带</h1>
    <p class="sub">柱 → 禁入并集 → 可用开区间 → 按优先序从左填空 · 色块与放不下为同一次产出</p>
    <div><button class="btn" @click="run">重新分配</button>
      <span v-if="err" class="badge badge-bad" style="margin-left:.5rem">{{ err }}</span></div>
    <div class="ss-band-ruler" v-if="data">
      <span>0 m</span>
      <span>{{ data.segment.name }} · {{ data.segment.width_m }} m · 禁入 {{ data.blocked_spans.length }} 段</span>
      <span>{{ data.segment.width_m }} m</span>
    </div>
    <div class="ss-street-band" v-if="data">
      <div class="ss-street-inner" style="display:block">
        <div
          v-for="(c,i) in cells" :key="i"
          class="ss-band-cell"
          :class="{ 'ss-pillar': c.type === 'pillar' }"
          :style="{
            position: 'absolute', top: 0, bottom: 0,
            left: c.leftPct + '%', width: c.wPct + '%',
            background: c.type === 'pillar' ? undefined : c.color,
          }"
        >{{ c.label }}</div>
      </div>
    </div>
    <div class="ss-vendor-queue">
      <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
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
    <div class="card" v-if="data">
      <strong>本次放不下（与上图同一次分配）</strong>
      <table>
        <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
        <tbody>
          <tr v-for="r in data.rejected" :key="r.vendor_id">
            <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!data.rejected.length" class="muted">全部放下</p>
    </div>
  </div>
</template>
