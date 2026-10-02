<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { allocation } from '../allocation'

const rows = computed(() => allocation.result.value?.rejected ?? [])
const runId = allocation.runId

onMounted(() => {
  // Map 与本页共享同一对象；若直接进入本页则按当前柱实时重算。
  if (!allocation.result.value) allocation.refreshLatest()
})
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">
    无法在连续开区间内安置且不跨越挡柱的摊位 · 与主图来自同一次分配
    <span class="muted">{{ runId ? `#${runId}` : '（实时）' }}</span>
  </p>
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
