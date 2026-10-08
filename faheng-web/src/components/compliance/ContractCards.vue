<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useComplianceStore } from '../../stores/compliance'
import api from '../../api'

const store = useComplianceStore()
const uploadVisible = ref(false)
const uploading = ref(false)
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
  if (files.length > MAX_FILES) {
    ElMessage.warning(`最多同时上传 ${MAX_FILES} 个合同`)
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
  try {
    for (const file of fileList.value) {
      const fd = new FormData()
      fd.append('file', file.raw)
      const { data } = await api.post('/compliance/upload', fd)
      await store.startExtractBackground(data.contract_id)
    }

    await store.fetchContracts()

    if (fileList.value.length > 1) {
      ElMessage.success(`已提交 ${fileList.value.length} 个合同进行提取`)
    } else {
      ElMessage.success('合同已开始提取')
    }

    fileList.value = []
    uploadVisible.value = false
  } catch (error) {
    console.error('上传失败:', error)
  } finally {
    uploading.value = false
  }
}

function statusText(c) {
  return { pending: '待提取', processing: '提取中', completed: '已完成', failed: '失败' }[c.status] || c.status
}

function statusType(c) {
  return { completed: 'success', failed: 'danger', processing: 'warning' }[c.status] || 'info'
}

async function onDelete(c) {
  try {
    await ElMessageBox.confirm(`删除合同《${c.filename}》及其全部履约节点与提醒？`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await store.deleteContract(c.id)
}
</script>

<template>
  <div class="cards">
    <div v-for="c in store.contracts" :key="c.id" class="card" @click="store.fetchDetail(c.id)">
      <div class="card-head">
        <span class="name" :title="c.filename">{{ c.filename }}</span>
        <el-tag :type="statusType(c)" size="small">{{ statusText(c) }}</el-tag>
      </div>
      <div class="card-body">
        <div v-if="c.start_date" class="period">
          {{ c.start_date }} ~ {{ c.end_date || '长期' }}
        </div>
        <div v-else class="period muted">未识别到合同期限</div>
        <div class="counts">
          <span class="count"><b :class="{ warn: c.overdue > 0 }">{{ c.overdue }}</b> 已逾期</span>
          <span class="count"><b :class="{ soon: c.due_soon7 > 0 }">{{ c.due_soon7 }}</b> 7天内</span>
          <span class="count"><b>{{ c.pending }}</b> 待履行</span>
          <span class="count"><b class="ok">{{ c.done }}</b> 已完成</span>
        </div>
      </div>
      <div class="card-foot">
        <span class="date">{{ (c.created_at || '').replace('T', ' ').slice(0, 16) }} 录入</span>
        <el-button
          text
          size="small"
          type="danger"
          @click.stop="onDelete(c)"
        >删除</el-button>
      </div>
    </div>

    <div class="card card-add" @click="uploadVisible = true">
      <span class="add-icon">＋</span>
      <span>上传新合同</span>
    </div>

    <el-dialog v-model="uploadVisible" title="上传已签署合同" width="460px">
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
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽或 <em>点击选择</em> .docx 文件</div>
        <template #tip>
          <div class="el-upload__tip">支持同时上传最多 {{ MAX_FILES }} 个 DOCX 文件，单个不超过 20MB</div>
        </template>
      </el-upload>
      <div style="margin-top: 16px; text-align: center;">
        <el-button
          type="primary"
          @click="submitUpload"
          :disabled="fileList.length === 0 || uploading"
          :loading="uploading"
        >
          {{ uploading ? '上传中...' : `开始提取 (${fileList.length} 个合同)` }}
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}

.card {
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  transition: box-shadow 0.15s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.card:hover {
  box-shadow: 0 4px 16px rgba(36, 89, 169, 0.12);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.name {
  font-weight: 600;
  color: #1d2b4f;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.period {
  font-size: 13px;
  color: #2459a9;
  background: #eaf2ff;
  border-radius: 6px;
  padding: 4px 10px;
  align-self: flex-start;
}

.period.muted {
  color: #9aabbe;
  background: #f5f7fb;
}

.counts {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: #66758a;
}

.count b {
  font-size: 16px;
  color: #1d2b4f;
  margin-right: 2px;
}

.count b.warn {
  color: #e74c3c;
}

.count b.soon {
  color: #f39c12;
}

.count b.ok {
  color: #27ae60;
}

.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid #f0f4fa;
  padding-top: 8px;
}

.date {
  font-size: 12px;
  color: #9aabbe;
}

.card-add {
  align-items: center;
  justify-content: center;
  border-style: dashed;
  color: #66758a;
  min-height: 120px;
  gap: 6px;
}

.add-icon {
  font-size: 26px;
  color: #2459a9;
}

.upload-icon {
  font-size: 36px;
  color: #2459a9;
}
</style>
