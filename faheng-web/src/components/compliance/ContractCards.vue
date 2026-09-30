<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useComplianceStore } from '../../stores/compliance'

const store = useComplianceStore()
const uploadVisible = ref(false)
const uploading = ref(false)

async function beforeUpload(file) {
  if (!/\.docx$/i.test(file.name)) {
    ElMessage.error('履约模块目前仅支持 .docx 文件')
    return false
  }
  uploading.value = true
  try {
    await store.uploadFile(file)
    uploadVisible.value = false
  } catch {
    /* 拦截器已提示 */
  } finally {
    uploading.value = false
  }
  return false
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
        :before-upload="beforeUpload"
        :show-file-list="false"
        accept=".docx"
        v-loading="uploading"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽或 <em>点击选择</em> .docx 文件</div>
      </el-upload>
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
