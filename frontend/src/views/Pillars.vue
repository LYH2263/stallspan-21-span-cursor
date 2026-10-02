<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const position = ref(15)
const thickness = ref(0.4)
const label = ref('加灯柱')
const msg = ref('')
const busy = ref(false)

async function refresh() { rows.value = await api('/pillars') }
onMounted(refresh)

async function addPillar() {
  busy.value = true; msg.value = ''
  try {
    await api('/pillars', {
      method: 'POST',
      body: JSON.stringify({ segment_id: 1, position_m: Number(position.value),
                             thickness_m: Number(thickness.value), label: label.value || '新挡柱' }),
    })
    // 改柱即落库：/allocate/latest 与主图“重新分配”都会按新柱瞬时重算，不吃旧禁入缓存
    await refresh()
    msg.value = '已插柱，下次分配/latest 按新柱重算'
  } catch (e: any) {
    msg.value = '插柱失败：' + String(e?.message || e)
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <h1>挡柱</h1>
  <p class="sub">街段障碍 · 在分配带上表现为竖直阻断块 · 插柱会拆开可用开区间</p>
  <div class="card">
    <div style="display:flex;gap:.6rem;flex-wrap:wrap;align-items:flex-end">
      <label>位置(m)
        <input v-model.number="position" type="number" min="0" max="30" step="0.1" style="width:7rem">
      </label>
      <label>厚度(m)
        <input v-model.number="thickness" type="number" min="0.05" step="0.05" style="width:6rem">
      </label>
      <label>名称
        <input v-model="label" type="text" style="width:8rem">
      </label>
      <button class="btn" :disabled="busy" @click="addPillar">插柱并触发重分</button>
    </div>
    <p v-if="msg" class="muted" style="margin-bottom:0">{{ msg }}</p>
  </div>
  <div class="ss-street-band" style="height:90px;min-height:90px">
    <div class="ss-street-inner" style="gap:1rem;padding:0 1rem;align-items:center">
      <div
        v-for="r in rows" :key="r.id ?? JSON.stringify(r)"
        class="ss-band-cell ss-pillar"
        :style="{ width: Math.max(r.thickness_m * 28, 36) + 'px', flex: '0 0 auto', height: '70%' }"
      >{{ r.label }} @{{ r.position_m }}m</div>
    </div>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>名称</th><th>位置(m)</th><th>厚度(m)</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)"><td>{{ r.label }}</td><td>{{ r.position_m }}</td><td>{{ r.thickness_m }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
