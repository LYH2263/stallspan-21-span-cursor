<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { allocation } from '../allocation'

const rows = ref<any[]>([])
const position = ref(15)
const thickness = ref(0.5)
const label = ref('新柱')
const error = ref('')
const busy = ref(false)

async function reload() {
  rows.value = await api('/pillars')
}
onMounted(reload)

async function addPillar() {
  error.value = ''
  busy.value = true
  try {
    await allocation.addPillar({
      segment_id: 1,
      position_m: Number(position.value),
      thickness_m: Number(thickness.value),
      label: label.value || '挡柱',
    })
    await reload()
  } catch (e: any) {
    error.value = e?.message || '插柱失败'
  } finally {
    busy.value = false
  }
}

async function removePillar(id: number) {
  error.value = ''
  busy.value = true
  try {
    await allocation.removePillar(id)
    await reload()
  } catch (e: any) {
    error.value = e?.message || '移除失败'
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <h1>挡柱</h1>
  <p class="sub">插柱后按新柱瞬时重算：主图色块与放不下页来自同一次禁入代数，一起改变</p>
  <div class="card">
    <form class="ss-pillar-form" @submit.prevent="addPillar">
      <label>位置(m)<input v-model.number="position" type="number" step="0.1" min="0" required /></label>
      <label>厚度(m)<input v-model.number="thickness" type="number" step="0.1" min="0.1" required /></label>
      <label>名称<input v-model="label" type="text" maxlength="32" /></label>
      <button class="btn" type="submit" :disabled="busy">在 {{ position }}m 插柱</button>
    </form>
    <p v-if="error" class="badge badge-bad ss-form-error">{{ error }}</p>
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
      <thead><tr><th>名称</th><th>位置(m)</th><th>厚度(m)</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.label }}</td><td>{{ r.position_m }}</td><td>{{ r.thickness_m }}</td>
          <td><button class="btn ss-btn-mini" :disabled="busy" @click="removePillar(r.id)">移除</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
