<script setup>
import { ref, computed } from 'vue'
import { Edit, Delete, Microphone, Loading } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'
import { useVoiceRecorder } from '../../composables/useVoiceRecorder'

const store = useItineraryStore()
const emit = defineEmits(['add', 'edit', 'remove', 'voice'])

// 单例状态机：弹框语音按钮三态渲染（裁决 2——非本来源 busy 时禁用）
const rec = useVoiceRecorder()
const dialogOwnsRecording = computed(
  () => rec.isBusy() && rec.source.value === 'dialog'
)
const otherSourceBusy = computed(
  () => rec.isBusy() && rec.source.value !== 'dialog'
)

const eventTypeMap = {
  meeting: '会议',
  performance: '演出',
  activity: '活动',
  interview: '采访',
  recording: '录制',
  other: '其他',
}

const detailVisible = ref(false)
const selectedEvent = ref(null)

function typeLabel(type) {
  return eventTypeMap[type] || '其他'
}

function openDetail(event) {
  selectedEvent.value = event
  detailVisible.value = true
}

function closeDetail() {
  detailVisible.value = false
  selectedEvent.value = null
}

async function remove(eventId) {
  try {
    await ElMessageBox.confirm('确定删除这条行程吗？', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    emit('remove', eventId)
  } catch {
    // cancel
  }
}
</script>

<template>
  <div>
    <div class="detail-actions">
      <el-button type="primary" size="small" :icon="Edit" @click="emit('add')">手动新增</el-button>
      <el-tooltip
        content="语音录入进行中"
        placement="top"
        :disabled="!otherSourceBusy"
      >
        <span class="voice-btn-wrap">
          <el-button
            size="small"
            :icon="Microphone"
            :type="dialogOwnsRecording && rec.phase.value === 'recording' ? 'danger' : 'default'"
            :loading="dialogOwnsRecording && rec.phase.value === 'processing'"
            :disabled="otherSourceBusy"
            @click="emit('voice')"
          >
            <template #icon>
              <el-icon v-if="dialogOwnsRecording && rec.phase.value === 'recording'"><Loading class="spin" /></el-icon>
              <el-icon v-else><Microphone /></el-icon>
            </template>
            {{ dialogOwnsRecording && rec.phase.value === 'recording' ? '正在听·点击结束' : dialogOwnsRecording && rec.phase.value === 'processing' ? '识别中…' : '语音录入' }}
          </el-button>
        </span>
      </el-tooltip>
    </div>
    <div v-if="store.dailyEvents.length === 0" class="empty-state">
      <p>当日暂无行程</p>
    </div>
    <div v-else class="event-cards">
      <div
        v-for="event in store.dailyEvents"
        :key="event.id"
        class="event-card"
        :style="{ borderLeftColor: event.artist_color || '#2459a9' }"
        @click="openDetail(event)"
      >
        <div class="event-main">
          <div class="event-time">{{ event.start_time || '--:--' }} ~ {{ event.end_time || '--:--' }}</div>
          <div class="event-title">{{ event.title }}</div>
          <el-tag size="small" class="event-type">{{ typeLabel(event.event_type) }}</el-tag>
        </div>
        <div class="event-meta">
          <div v-if="event.location"><b>地点：</b>{{ event.location }}</div>
          <div v-if="event.summary"><b>摘要：</b>{{ event.summary }}</div>
          <div v-if="event.contacts"><b>对接人：</b>{{ event.contacts }}</div>
          <div v-if="event.materials"><b>物料：</b>{{ event.materials }}</div>
          <div v-if="event.notes"><b>备注：</b>{{ event.notes }}</div>
        </div>
        <div class="event-actions">
          <el-button link size="small" :icon="Edit" @click.stop="emit('edit', event)">编辑</el-button>
          <el-button link type="danger" size="small" :icon="Delete" @click.stop="remove(event.id)">删除</el-button>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="detailVisible"
      title="行程详情"
      width="520px"
      :close-on-click-modal="true"
      class="event-detail-dialog"
      @closed="closeDetail"
    >
      <div v-if="selectedEvent" class="detail-body">
        <div class="detail-header">
          <div class="detail-time">{{ selectedEvent.start_time || '--:--' }} ~ {{ selectedEvent.end_time || '--:--' }}</div>
          <h3 class="detail-title">{{ selectedEvent.title }}</h3>
          <el-tag size="small">{{ typeLabel(selectedEvent.event_type) }}</el-tag>
        </div>
        <div class="detail-fields">
          <div v-if="selectedEvent.location" class="detail-field">
            <span class="field-label">地点</span>
            <span class="field-value">{{ selectedEvent.location }}</span>
          </div>
          <div v-if="selectedEvent.summary" class="detail-field">
            <span class="field-label">摘要</span>
            <span class="field-value">{{ selectedEvent.summary }}</span>
          </div>
          <div v-if="selectedEvent.contacts" class="detail-field">
            <span class="field-label">对接人</span>
            <span class="field-value">{{ selectedEvent.contacts }}</span>
          </div>
          <div v-if="selectedEvent.materials" class="detail-field">
            <span class="field-label">物料准备</span>
            <span class="field-value">{{ selectedEvent.materials }}</span>
          </div>
          <div v-if="selectedEvent.notes" class="detail-field">
            <span class="field-label">备注</span>
            <span class="field-value">{{ selectedEvent.notes }}</span>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.detail-actions {
  margin-bottom: 16px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}

/* el-button 禁用态包一层 span 才能挂 tooltip（disabled 按钮不触发鼠标事件） */
.voice-btn-wrap {
  display: inline-flex;
}

.spin {
  animation: voice-rotate 1s linear infinite;
}

@keyframes voice-rotate {
  to {
    transform: rotate(360deg);
  }
}

.empty-state {
  text-align: center;
  padding: 40px 0;
  color: #9aabbe;
  font-size: 14px;
}

.event-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: calc(80vh - 120px);
  overflow-y: auto;
  padding-right: 4px;
}

@media (max-width: 768px) {
  .event-cards {
    max-height: calc(70vh - 120px);
  }
}

.event-card {
  background: #fff;
  border: 1px solid #e4e9f2;
  border-left-width: 4px;
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
}

.event-card:hover {
  border-color: #2459a9;
  box-shadow: 0 4px 12px rgba(36, 89, 169, 0.1);
}

.event-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.event-time {
  font-size: 13px;
  color: #2459a9;
  background: #eaf2ff;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 500;
}

.event-title {
  font-size: 15px;
  font-weight: 600;
  color: #1d2b4f;
}

.event-type {
  margin-left: auto;
}

.event-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
  font-size: 13px;
  color: #66758a;
  margin-bottom: 12px;
}

.event-meta div {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 768px) {
  .event-meta {
    grid-template-columns: 1fr;
  }
}

.event-detail-dialog :deep(.el-dialog__body) {
  padding: 0 20px 20px;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding-bottom: 14px;
  border-bottom: 1px solid #e4e9f2;
}

.detail-time {
  font-size: 13px;
  color: #2459a9;
  background: #eaf2ff;
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 500;
}

.detail-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1d2b4f;
}

.detail-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 12px;
  color: #9aabbe;
  font-weight: 500;
}

.field-value {
  font-size: 14px;
  color: #1d2b4f;
  line-height: 1.6;
  word-break: break-word;
}

@media (max-width: 768px) {
  .event-detail-dialog :deep(.el-dialog) {
    width: 92% !important;
  }

  .detail-title {
    font-size: 16px;
  }
}
</style>
