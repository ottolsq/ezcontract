<script setup>
import { computed } from 'vue'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()
const emit = defineEmits(['date-click'])

const WEEK_DAYS = ['日', '一', '二', '三', '四', '五', '六']

const calendarDays = computed(() => {
  const [year, month] = store.currentMonth.split('-').map(Number)
  const firstDayOfMonth = new Date(year, month - 1, 1)
  const lastDayOfMonth = new Date(year, month, 0)

  const startOffset = firstDayOfMonth.getDay() // 0 = Sunday
  const totalDays = lastDayOfMonth.getDate()

  const days = []

  // 上月尾部日期（灰色显示）
  const prevMonthLastDay = new Date(year, month - 1, 0).getDate()
  for (let i = startOffset - 1; i >= 0; i--) {
    const d = prevMonthLastDay - i
    days.push({ day: d, date: '', isCurrentMonth: false })
  }

  // 当月日期
  for (let d = 1; d <= totalDays; d++) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    days.push({ day: d, date, isCurrentMonth: true })
  }

  // 下月头部日期（灰色显示），补齐到 42 格
  const remaining = 42 - days.length
  for (let d = 1; d <= remaining; d++) {
    days.push({ day: d, date: '', isCurrentMonth: false })
  }

  return days
})

function prevMonth() {
  store.changeMonth(-1)
}

function nextMonth() {
  store.changeMonth(1)
}

function dateEvents(date) {
  if (!date) return []
  return store.eventsByDate[date] || []
}

function hasEvent(date) {
  return dateEvents(date).length > 0
}

function eventCount(date) {
  return dateEvents(date).length
}

function selectDate(date) {
  if (!date) return
  store.fetchDailyEvents(date)
  emit('date-click', date)
}
</script>

<template>
  <div class="calendar-card">
    <div class="calendar-header">
      <div class="title-group">
        <h2>{{ store.currentMonth }}</h2>
        <span v-if="store.loading" class="loading-hint">加载中…</span>
      </div>
      <div class="month-nav">
        <el-button :icon="ArrowLeft" circle size="small" @click="prevMonth" />
        <el-button :icon="ArrowRight" circle size="small" @click="nextMonth" />
      </div>
    </div>

    <div class="calendar-grid">
      <div v-for="d in WEEK_DAYS" :key="d" class="cell header-cell">{{ d }}</div>
      <div
        v-for="(cell, idx) in calendarDays"
        :key="idx"
        :class="[
          'cell date-cell',
          {
            'other-month': !cell.isCurrentMonth,
            today: cell.date === store.selectedDate,
            hasEvent: hasEvent(cell.date),
          },
        ]"
        @click="selectDate(cell.date)"
      >
        <span class="day-num">{{ cell.day }}</span>
        <span v-if="hasEvent(cell.date)" class="event-dot">{{ eventCount(cell.date) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.calendar-card {
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 16px;
  padding: 16px 20px 20px;
  width: 100%;
}

.calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.title-group {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.calendar-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1d2b4f;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.loading-hint {
  font-size: 12px;
  color: #9aabbe;
}

.month-nav {
  display: flex;
  gap: 8px;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
}

.cell {
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  position: relative;
}

.header-cell {
  color: #9aabbe;
  font-weight: 600;
  padding: 6px 0;
  min-height: 32px;
}

.date-cell {
  background: #f7f9fc;
  color: #1d2b4f;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
  min-height: 72px;
  align-items: flex-start;
  justify-content: flex-start;
  padding: 8px;
}

.date-cell:hover {
  background: #eaf2ff;
}

.date-cell.other-month {
  color: #c8d0dc;
  background: #fafbfd;
}

.date-cell.today {
  border-color: #2459a9;
  background: #f0f7ff;
  font-weight: 600;
}

.date-cell.hasEvent {
  background: #eaf2ff;
}

.day-num {
  position: relative;
  z-index: 1;
  font-size: 14px;
}

.event-dot {
  position: absolute;
  top: 6px;
  right: 8px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: #2459a9;
  color: #fff;
  border-radius: 999px;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 768px) {
  .calendar-card {
    padding: 12px 14px 14px;
    border-radius: 12px;
  }

  .calendar-grid {
    gap: 4px;
  }

  .cell {
    font-size: 13px;
    border-radius: 8px;
  }

  .header-cell {
    min-height: 24px;
    padding: 4px 0;
  }

  .date-cell {
    min-height: 52px;
    padding: 6px;
  }

  .day-num {
    font-size: 13px;
  }

  .event-dot {
    min-width: 16px;
    height: 16px;
    font-size: 10px;
    top: 4px;
    right: 5px;
  }
}

@media (max-width: 480px) {
  .calendar-card {
    padding: 10px 12px 12px;
  }

  .calendar-header h2 {
    font-size: 18px;
  }

  .header-cell {
    min-height: 22px;
    font-size: 12px;
  }

  .date-cell {
    min-height: 46px;
    padding: 4px;
  }

  .day-num {
    font-size: 12px;
  }

  .event-dot {
    min-width: 14px;
    height: 14px;
    font-size: 9px;
    padding: 0 3px;
    top: 3px;
    right: 3px;
  }
}
</style>
