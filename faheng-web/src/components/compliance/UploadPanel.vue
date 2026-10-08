<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useComplianceStore } from '../../stores/compliance'

const store = useComplianceStore()
const uploading = ref(false)

async function beforeUpload(file) {
  if (uploading.value) return false
  if (!/\.docx$/i.test(file.name)) {
    ElMessage.error('履约模块目前仅支持 .docx 文件')
    return false
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error('文件超过 20MB')
    return false
  }
  uploading.value = true
  try {
    await store.uploadFile(file)
  } catch {
    /* 拦截器已提示 */
  } finally {
    uploading.value = false
  }
  return false // 阻止 el-upload 自动上传
}

async function onSample() {
  if (uploading.value) return
  uploading.value = true
  try {
    await store.loadSample()
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="upload-wrap" v-loading="uploading">
    <h2>上传已签署合同</h2>
    <p class="sub">AI 将自动识别付款日、交付日等履约节点，计算截止日期并在到期前一天提醒</p>
    <el-upload drag :before-upload="beforeUpload" :show-file-list="false" accept=".docx">
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <div class="el-upload__text">拖拽合同到此处，或 <em>点击选择</em></div>
      <template #tip>
        <div class="el-upload__tip">仅支持 DOCX，单份不超过 20MB</div>
      </template>
    </el-upload>
    <el-button class="sample-btn" @click="onSample">载入测试合同</el-button>
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
</style>
