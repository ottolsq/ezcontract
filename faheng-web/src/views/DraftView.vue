<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useDraftStore } from '../stores/draft'
import RichEditor from '../components/draft/RichEditor.vue'

const store = useDraftStore()
const router = useRouter()

const editorRef = ref(null)
const form = ref({
  keywords: '',
  contract_type: '',
  party_a: '',
  party_b: '',
  extra_requirements: '',
})

const reviseInput = ref('')

async function onGenerate() {
  if (!form.value.keywords.trim()) {
    ElMessage.warning('请输入合同关键词')
    return
  }
  await store.generate(form.value)
}

async function onRevise() {
  if (!reviseInput.value.trim()) {
    ElMessage.warning('请输入修改要求')
    return
  }
  await store.revise(reviseInput.value)
  reviseInput.value = ''
}

async function onExport() {
  const html = editorRef.value?.getHtml?.() ?? ''
  try {
    await store.exportDocx(store.title || '合同草稿', html)
    ElMessage.success('已导出 Word 文档')
  } catch (e) {
    // 拦截器已提示错误，这里静默
  }
}

/** 完成本次起草：清空 store + 跳首页 */
function onFinish() {
  store.$reset()
  router.push('/')
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h1>合同起草</h1>
      <div v-if="store.draftId" class="head-actions">
        <el-button type="warning" @click="onExport">导出 Word</el-button>
        <el-button type="primary" @click="onFinish">完成</el-button>
      </div>
    </div>

    <!-- 表单 -->
    <el-card v-if="!store.draftId" class="form-card" shadow="never" v-loading="store.loading">
      <template #header>输入起草需求</template>
      <el-form label-width="90px">
        <el-form-item label="关键词" required>
          <el-input
            v-model="form.keywords"
            placeholder="如：ERP软件采购 私有云部署 三年订阅"
            @keyup.enter="onGenerate"
          />
        </el-form-item>
        <el-form-item label="合同类型">
          <el-select v-model="form.contract_type" placeholder="自动判断" clearable>
            <el-option label="采购合同" value="采购合同" />
            <el-option label="销售合同" value="销售合同" />
            <el-option label="保密协议（NDA）" value="保密协议" />
            <el-option label="服务合同" value="服务合同" />
            <el-option label="劳动合同" value="劳动合同" />
          </el-select>
        </el-form-item>
        <el-form-item label="甲方">
          <el-input v-model="form.party_a" placeholder="留空则使用【甲方名称】占位" />
        </el-form-item>
        <el-form-item label="乙方">
          <el-input v-model="form.party_b" placeholder="留空则使用【乙方名称】占位" />
        </el-form-item>
        <el-form-item label="补充要求">
          <el-input
            v-model="form.extra_requirements"
            type="textarea"
            :rows="3"
            placeholder="如：重点保护甲方数据安全与退出权利"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="store.loading" @click="onGenerate">
            生成合同模板
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 编辑器（单栏 WYSIWYG） -->
    <template v-else>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="下载提醒"
        description="平台不会保留您起草的合同内容，导出后请及时下载并保存到本地，避免丢失。"
        class="download-notice"
      />
      <el-card class="editor-pane" shadow="never">
        <template #header>
          <div class="pane-head">
            <span>{{ store.title }}</span>
            <span class="save-state" :class="{ saving: !store.saved }">
              {{ store.saved ? '已保存' : '保存中…' }}
            </span>
          </div>
        </template>
        <RichEditor
          ref="editorRef"
          :model-value="store.markdown"
          @update:model-value="store.updateContent($event)"
        />
      </el-card>

      <!-- 修订对话 -->
      <el-card class="revise-card" shadow="never">
        <template #header>
          <div class="pane-head">
            <span>对话式修订</span>
            <el-tag v-for="(h, i) in store.history" :key="i" size="small" type="info" class="hist-tag">
              {{ h.instruction.slice(0, 16) }}
            </el-tag>
          </div>
        </template>
        <div class="revise-row">
          <el-input
            v-model="reviseInput"
            placeholder="如：把付款方式改为按验收节点分期付款，并增加数据导出协助条款"
            @keyup.enter="onRevise"
          />
          <el-button type="primary" :loading="store.revising" @click="onRevise">
            AI 修订
          </el-button>
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 16px 24px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
  flex-shrink: 0;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

h1 {
  margin: 0;
  font-size: 24px;
}

.form-card {
  width: 100%;
  max-width: 760px;
  margin: 40px auto;
}

.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.save-state {
  font-size: 12px;
  color: #27ae60;
}

.save-state.saving {
  color: #f39c12;
}

.editor-pane {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-bottom: 14px;
}

.editor-pane :deep(.el-card__body) {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px;
  overflow: auto;
}

.revise-card {
  flex-shrink: 0;
}

.download-notice {
  margin-bottom: 14px;
  flex-shrink: 0;
}

.download-notice :deep(.el-alert__title) {
  font-weight: 600;
}

.revise-row {
  display: flex;
  gap: 10px;
}

.hist-tag {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>