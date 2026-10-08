<script setup>
/**
 * 起草模块加载面板
 */
import { useDraftStore } from '../../stores/draft'
import LoadingIndicator from '../LoadingIndicator.vue'

const store = useDraftStore()
</script>

<template>
  <div class="draft-loading">
    <LoadingIndicator
      type="draft"
      :percentage="store.loading ? 30 : 0"
      :stage="store.revising ? '正在根据要求修订合同...' : '正在生成合同模板...'"
      :title="store.revising ? '正在修订合同' : '正在生成合同模板'"
    />
  </div>
</template>

<style scoped>
.draft-loading {
  width: 480px;
  margin: 60px auto;
  text-align: center;
}
</style>
