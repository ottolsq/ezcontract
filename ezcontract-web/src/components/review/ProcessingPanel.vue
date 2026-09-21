<script setup>
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()
</script>

<template>
  <div class="processing">
    <div class="radar" aria-hidden="true">AI</div>
    <h2>正在进行 AI 审查</h2>
    <p class="file">{{ store.filename }}</p>
    <el-progress
      :percentage="store.progress.percent"
      :stroke-width="10"
      class="bar"
    />
    <p class="stage">{{ store.progress.stage }}</p>
    <el-alert
      v-if="store.status === 'failed'"
      :title="store.error || '审查失败'"
      type="error"
      class="err"
      :closable="false"
    />
  </div>
</template>

<style scoped>
.processing {
  max-width: 520px;
  margin: 60px auto;
  text-align: center;
}

.radar {
  width: 88px;
  height: 88px;
  margin: 0 auto 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #2459a9;
  font-weight: 600;
  position: relative;
  background:
    radial-gradient(circle at center, #eaf2ff 0 43%, transparent 44%),
    conic-gradient(#2459a9, #dbe3ee, #2459a9);
  animation: spin 1.6s linear infinite;
}

.radar::after {
  content: '';
  position: absolute;
  inset: 12px;
  border-radius: 50%;
  background: #fff;
  z-index: -1;
}

.radar {
  z-index: 0;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

h2 {
  margin: 0 0 6px;
}

.file {
  color: #66758a;
  font-size: 13px;
  margin-bottom: 22px;
}

.bar {
  margin-bottom: 10px;
}

.stage {
  color: #66758a;
  font-size: 13px;
  min-height: 20px;
}
</style>
