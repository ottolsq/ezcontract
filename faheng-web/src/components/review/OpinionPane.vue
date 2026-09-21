<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useReviewStore } from '../../stores/review'

const store = useReviewStore()

const showModify = ref(false)
const showReject = ref(false)
const modifyText = ref('')
const rejectReason = ref('经业务确认，风险可接受')

const rejectOptions = [
  '经业务确认，风险可接受',
  '已通过其他条款覆盖',
  '谈判后决定保留原条款',
  '其他',
]

const risk = computed(() => store.currentRisk)
const existingDecision = computed(() =>
  risk.value ? store.decisions[risk.value.risk_id] : null,
)

const severityLabel = computed(() => {
  if (!risk.value) return ''
  if (existingDecision.value) {
    const label = { accepted: '已采纳', modified: '已修改后采纳', rejected: '已不采纳' }[
      existingDecision.value.type
    ]
    return `已处理 · ${label}`
  }
  return risk.value.level === 'high' ? '高风险 · 必须修改' : '中风险 · 建议争取'
})

// 切换风险时重置编辑面板
watch(
  () => store.currentRiskId,
  () => {
    showModify.value = false
    showReject.value = false
  },
)

async function onAccept() {
  await store.saveDecision(risk.value, 'accepted')
  ElMessage.success('已采纳建议条款')
}

function openModify() {
  modifyText.value =
    existingDecision.value?.type === 'modified'
      ? existingDecision.value.text
      : risk.value.suggestion
  showReject.value = false
  showModify.value = true
}

async function onSaveModify() {
  if (!modifyText.value.trim()) {
    ElMessage.warning('条款内容不能为空')
    return
  }
  await store.saveDecision(risk.value, 'modified', { text: modifyText.value.trim() })
  showModify.value = false
  ElMessage.success('已保存修改后条款')
}

function openReject() {
  showModify.value = false
  showReject.value = true
}

async function onSaveReject() {
  await store.saveDecision(risk.value, 'rejected', { reason: rejectReason.value })
  showReject.value = false
  ElMessage.success('已标记不采纳')
}

async function onUndo() {
  await store.undoDecision(risk.value)
}
</script>

<template>
  <el-card v-if="risk" class="opinion-pane" shadow="never">
    <template #header>
      <div class="head">
        <span>法务意见</span>
        <span class="clause-no">{{ risk.clause_no }}</span>
      </div>
    </template>

    <div class="severity" :class="[risk.level, { handled: existingDecision }]">
      {{ severityLabel }}
    </div>

    <h3 class="risk-title">{{ risk.title }}</h3>

    <div v-if="risk.matched_rules.length" class="rules">
      <el-tag v-for="rid in risk.matched_rules" :key="rid" size="small" type="warning">
        {{ rid }}
      </el-tag>
    </div>

    <div class="section">
      <div class="label">风险说明</div>
      <div>{{ risk.issue }}</div>
    </div>
    <div class="section">
      <div class="label">对甲方的影响</div>
      <div>{{ risk.impact }}</div>
    </div>
    <div class="section">
      <div class="label">建议替换条款</div>
      <div class="suggestion">{{ risk.suggestion }}</div>
    </div>

    <!-- 决策按钮 -->
    <div class="decision-actions">
      <el-button type="primary" @click="onAccept">采纳</el-button>
      <el-button @click="openModify">修改</el-button>
      <el-button @click="openReject">不采纳</el-button>
    </div>

    <!-- 修改面板 -->
    <div v-if="showModify" class="edit-box">
      <div class="label">修改后的替换条款</div>
      <el-input v-model="modifyText" type="textarea" :rows="5" />
      <div class="edit-actions">
        <el-button type="primary" size="small" @click="onSaveModify">保存并采纳</el-button>
        <el-button size="small" @click="showModify = false">取消</el-button>
      </div>
    </div>

    <!-- 不采纳面板 -->
    <div v-if="showReject" class="edit-box">
      <div class="label">不采纳原因</div>
      <el-select v-model="rejectReason" style="width: 100%">
        <el-option v-for="o in rejectOptions" :key="o" :label="o" :value="o" />
      </el-select>
      <div class="edit-actions">
        <el-button type="primary" size="small" @click="onSaveReject">确认不采纳</el-button>
        <el-button size="small" @click="showReject = false">取消</el-button>
      </div>
    </div>

    <!-- 已决策状态 -->
    <el-alert v-if="existingDecision" class="decision-status" type="success" :closable="false">
      <template #title>
        {{
          existingDecision.type === 'rejected'
            ? `已不采纳：${existingDecision.reason || '保留原条款'}`
            : existingDecision.type === 'modified'
              ? '已修改后采纳：以编辑后的条款进入修改清单'
              : '已采纳：建议条款已加入合同修改清单'
        }}
      </template>
      <el-button link size="small" @click="onUndo">撤销决策</el-button>
    </el-alert>
  </el-card>

  <el-card v-else shadow="never">
    <el-empty description="选择左侧风险项查看意见" :image-size="60" />
  </el-card>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.clause-no {
  color: #66758a;
  font-size: 13px;
}

.severity {
  display: inline-block;
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 10px;
}

.severity.high {
  background: #fdecea;
  color: #b42318;
}

.severity.medium {
  background: #fef5e7;
  color: #a15c00;
}

.severity.handled {
  background: #e8f8f2;
  color: #087a55;
}

.risk-title {
  margin: 6px 0 10px;
  font-size: 17px;
}

.rules {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.section {
  padding: 10px 0;
  border-top: 1px solid #eef2f8;
}

.label {
  color: #66758a;
  font-size: 12px;
  margin-bottom: 5px;
}

.suggestion {
  background: #e8f8f2;
  border-radius: 8px;
  padding: 10px;
  line-height: 1.7;
}

.decision-actions {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}

.edit-box {
  margin-top: 10px;
  background: #f4f7fb;
  border-radius: 10px;
  padding: 12px;
}

.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.decision-status {
  margin-top: 12px;
}
</style>
