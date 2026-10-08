<script setup>
import { useComplianceStore } from '../../stores/compliance'
import LoadingIndicator from '../LoadingIndicator.vue'

const store = useComplianceStore()
</script>

<template>
  <div class="extracting">
    <!-- 失败状态 -->
    <template v-if="store.status === 'failed'">
      <div class="fail-icon">✕</div>
      <h2>提取失败</h2>
      <p class="sub">{{ store.error || '发生未知错误' }}</p>
      <div class="actions">
        <el-button @click="store.goList()">返回列表</el-button>
        <el-button type="primary" @click="store.retryExtract()">重试提取</el-button>
      </div>
    </template>

    <!-- 加载状态：使用统一指示器 -->
    <LoadingIndicator
      v-else
      type="compliance"
      :percentage="50"
      :stage="store.progressStage"
      title="正在提取履约节点"
      :subtitle="store.contract?.filename"
    />
  </div>
</template>

<style scoped>
.extracting {
  width: 480px;
  margin: 60px auto;
  text-align: center;
}

.fail-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 14px;
  border-radius: 50%;
  background: #fdecea;
  color: #e74c3c;
  font-size: 30px;
  line-height: 64px;
}

h2 {
  margin: 0 0 8px;
  font-size: 20px;
}

.sub {
  color: #66758a;
  margin-bottom: 24px;
}

.actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
