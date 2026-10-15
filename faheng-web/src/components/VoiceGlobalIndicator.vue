<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { useItineraryStore } from '../stores/itinerary'
import { useAuthStore } from '../stores/auth'
import { useVoiceRecorder } from '../composables/useVoiceRecorder'

// 跨页面录音浮标：录音/识别未结束且用户不在行程页时出现，
// 与行程页悬浮麦克风同位（视觉上是同一控件"还在原地"）。
const route = useRoute()
const store = useItineraryStore()
const auth = useAuthStore()
const rec = useVoiceRecorder()

const show = computed(
  () =>
    rec.isBusy() &&
    route.path !== '/itinerary' &&
    !route.meta.fullscreen &&
    auth.isLoggedIn
)

const isRecordingPhase = computed(
  () => rec.phase.value === 'recording' || rec.phase.value === 'starting'
)
const canStop = computed(() => rec.phase.value === 'recording')

// ── 计时器：每 tick 从 startedAt 重算（不累加），墙钟（裁决 7）──
const elapsedText = ref('00:00')
let timer = null

function tick() {
  if (!rec.startedAt.value) {
    elapsedText.value = '00:00'
    return
  }
  const sec = Math.floor((Date.now() - rec.startedAt.value) / 1000)
  const m = String(Math.floor(sec / 60)).padStart(2, '0')
  const s = String(sec % 60).padStart(2, '0')
  elapsedText.value = `${m}:${s}`
}

// 浮标只在可见时跑 interval（走查项：避免后台空转）
watch(
  show,
  (visible) => {
    if (visible) {
      tick()
      timer = setInterval(tick, 1000)
    } else if (timer) {
      clearInterval(timer)
      timer = null
    }
  },
  { immediate: true }
)

// 解析完成 toast：仅在非行程页弹（行程页确认框自己会开）；
// 空结果/失败不弹误导性提示
watch(
  () => rec.phase.value,
  (now, was) => {
    if (was && was !== 'idle' && now === 'idle' && route.path !== '/itinerary') {
      if ((store.voiceParsedEvents || []).length > 0) {
        ElMessage.success('语音已解析，回到「人员行程」确认')
      }
    }
  }
)

onMounted(() => {
  if (show.value && !timer) {
    tick()
    timer = setInterval(tick, 1000)
  }
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})

function onStop() {
  rec.stop()
}
</script>

<template>
  <div v-if="show" class="voice-indicator">
    <!-- 录音中（含 starting：结束按钮禁用，裁决 6） -->
    <template v-if="isRecordingPhase">
      <span class="rec-dot"></span>
      <span class="rec-text">正在录音 {{ elapsedText }}</span>
      <el-button
        size="small"
        type="danger"
        plain
        :disabled="!canStop"
        @click="onStop"
      >✕ 结束</el-button>
    </template>

    <!-- 识别中：只读展示，无操作面 -->
    <template v-else>
      <el-icon class="proc-spin"><Loading /></el-icon>
      <span class="rec-text">语音识别中…</span>
    </template>
  </div>
</template>

<style scoped>
.voice-indicator {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 999px;
  padding: 8px 10px 8px 14px;
  box-shadow: 0 6px 18px rgba(36, 89, 169, 0.18);
  /* 消掉移动端 300ms 延迟与双击缩放误触 */
  touch-action: manipulation;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.rec-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #e74c3c;
  flex-shrink: 0;
  animation: dot-breath 1.4s ease-in-out infinite;
}

@keyframes dot-breath {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.25;
  }
}

.rec-text {
  font-size: 13px;
  color: #1d2b4f;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.proc-spin {
  color: #2459a9;
  font-size: 16px;
  animation: proc-rotate 1s linear infinite;
}

@keyframes proc-rotate {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .voice-indicator {
    right: 16px;
    bottom: 16px;
  }
}
</style>
