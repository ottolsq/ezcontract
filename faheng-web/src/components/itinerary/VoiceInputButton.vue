<script setup>
import { Microphone, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'
import { useVoiceRecorder } from '../../composables/useVoiceRecorder'

const store = useItineraryStore()

// 全局语音入口（悬浮 FAB）：无默认日期，日期全靠嘴上说。
// 单例状态机的控制面板之一——录音状态跨路由存活，卸载不再销毁。
const rec = useVoiceRecorder()

function onClick() {
  if (!store.selectedArtistId) {
    ElMessage.warning('请先选择或新增一个人员')
    return
  }
  rec.toggle({
    source: 'fab',
    onResult: () => {
      store.voiceDialogVisible = true
    },
  })
}
</script>

<template>
  <div class="voice-fab" @click="onClick">
    <div :class="['pulse-ring', { recording: rec.isRecording.value }]"></div>
    <div :class="['btn', { recording: rec.isRecording.value }]">
      <el-icon v-if="rec.phase.value === 'processing'"><Loading class="spin" /></el-icon>
      <el-icon v-else><Microphone /></el-icon>
    </div>
    <div v-if="rec.phase.value === 'processing'" class="tip">识别中…</div>
    <div v-else-if="rec.isRecording.value" class="tip">正在听（点击结束）</div>
    <div v-else class="tip">语音录入</div>
  </div>
</template>

<style scoped>
.voice-fab {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  /* 消掉移动端 300ms 延迟与双击缩放误触 */
  touch-action: manipulation;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.btn {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #2459a9;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  box-shadow: 0 6px 18px rgba(36, 89, 169, 0.35);
  transition: all 0.2s;
}

.btn.recording {
  background: #e74c3c;
  box-shadow: 0 6px 18px rgba(231, 76, 60, 0.35);
}

.spin {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  to {
    transform: rotate(360deg);
  }
}

.pulse-ring {
  position: absolute;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 2px solid #2459a9;
  opacity: 0;
}

.pulse-ring.recording {
  animation: pulse 1.4s infinite;
}

@keyframes pulse {
  0% {
    transform: scale(1);
    opacity: 0.5;
  }
  100% {
    transform: scale(1.6);
    opacity: 0;
  }
}

.tip {
  font-size: 12px;
  color: #2459a9;
  background: #fff;
  padding: 2px 8px;
  border-radius: 999px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

@media (max-width: 768px) {
  .voice-fab {
    right: 16px;
    bottom: 16px;
  }

  .btn {
    width: 64px;
    height: 64px;
    font-size: 28px;
  }

  .pulse-ring {
    width: 64px;
    height: 64px;
  }

  .tip {
    font-size: 13px;
  }
}
</style>
