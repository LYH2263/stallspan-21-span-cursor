<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const loading = ref(false)
async function load() {
  loading.value = true
  try {
    // latest 自带输入指纹：柱变了会按新柱瞬时重算，这里拿到的放不下与主图同源
    const data = await api('/allocate/latest?segment_id=1')
    rows.value = data.rejected || []
  } finally { loading.value = false }
}
onMounted(load)
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">无法在连续空档内安置且不跨越挡柱的摊位 · 与分配带为同一次禁入代数产出</p>
  <button class="btn" style="margin-bottom:.6rem" :disabled="loading" @click="load">刷新（插柱后自动重算）</button>
  <div class="card">
    <table>
      <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!rows.length" class="muted">全部放下</p>
  </div>
</template>
