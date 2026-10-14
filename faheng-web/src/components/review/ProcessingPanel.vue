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
      show-cancel
      @cancel="store.cancel()"
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
  max-width: calc(100% - 32px);
  margin: 60px auto;
  text-align: center;
  padding: 0 16px;
}

.err {
  margin-top: 20px;
}

@media (max-width: 768px) {
  .processing {
    margin: 40px auto;
  }
}

@media (max-width: 480px) {
  .processing {
    margin: 24px auto;
  }
}
</style>
