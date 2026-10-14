<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'
import EventForm from './EventForm.vue'
import DayDetailContent from './DayDetailContent.vue'

const store = useItineraryStore()
const visible = ref(false)
const isMobile = ref(false)

onMounted(() => {
  isMobile.value = window.innerWidth <= 768
  window.addEventListener('resize', () => {
    isMobile.value = window.innerWidth <= 768
  })
})

const title = computed(() => {
  if (!store.selectedDate) return '当日行程'
  return `${store.selectedDate} 当日行程`
})

function open() {
  visible.value = true
}

function close() {
  visible.value = false
}

watch(
  () => store.dailyEvents,
  () => {
    if (store.dailyEvents.length > 0 && !visible.value) {
      visible.value = true
    }
  }
)

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
  if (store.dailyEvents.length === 0) {
    close()
  }
}

defineExpose({ open })
</script>

<template>
  <div>
    <!-- 桌面端抽屉 -->
    <el-drawer
      v-if="!isMobile"
      v-model="visible"
      :title="title"
      direction="rtl"
      size="640px"
      :close-on-click-modal="true"
      class="day-detail-drawer"
    >
      <DayDetailContent @add="startAdd" @edit="startEdit" @remove="removeEvent" />
    </el-drawer>

    <!-- 移动端弹窗 -->
    <el-dialog
      v-else
      v-model="visible"
      :title="title"
      width="92%"
      top="18vh"
      :close-on-click-modal="true"
      class="day-detail-dialog"
    >
      <DayDetailContent @add="startAdd" @edit="startEdit" @remove="removeEvent" />
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
:deep(.day-detail-dialog .el-dialog__body) {
  padding-top: 10%;
  padding-bottom: 16px;
  max-height: calc(70vh - 120px);
  overflow-y: auto;
}
</style>
