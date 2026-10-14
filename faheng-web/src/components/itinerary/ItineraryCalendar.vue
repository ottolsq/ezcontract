<script setup>
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()

const WEEK_DAYS = ['日', '一', '二', '三', '四', '五', '六']

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
}
</script>

<template>
  <div class="calendar-card">
    <div class="calendar-header">
      <h2>{{ store.currentMonth }}</h2>
      <div class="month-nav">
        <el-button :icon="ArrowLeft" circle size="small" @click="prevMonth" />
        <el-button :icon="ArrowRight" circle size="small" @click="nextMonth" />
      </div>
    </div>

    <div class="calendar-grid">
      <div v-for="d in WEEK_DAYS" :key="d" class="cell header-cell">{{ d }}</div>
      <div
        v-for="(cell, idx) in store.monthDates"
        :key="idx"
        :class="[
          'cell date-cell',
          {
            blank: !cell.date,
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
  padding: 20px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.calendar-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1d2b4f;
}

.month-nav {
  display: flex;
  gap: 8px;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
  flex: 1;
}

.cell {
  aspect-ratio: 1;
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
  aspect-ratio: auto;
  padding-bottom: 4px;
}

.date-cell {
  background: #f7f9fc;
  color: #1d2b4f;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.date-cell:hover {
  background: #eaf2ff;
}

.date-cell.today {
  border-color: #2459a9;
  background: #f0f7ff;
  font-weight: 600;
}

.date-cell.hasEvent {
  background: #eaf2ff;
}

.date-cell.blank {
  background: transparent;
  cursor: default;
}

.day-num {
  position: relative;
  z-index: 1;
}

.event-dot {
  position: absolute;
  top: 4px;
  right: 6px;
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
    padding: 14px;
    border-radius: 12px;
  }

  .calendar-grid {
    gap: 4px;
  }

  .cell {
    font-size: 13px;
    border-radius: 8px;
  }

  .event-dot {
    min-width: 16px;
    height: 16px;
    font-size: 10px;
    top: 2px;
    right: 3px;
  }
}

@media (max-width: 480px) {
  .calendar-card {
    padding: 12px;
  }

  .calendar-header h2 {
    font-size: 18px;
  }
}
</style>
