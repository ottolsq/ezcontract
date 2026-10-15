<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'
import { useVoiceRecorder } from '../../composables/useVoiceRecorder'
import EventForm from './EventForm.vue'
import DayDetailContent from './DayDetailContent.vue'

const store = useItineraryStore()
const visible = ref(false)

const title = computed(() => {
  if (!store.selectedDate) return '当日行程'
  return `${store.selectedDate} 当日行程`
})

function open() {
  visible.value = true
}

// 弹框内语音录入：默认日期 = 点击的日期（语音中提到日期则以后端解析为准，
// 由 default_date 兜底语义保证）。解析成功后确认框叠加在本弹框之上。
const rec = useVoiceRecorder({
  onResult: () => {
    store.voiceDialogVisible = true
  },
  getDefaultDate: () => store.selectedDate,
})

function onVoiceClick() {
  if (!store.selectedArtistId) {
    ElMessage.warning('请先选择或新增一个人员')
    return
  }
  rec.toggle()
}

// 关闭当日弹框时停掉进行中的录音并释放麦克风
function onDialogClose() {
  rec.dispose()
}

const editingEvent = ref(null)
const editDialogVisible = ref(false)

function startEdit(event) {
  editingEvent.value = { ...event }
  editDialogVisible.value = true
}

async function saveEdit() {
  if (!editingEvent.value.title || !editingEvent.value.event_date) {
    ElMessage.warning('请填写行程事项和日期')
    return
  }
  try {
    await store.updateEvent(editingEvent.value.id, editingEvent.value)
    editDialogVisible.value = false
    await store.fetchDailyEvents(store.selectedDate)
    await store.fetchMonthEvents()
  } catch {
    // handled in store
  }
}

const newEvent = ref(null)
const addDialogVisible = ref(false)
const eventTypeOptions = [
  { value: 'meeting', label: '会议' },
  { value: 'performance', label: '演出' },
  { value: 'activity', label: '活动' },
  { value: 'interview', label: '采访' },
  { value: 'recording', label: '录制' },
  { value: 'other', label: '其他' },
]

function startAdd() {
  newEvent.value = {
    artist_id: store.selectedArtistId,
    event_date: store.selectedDate,
    start_time: '',
    end_time: '',
    title: '',
    event_type: 'other',
    location: '',
    summary: '',
    contacts: '',
    materials: '',
    notes: '',
  }
  addDialogVisible.value = true
}

async function saveAdd() {
  if (!newEvent.value.title || !newEvent.value.event_date) {
    ElMessage.warning('请填写行程事项和日期')
    return
  }
  try {
    await store.createEvent(newEvent.value)
    addDialogVisible.value = false
    await store.fetchDailyEvents(store.selectedDate)
    await store.fetchMonthEvents()
  } catch {
    // handled in store
  }
}

async function removeEvent(eventId) {
  await store.deleteEvent(eventId)
  await store.fetchDailyEvents(store.selectedDate)
  await store.fetchMonthEvents()
  // 删光当日行程后弹框保持打开，显示「当日暂无行程」
}

defineExpose({ open })
</script>

<template>
  <div>
    <!-- 当日行程弹框（桌面/移动统一） -->
    <el-dialog
      v-model="visible"
      :title="title"
      width="640px"
      :close-on-click-modal="true"
      class="day-detail-dialog"
      @close="onDialogClose"
    >
      <DayDetailContent
        @add="startAdd"
        @edit="startEdit"
        @remove="removeEvent"
        @voice="onVoiceClick"
      />
    </el-dialog>

    <!-- 编辑/新增弹窗 -->
    <el-dialog
      v-model="editDialogVisible"
      title="编辑行程"
      width="640px"
      :close-on-click-modal="false"
    >
      <EventForm v-if="editingEvent" v-model="editingEvent" :artists="store.artists" :event-type-options="eventTypeOptions" />
      <template #footer>
        <el-button size="small" @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="addDialogVisible"
      title="新增行程"
      width="640px"
      :close-on-click-modal="false"
    >
      <EventForm v-if="newEvent" v-model="newEvent" :artists="store.artists" :event-type-options="eventTypeOptions" />
      <template #footer>
        <el-button size="small" @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="saveAdd">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 弹框内行程列表滚动区：限制高度避免长列表撑爆视口 */
:deep(.day-detail-dialog .el-dialog__body) {
  max-height: calc(100vh - 200px);
  overflow-y: auto;
}

@media (max-width: 768px) {
  :deep(.day-detail-dialog .el-dialog) {
    width: 92% !important;
  }
}
</style>
