<script setup>
import { Edit, Delete } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()
const emit = defineEmits(['add', 'edit', 'remove'])

const eventTypeMap = {
  meeting: '会议',
  performance: '演出',
  activity: '活动',
  interview: '采访',
  recording: '录制',
  other: '其他',
}

function typeLabel(type) {
  return eventTypeMap[type] || '其他'
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
      <el-button type="primary" size="small" :icon="Edit" @click="emit('add')">新增当日行程</el-button>
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
          <el-button link size="small" :icon="Edit" @click="emit('edit', event)">编辑</el-button>
          <el-button link type="danger" size="small" :icon="Delete" @click="remove(event.id)">删除</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-actions {
  margin-bottom: 16px;
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
}

.event-card {
  background: #fff;
  border: 1px solid #e4e9f2;
  border-left-width: 4px;
  border-radius: 10px;
  padding: 14px;
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
</style>
