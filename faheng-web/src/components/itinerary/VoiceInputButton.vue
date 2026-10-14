<script setup>
import { ref, computed, onMounted } from 'vue'
import { Microphone } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()
const supported = ref(false)

onMounted(() => {
  supported.value = 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window
})

const isRecording = computed(() => store.voiceRecording)

function start() {
  if (!supported.value) {
    ElMessage.warning('当前浏览器不支持语音输入，请使用 Chrome 或 Edge 浏览器')
    return
  }
  if (!store.selectedArtistId) {
    ElMessage.warning('请先选择或新增一个艺人')
    return
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  const recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.continuous = true
  recognition.interimResults = true

  store.voiceRecording = true
  store.voiceText = ''
  store.voiceParsedEvents = []

  recognition.onresult = (event) => {
    let final = ''
    let interim = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript
      if (event.results[i].isFinal) {
        final += transcript
      } else {
        interim += transcript
      }
    }
    store.voiceText = (store.voiceText + final).trim() || interim
  }

  recognition.onerror = (event) => {
    store.voiceRecording = false
    if (event.error !== 'aborted') {
      ElMessage.error('语音识别出错：' + event.error)
    }
  }

  recognition.onend = async () => {
    store.voiceRecording = false
    if (!store.voiceText.trim()) {
      ElMessage.warning('未能识别到语音内容，请重试')
      return
    }
    try {
      await store.parseVoice(store.voiceText)
      store.voiceDialogVisible = true
    } catch (e) {
      // error handled in store
    }
  }

  recognition.start()

  // 10 秒后自动停止录音（避免一直占用麦克风）
  setTimeout(() => {
    try {
      recognition.stop()
    } catch {
      // ignore
    }
  }, 10000)
}
</script>

<template>
  <div class="voice-fab" @click="start">
    <div :class="['pulse-ring', { recording: isRecording }]"></div>
    <div :class="['btn', { recording: isRecording }]">
      <el-icon><Microphone /></el-icon>
    </div>
    <div v-if="isRecording" class="tip">正在听…</div>
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
