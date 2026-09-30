<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import { useNotificationsStore } from '../stores/notifications'

const store = useNotificationsStore()
const router = useRouter()

const recent = computed(() => store.items.slice(0, 10))

function kindIcon(kind) {
  return kind === 'overdue' ? '⚠️' : '⏰'
}

function timeText(iso) {
  if (!iso) return ''
  return iso.replace('T', ' ').slice(5, 16)
}

async function onItemClick(n) {
  await store.markRead([n.id])
  router.push('/compliance')
}

onMounted(() => store.startPolling())
onUnmounted(() => store.stopPolling())
</script>

<template>
  <el-popover placement="bottom" :width="340" trigger="click">
    <template #reference>
      <button class="bell-btn" title="履约提醒通知">
        <el-icon :size="18"><Bell /></el-icon>
        <el-badge
          :value="store.unread"
          :hidden="store.unread === 0"
          :max="99"
          class="bell-badge"
        />
      </button>
    </template>

    <div class="notif-panel">
      <div class="notif-head">
        <span>履约提醒</span>
        <el-button v-if="store.unread > 0" text size="small" @click="store.markAllRead()">
          全部已读
        </el-button>
      </div>

      <el-empty v-if="!recent.length" description="暂无提醒" :image-size="60" />

      <div v-else class="notif-list">
        <div
          v-for="n in recent"
          :key="n.id"
          class="notif-item"
          :class="{ unread: !n.is_read }"
          @click="onItemClick(n)"
        >
          <span class="notif-icon">{{ kindIcon(n.kind) }}</span>
          <div class="notif-body">
            <div class="notif-title">{{ n.title }}</div>
            <div class="notif-sub">{{ n.content }} · {{ timeText(n.created_at) }}</div>
          </div>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.bell-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 50%;
  cursor: pointer;
  color: #66758a;
}

.bell-btn:hover {
  background: #f0f4fa;
  color: #2459a9;
}

.bell-badge {
  position: absolute;
  top: -2px;
  right: -6px;
}

.notif-panel {
  margin: -4px -8px;
}

.notif-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px 10px;
  border-bottom: 1px solid #e4e9f2;
  font-weight: 600;
  color: #1d2b4f;
}

.notif-list {
  max-height: 360px;
  overflow-y: auto;
}

.notif-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid #f0f4fa;
}

.notif-item:hover {
  background: #f5f7fb;
}

.notif-item.unread {
  background: #eaf2ff;
}

.notif-item.unread .notif-title {
  font-weight: 600;
}

.notif-icon {
  font-size: 16px;
  line-height: 22px;
}

.notif-body {
  flex: 1;
  min-width: 0;
}

.notif-title {
  font-size: 13px;
  color: #1d2b4f;
  line-height: 1.5;
}

.notif-sub {
  font-size: 12px;
  color: #9aabbe;
  margin-top: 2px;
}
</style>
