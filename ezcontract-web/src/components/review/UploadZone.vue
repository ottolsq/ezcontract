<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()
const uploading = ref(false)

async function beforeUpload(file) {
  const ok = /\.(docx|pdf)$/i.test(file.name)
  if (!ok) {
    ElMessage.error('仅支持 .docx / .pdf 文件')
    return false
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error('文件超过 20MB')
    return false
  }
  uploading.value = true
  try {
    await store.uploadFile(file)
    ElMessage.success(`已识别 ${store.clauses.length} 条条款`)
  } catch {
    /* 拦截器已提示 */
  } finally {
    uploading.value = false
  }
  return false // 阻止 el-upload 自动上传
}

async function onSample() {
  uploading.value = true
  try {
    await store.loadSample()
    ElMessage.success(`已载入测试合同，识别 ${store.clauses.length} 条条款`)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <!-- 未上传视图 -->
  <div v-if="store.phase === 'upload'" class="upload-wrap" v-loading="uploading">
    <h2>上传待审查合同</h2>
    <p class="sub">AI 将按企业规则库逐条审查，识别风险并给出可替换条款</p>
    <el-upload drag :before-upload="beforeUpload" :show-file-list="false" accept=".docx,.pdf">
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <div class="el-upload__text">拖拽合同到此处，或 <em>点击选择</em></div>
      <template #tip>
        <div class="el-upload__tip">支持 DOCX / PDF，单份不超过 20MB</div>
      </template>
    </el-upload>
    <el-button class="sample-btn" @click="onSample">载入测试合同（乙方埋坑版）</el-button>
  </div>

  <!-- 已上传待开始视图 -->
  <div v-else class="upload-wrap">
    <div class="ok-icon">✓</div>
    <h2>文件已就绪</h2>
    <p class="sub">{{ store.filename }} · 已切分 {{ store.clauses.length }} 条条款</p>
    <div class="actions">
      <el-button @click="store.reset()">重新选择</el-button>
      <el-button type="primary" @click="store.startReview()">开始 AI 审查</el-button>
    </div>
  </div>
</template>

<style scoped>
.upload-wrap {
  max-width: 620px;
  margin: 40px auto;
  text-align: center;
}

h2 {
  margin: 0 0 8px;
}

.sub {
  color: #66758a;
  margin-bottom: 24px;
}

.upload-icon {
  font-size: 48px;
  color: #2459a9;
}

.sample-btn {
  margin-top: 16px;
}

.ok-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 14px;
  border-radius: 50%;
  background: #e6f7f0;
  color: #087a55;
  font-size: 30px;
  line-height: 64px;
}

.actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
