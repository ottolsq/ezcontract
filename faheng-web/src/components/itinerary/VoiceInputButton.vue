<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Microphone } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()
const supported = ref(false)

// 录音：getUserMedia + MediaRecorder（参考 idcServer 的语音助手实现）
let mediaStream = null
let mediaRecorder = null
let audioChunks = []
let stopTimer = null

onMounted(() => {
  // 录音能力探测：getUserMedia + MediaRecorder（Chrome/Edge/Firefox/Safari 均支持）
  supported.value =
    !!(navigator.mediaDevices?.getUserMedia) &&
    (typeof MediaRecorder !== 'undefined')
})

onBeforeUnmount(() => {
  cleanupRecording()
})

const isRecording = computed(() => store.voiceRecording)

function cleanupRecording() {
  clearTimeout(stopTimer)
  stopTimer = null
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    try {
      mediaRecorder.stop()
    } catch {
      // ignore
    }
  }
  mediaRecorder = null
  mediaStream?.getTracks().forEach((t) => t.stop())
  mediaStream = null
  audioChunks = []
}

function pickMimeType() {
  // 常见浏览器录音格式优先级；后端统一转码
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
    'audio/mpeg',
  ]
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported?.(type)) return type
  }
  return ''
}

async function start() {
  if (!supported.value) {
    ElMessage.warning('当前浏览器不支持录音，请使用 Chrome 或 Edge 浏览器')
    return
  }
  if (!store.selectedArtistId) {
    ElMessage.warning('请先选择或新增一个艺人')
    return
  }
  // 录音中再次点击 = 提前结束并送去识别
  if (store.voiceRecording) {
    clearTimeout(stopTimer)
    stopTimer = null
    try {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop()
    } catch {
      // ignore
    }
    return
  }

  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    if (e?.name === 'NotAllowedError') {
      ElMessage.error('麦克风权限未开启，请在浏览器地址栏允许麦克风后重试')
    } else {
      ElMessage.error('无法访问麦克风：' + (e?.message || e))
    }
    return
  }

  mediaStream = stream
  audioChunks = []
  const mimeType = pickMimeType()
  mediaRecorder = mimeType
    ? new MediaRecorder(stream, { mimeType })
    : new MediaRecorder(stream)

  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) audioChunks.push(e.data)
  }

  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, {
      type: mediaRecorder?.mimeType || 'audio/webm',
    })
    cleanupRecording()
    store.voiceRecording = false

    if (!blob.size) {
      ElMessage.warning('未能识别到语音内容，请重试')
      return
    }
    try {
      await store.parseVoiceAudio(blob)
      store.voiceDialogVisible = true
    } catch (e) {
      // error handled in store
    }
  }

  store.voiceRecording = true
  store.voiceText = ''
  store.voiceParsedEvents = []
  mediaRecorder.start()

  // 10 秒后自动停止录音（避免一直占用麦克风）
  stopTimer = setTimeout(() => {
    try {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop()
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
