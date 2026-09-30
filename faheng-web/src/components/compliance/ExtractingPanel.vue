<script setup>
import { useComplianceStore } from '../../stores/compliance'

const store = useComplianceStore()
</script>

<template>
  <div class="extracting" v-loading="true" element-loading-background="transparent">
    <template v-if="store.status === 'failed'">
      <div class="fail-icon">✕</div>
      <h2>提取失败</h2>
      <p class="sub">{{ store.error || '发生未知错误' }}</p>
      <div class="actions">
        <el-button @click="store.goList()">返回列表</el-button>
        <el-button type="primary" @click="store.retryExtract()">重试提取</el-button>
      </div>
    </template>
    <template v-else>
      <el-progress type="circle" :percentage="50" status="warning" :show-text="false" />
      <h2>正在提取履约节点</h2>
      <p class="sub">{{ store.progressStage || 'AI 正在识别合同中的时间节点…' }}</p>
    </template>
  </div>
</template>

<style scoped>
.extracting {
  max-width: 480px;
  margin: 60px auto;
  text-align: center;
  padding: 20px 0;
}

h2 {
  margin: 18px 0 8px;
  font-size: 20px;
}

.sub {
  color: #66758a;
  margin-bottom: 24px;
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

.actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
