<script setup>
import { onMounted } from 'vue'
import { useComplianceStore } from '../stores/compliance'
import UploadPanel from '../components/compliance/UploadPanel.vue'
import ExtractingPanel from '../components/compliance/ExtractingPanel.vue'
import ContractCards from '../components/compliance/ContractCards.vue'
import MilestoneTable from '../components/compliance/MilestoneTable.vue'

const store = useComplianceStore()

onMounted(() => store.fetchContracts())
</script>

<template>
  <div class="page compliance-page">
    <div class="page-head">
      <h1>履约提醒</h1>
      <div v-if="store.phase === 'detail'" class="head-actions">
        <el-button @click="store.goList()">← 返回列表</el-button>
      </div>
      <div v-else-if="store.phase === 'list'" class="head-actions">
        <el-alert
          v-if="store.contracts.some((c) => c.overdue > 0)"
          type="error"
          :closable="false"
          show-icon
          title="有履约节点已逾期"
          class="overdue-alert"
        />
      </div>
    </div>

    <!-- 视图状态机 -->
    <UploadPanel v-if="store.phase === 'empty'" />

    <ExtractingPanel v-else-if="store.phase === 'processing'" />

    <template v-else-if="store.phase === 'list'">
      <ContractCards />
    </template>

    <template v-else-if="store.phase === 'detail' && store.contract">
      <div class="contract-head">
        <div class="contract-info">
          <span class="contract-name">{{ store.contract.contract.filename }}</span>
          <el-tag v-if="store.contract.contract.sign_date" size="small" type="info">
            签署日 {{ store.contract.contract.sign_date }}
          </el-tag>
          <el-tag
            v-if="store.contract.contract.start_date"
            size="small"
            type="info"
          >
            合同期限 {{ store.contract.contract.start_date }} ~ {{ store.contract.contract.end_date || '长期' }}
          </el-tag>
          <el-tag
            v-if="store.contract.contract.error"
            size="small"
            type="warning"
          >{{ store.contract.contract.error }}</el-tag>
        </div>
        <div class="stats-strip">
          <div class="stat">
            <b>{{ store.stats.total }}</b><span>总节点</span>
          </div>
          <div class="stat warn">
            <b>{{ store.stats.overdue }}</b><span>已逾期</span>
          </div>
          <div class="stat soon">
            <b>{{ store.stats.dueSoon7 }}</b><span>7天内到期</span>
          </div>
          <div class="stat">
            <b>{{ store.stats.pending }}</b><span>待履行</span>
          </div>
          <div class="stat ok">
            <b>{{ store.stats.done }}</b><span>已完成</span>
          </div>
        </div>
      </div>

      <div class="table-scroll">
        <MilestoneTable />
      </div>
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

.compliance-page {
  overflow-y: auto;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  flex-shrink: 0;
}

h1 {
  margin: 0;
  font-size: 24px;
}

.overdue-alert {
  flex: 1;
  margin-right: 12px;
}

.contract-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 14px;
  flex-shrink: 0;
}

.contract-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.contract-name {
  font-weight: 600;
  color: #1d2b4f;
  font-size: 15px;
}

.stats-strip {
  display: flex;
  gap: 22px;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 56px;
}

.stat b {
  font-size: 20px;
  color: #1d2b4f;
  line-height: 1.2;
}

.stat span {
  font-size: 12px;
  color: #9aabbe;
}

.stat.warn b {
  color: #e74c3c;
}

.stat.soon b {
  color: #f39c12;
}

.stat.ok b {
  color: #27ae60;
}

.table-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: 20px;
}
</style>
