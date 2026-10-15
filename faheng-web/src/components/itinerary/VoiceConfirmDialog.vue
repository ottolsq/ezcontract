<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()
const visible = computed({
  get: () => store.voiceDialogVisible,
  set: (v) => { store.voiceDialogVisible = v },
})

const eventTypeOptions = [
  { value: 'meeting', label: '会议' },
  { value: 'performance', label: '演出' },
  { value: 'activity', label: '活动' },
  { value: 'interview', label: '采访' },
  { value: 'recording', label: '录制' },
  { value: 'other', label: '其他' },
]

function addEvent() {
  store.voiceParsedEvents.push({
    artist_id: store.selectedArtistId,
    artist_name: store.selectedArtist?.name || '',
    event_date: '',
    start_time: '',
    end_time: '',
    title: '',
    event_type: 'other',
    location: '',
    summary: '',
    contacts: '',
    materials: '',
    notes: '',
    raw_text: store.voiceText,
    _key: Math.random().toString(36).slice(2),
  })
}

function removeEvent(index) {
  store.voiceParsedEvents.splice(index, 1)
}

function close() {
  store.resetVoice()
}

async function confirm() {
  // 校验必填
  const invalid = store.voiceParsedEvents.some((ev) => !ev.artist_id || !ev.event_date || !ev.title)
  if (invalid) {
    ElMessage.warning('请补全每条行程的人员、日期和事项')
    return
  }
  const payload = store.voiceParsedEvents.map((ev) => ({
    artist_id: ev.artist_id,
    event_date: ev.event_date,
    start_time: ev.start_time,
    end_time: ev.end_time,
    title: ev.title,
    event_type: ev.event_type,
    location: ev.location,
    summary: ev.summary,
    contacts: ev.contacts,
    materials: ev.materials,
    notes: ev.notes,
  }))
  try {
    await store.confirmVoiceEvents(payload)
    store.voiceDialogVisible = false
    store.voiceText = ''
    store.voiceParsedEvents = []
    await store.fetchMonthEvents()
    await store.fetchDailyEvents(store.selectedDate)
  } catch (e) {
    // error handled in store
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="确认行程"
    width="720px"
    :close-on-click-modal="false"
    @closed="close"
    class="voice-confirm-dialog"
    destroy-on-close
  >
    <div class="hint">
      <p>请核对语音识别结果，修改后点击确认保存。</p>
      <p class="fields-hint">
        必要字段：<b>人员</b>、<b>日期</b>、<b>行程事项</b>；可选字段：时间、地点、类型、摘要、对接人、物料、备注
      </p>
    </div>

    <div v-if="store.voiceText" class="raw-text">
      <b>识别原文：</b>{{ store.voiceText }}
    </div>

    <div class="events-list">
      <div
        v-for="(ev, idx) in store.voiceParsedEvents"
        :key="ev._key"
        class="event-form-card"
      >
        <div class="form-head">
          <span class="form-title">行程 {{ idx + 1 }}</span>
          <el-button link type="danger" size="small" @click="removeEvent(idx)">删除</el-button>
        </div>
        <div class="form-grid">
          <div class="form-item">
            <label class="required">人员</label>
            <el-select v-model="ev.artist_id" placeholder="选择人员" size="small" style="width: 100%">
              <el-option
                v-for="artist in store.artists"
                :key="artist.id"
                :label="artist.name"
                :value="artist.id"
              />
            </el-select>
          </div>

          <div class="form-item">
            <label class="required">日期</label>
            <el-date-picker
              v-model="ev.event_date"
              type="date"
              placeholder="选择日期"
              size="small"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </div>

          <div class="form-item">
            <label>时间段</label>
            <div class="time-range">
              <el-time-picker
                v-model="ev.start_time"
                placeholder="开始"
                size="small"
                value-format="HH:mm"
                style="width: 100%"
              />
              <span>~</span>
              <el-time-picker
                v-model="ev.end_time"
                placeholder="结束"
                size="small"
                value-format="HH:mm"
                style="width: 100%"
              />
            </div>
          </div>

          <div class="form-item">
            <label class="required">行程事项</label>
            <el-input v-model="ev.title" placeholder="如：品牌发布会" size="small" />
          </div>

          <div class="form-item">
            <label>事项类型</label>
            <el-select v-model="ev.event_type" placeholder="类型" size="small" style="width: 100%">
              <el-option
                v-for="opt in eventTypeOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>

          <div class="form-item">
            <label>地点</label>
            <el-input v-model="ev.location" placeholder="地点" size="small" />
          </div>

          <div class="form-item wide">
            <label>内容摘要</label>
            <el-input v-model="ev.summary" type="textarea" :rows="2" placeholder="活动内容摘要" size="small" />
          </div>

          <div class="form-item">
            <label>随行/对接人</label>
            <el-input v-model="ev.contacts" placeholder="对接人姓名" size="small" />
          </div>

          <div class="form-item">
            <label>物料准备</label>
            <el-input v-model="ev.materials" placeholder="需要准备的物料" size="small" />
          </div>

          <div class="form-item wide">
            <label>备注</label>
            <el-input v-model="ev.notes" type="textarea" :rows="2" placeholder="其他备注" size="small" />
          </div>
        </div>
      </div>
    </div>

    <div v-if="store.voiceParsedEvents.length === 0" class="empty-tip">
      <p>未解析到行程，请重试或手动添加。</p>
      <el-button type="primary" size="small" @click="addEvent">手动添加</el-button>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button size="small" @click="addEvent">+ 添加一条</el-button>
        <div class="right-actions">
          <el-button size="small" @click="close">取消</el-button>
          <el-button type="primary" size="small" :loading="store.voiceSaving" @click="confirm">确认保存</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.hint {
  margin-bottom: 12px;
  color: #66758a;
  font-size: 13px;
}

.hint p {
  margin: 0 0 4px;
}

.fields-hint {
  color: #9aabbe;
}

.fields-hint b {
  color: #2459a9;
}

.raw-text {
  background: #f7f9fc;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  color: #1d2b4f;
  margin-bottom: 16px;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 50vh;
  overflow-y: auto;
  padding-right: 4px;
}

.event-form-card {
  border: 1px solid #e4e9f2;
  border-radius: 12px;
  padding: 14px;
}

.form-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.form-title {
  font-weight: 600;
  color: #1d2b4f;
  font-size: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-item.wide {
  grid-column: span 3;
}

.form-item label {
  font-size: 12px;
  color: #66758a;
}

.form-item label.required::after {
  content: '*';
  color: #e74c3c;
  margin-left: 2px;
}

.time-range {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 6px;
}

.empty-tip {
  text-align: center;
  padding: 24px;
  color: #9aabbe;
  font-size: 14px;
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  width: 100%;
}

.right-actions {
  display: flex;
  gap: 10px;
}

@media (max-width: 768px) {
  .voice-confirm-dialog :deep(.el-dialog) {
    width: 92% !important;
    margin-top: 5vh !important;
  }

  .form-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .form-item.wide {
    grid-column: span 2;
  }

  .events-list {
    max-height: 55vh;
  }
}

@media (max-width: 480px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-item.wide {
    grid-column: span 1;
  }
}
</style>
