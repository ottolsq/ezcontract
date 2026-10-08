<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useComplianceStore } from '../../stores/compliance'
import api from '../../api'

const store = useComplianceStore()
const uploading = ref(false)
const uploadProgress = ref({ current: 0, total: 0 })
const fileList = ref([])
const MAX_FILES = 3

function beforeUpload(file) {
  if (!/\.docx$/i.test(file.name)) {
    ElMessage.error(`${file.name} 不是 .docx 文件`)
    return false
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error(`${file.name} 超过 20MB`)
    return false
  }
  return true
}

function handleChange(file, files) {
  // 检查文件数量限制
  if (files.length > MAX_FILES) {
    ElMessage.warning(`最多同时上传 ${MAX_FILES} 个合同`)
    // 移除多余的文件
    fileList.value = files.slice(0, MAX_FILES)
  } else {
    fileList.value = files
  }
}

function handleRemove(file, files) {
  fileList.value = files
}

async function submitUpload() {
  if (uploading.value || fileList.value.length === 0) return

  uploading.value = true
  uploadProgress.value = { current: 0, total: fileList.value.length }

  try {
    for (const file of fileList.value) {
      const fd = new FormData()
      fd.append('file', file.raw)
      const { data } = await api.post('/compliance/upload', fd)
      await store.startExtractBackground(data.contract_id)
      uploadProgress.value.current++
    }

    // 刷新合同列表
    await store.fetchContracts()

    if (fileList.value.length > 1) {
      ElMessage.success(`已提交 ${fileList.value.length} 个合同进行提取`)
    } else {
      ElMessage.success('合同已开始提取')
    }

    // 清空文件列表
    fileList.value = []
  } catch (error) {
    console.error('上传失败:', error)
  } finally {
    uploading.value = false
    uploadProgress.value = { current: 0, total: 0 }
  }
}
</script>

<template>
  <div class="upload-wrap">
    <h2>上传已签署合同</h2>
    <p class="sub">AI 将自动识别付款日、交付日等履约节点，计算截止日期并在到期前一天提醒</p>
    <el-upload
      drag
      multiple
      :auto-upload="false"
      :file-list="fileList"
      :on-change="handleChange"
      :on-remove="handleRemove"
      :before-upload="beforeUpload"
      accept=".docx"
      :disabled="uploading"
      list-type="text"
    >
      <el-icon v-if="!uploading" class="upload-icon"><UploadFilled /></el-icon>
      <div v-if="uploading" class="upload-progress">
        <div>正在上传 {{ uploadProgress.current }}/{{ uploadProgress.total }}...</div>
        <el-progress :percentage="(uploadProgress.current / uploadProgress.total) * 100" />
      </div>
      <div v-else class="el-upload__text">拖拽合同到此处，或 <em>点击选择</em></div>
      <template #tip>
        <div class="el-upload__tip">支持同时上传最多 {{ MAX_FILES }} 个 DOCX 文件，单个不超过 20MB</div>
      </template>
    </el-upload>
    <el-button
      v-if="fileList.length > 0 && !uploading"
      type="primary"
      @click="submitUpload"
      style="margin-top: 16px"
    >
      开始提取 ({{ fileList.length }} 个合同)
    </el-button>
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

.upload-progress {
  padding: 20px;
}

.upload-progress > div {
  margin-bottom: 10px;
  color: #66758a;
}
</style>
