<script setup>
import { useReviewStore } from '../../stores/review'
import LoadingIndicator from '../LoadingIndicator.vue'

const store = useReviewStore()
</script>

<template>
  <div class="processing">
    <!-- 使用统一指示器 -->
    <LoadingIndicator
      type="review"
      :percentage="store.progress.percent"
      :stage="store.progress.stage"
      title="正在进行 AI 审查"
      :subtitle="store.filename"
    />

    <!-- 失败提示 -->
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
  width: 480px;
  margin: 60px auto;
  text-align: center;
}

.err {
  margin-top: 20px;
}
</style>
