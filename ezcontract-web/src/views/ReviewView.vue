<script setup>
import { nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useReviewStore } from '../stores/review'
import { download } from '../api'
import UploadZone from '../components/review/UploadZone.vue'
import ProcessingPanel from '../components/review/ProcessingPanel.vue'
import StatsStrip from '../components/review/StatsStrip.vue'
import RiskListPane from '../components/review/RiskListPane.vue'
import ContractPane from '../components/review/ContractPane.vue'
import OpinionPane from '../components/review/OpinionPane.vue'
import ReportPanel from '../components/review/ReportPanel.vue'

const store = useReviewStore()
const contractPaneRef = ref(null)

// 选中风险变化 → 合同正文滚动到对应条款
watch(
  () => store.currentRiskId,
  async (id) => {
    if (!id) return
    await nextTick()
    contractPaneRef.value?.scrollToClause(store.currentRisk?.clause_id)
  },
)

function goReport() {
  if (store.processedCount === 0) {
    ElMessage.warning('请先在风险清单中处理至少一项')
    return
  }
  store.phase = 'report'
}

async function exportContract() {
  await download(`/review/${store.reviewId}/export`, `修改版合同.docx`)
  ElMessage.success('已导出修改后合同')
}

async function exportReport() {
  await download(`/review/${store.reviewId}/report/export`, `审核报告.docx`)
  ElMessage.success('已导出审核报告')
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h1>合同审查</h1>
      <div v-if="store.phase === 'workspace'" class="head-actions">
        <el-button @click="goReport">查看审核报告</el-button>
        <el-button type="primary" @click="exportContract">导出修改后合同</el-button>
      </div>
      <div v-else-if="store.phase === 'report'" class="head-actions">
        <el-button @click="store.phase = 'workspace'">返回审核</el-button>
        <el-button @click="exportContract">导出修改后合同</el-button>
        <el-button type="primary" @click="exportReport">导出审核报告</el-button>
      </div>
    </div>

    <!-- 视图状态机 -->
    <UploadZone v-if="store.phase === 'upload' || store.phase === 'uploaded'" />

    <ProcessingPanel v-else-if="store.phase === 'processing'" />

    <template v-else-if="store.phase === 'workspace'">
      <StatsStrip />
      <div class="workspace">
        <RiskListPane />
        <ContractPane ref="contractPaneRef" />
        <OpinionPane />
      </div>
    </template>

    <ReportPanel v-else-if="store.phase === 'report'" />
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

h1 {
  margin: 0;
  font-size: 24px;
}

.workspace {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr) 360px;
  gap: 14px;
  align-items: start;
}

@media (max-width: 1100px) {
  .workspace {
    grid-template-columns: 240px minmax(0, 1fr);
  }
}

@media (max-width: 860px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>
